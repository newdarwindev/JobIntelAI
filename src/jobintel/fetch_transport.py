"""libcurl owns HTTP/TLS/CONNECT; policy owns destinations, budgets and outcomes."""

import io
import ipaddress
import math
import os
import ssl
import time
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass_environment

import pycurl

from jobintel.egress_policy import ROUTE_HEADER
from jobintel.fetch_content import remaining_budget
from jobintel.fetch_destinations import Destination, DNSResolver, resolve_destination
from jobintel.fetch_types import FetchError
from jobintel.policy_proxy_client import capability, policy_destination, rpc_failure


def configured_proxy(destination, proxies):
    if proxy_bypass_environment(destination.host, proxies):
        return None
    value = proxies.get(destination.scheme) or proxies.get("all")
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port or 80
    except ValueError:
        raise FetchError("proxy_unsupported") from None
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise FetchError("proxy_unsupported")
    return parsed.hostname, port


class CurlResponse(io.BytesIO):
    """Bounded wire buffer; libcurl removes chunk framing, never content encoding."""

    def __init__(self, policy, peer):
        super().__init__()
        self.policy, self.peer = policy, ipaddress.ip_address(peer)
        self.status, self.headers, self.error = 0, {}, None
        self.activity = None

    def prerequest(self, remote, *_):
        if ipaddress.ip_address(remote) != self.peer:
            self.error = FetchError("blocked_destination", 422)
            return pycurl.PREREQFUNC_ABORT
        self.status, self.headers = 0, {}
        self.activity = time.monotonic()
        return pycurl.PREREQFUNC_OK

    def header(self, line):
        if self.activity is not None:
            self.activity = time.monotonic()
        if line.startswith(b"HTTP/"):
            self.status, self.headers = int(line.split()[1]), {}
        elif b":" in line:
            key, value = line.decode("iso-8859-1").split(":", 1)
            self.headers[key.lower()] = value.strip()
        return len(line)

    def receive(self, data):
        self.activity = time.monotonic()
        if self.status != 200:
            return 0  # Orchestration inspects status/redirects without consuming failure bodies.
        if self.tell() + len(data) > self.policy.max_bytes:
            self.error = FetchError("body_too_large", 413)
            return 0
        return self.write(data)

    def read(self, size, timeout):
        return super().read(size)


def transfer(curl, response, deadline):
    """Multi polling preserves millisecond inactivity bounds without socket/timer owners."""
    multi = pycurl.CurlMulti()
    multi.add_handle(curl)
    try:
        while True:
            _, running = multi.perform()
            budget = remaining_budget(deadline, time.monotonic)
            if response.error:
                raise response.error
            if not running:
                break
            if response.activity is not None:
                idle = response.policy.read_timeout - (time.monotonic() - response.activity)
                if idle <= 0:
                    raise FetchError("read_timeout", 504, True)
                budget = min(budget, idle)
            multi.select(min(budget, 0.05))
        _, _, failures = multi.info_read()
        if failures:
            curl_failure(curl, response, failures[0][1])
    finally:
        multi.remove_handle(curl)
        multi.close()


def curl_failure(curl, response, code):
    if code == pycurl.E_WRITE_ERROR and response.status not in {0, 200}:
        return
    if code == pycurl.E_OPERATION_TIMEDOUT:
        raise FetchError("connect_timeout", 504, True)
    if code in {pycurl.E_PEER_FAILED_VERIFICATION, pycurl.E_SSL_CONNECT_ERROR}:
        raise FetchError("tls_error")
    if curl.getinfo(pycurl.HTTP_CONNECTCODE) not in {0, 200}:
        raise FetchError("proxy_denied")
    raise FetchError("network_failure", 502, True)


class HttpTransport:
    def __init__(self, *, proxies=None, context=None, proxy_resolver=None, mode=None):
        self.proxies, self.proxy_resolver = proxies, proxy_resolver or DNSResolver()
        self.mode = mode or os.getenv("JOBINTEL_ACQUISITION_MODE", "auto")
        if self.mode not in {"auto", "direct", "pinned-proxy", "policy-proxy"}:
            raise ValueError("unsupported JOBINTEL_ACQUISITION_MODE")
        context = context or ssl.create_default_context()
        if os.getenv("JOBINTEL_ACQUISITION_CA_FILE"):
            context.load_verify_locations(os.environ["JOBINTEL_ACQUISITION_CA_FILE"])
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("acquisition requires verified TLS")
        self.ca = "".join(
            ssl.DER_cert_to_PEM_cert(c) for c in context.get_ca_certs(binary_form=True)
        )

    def selected_proxy(self, destination):
        proxies = getproxies() if self.proxies is None else self.proxies
        proxy = configured_proxy(destination, proxies)
        if (self.mode == "direct" and proxy) or (
            self.mode in {"pinned-proxy", "policy-proxy"} and not proxy
        ):
            raise FetchError("proxy_capability", 503)
        return proxy

    def resolve(self, url, resolver, timeout):
        hint = self.hint(urlsplit(url).scheme, url)
        proxy = self.selected_proxy(hint)
        if self.mode == "policy-proxy":
            if hint.port != (443 if hint.scheme == "https" else 80):
                raise FetchError("invalid_url", 422)
            return policy_destination(url, proxy, timeout, self.proxy_resolver)
        return resolve_destination(url, resolver, timeout)

    @staticmethod
    def hint(scheme, url=None):
        parsed = urlsplit(url or f"{scheme}://readiness.invalid/")
        return Destination(
            parsed.geturl(),
            parsed.hostname,
            parsed.port or (443 if scheme == "https" else 80),
            "",
            scheme,
        )

    def readiness(self):
        try:
            for scheme in ("http", "https"):
                proxy = self.selected_proxy(self.hint(scheme))
                if self.mode == "policy-proxy":
                    capability(proxy, 3, self.proxy_resolver)
            return {
                "ready": True,
                "mode": self.mode,
                "destination_check": "per-request",
                "local_destination_dns": self.mode != "policy-proxy",
            }
        except FetchError as error:
            return {"ready": False, "mode": self.mode, "error": error.detail()}

    def options(self, curl, destination, policy, deadline, proxy, response):
        headers = [
            f"Host: {destination.authority}",
            "User-Agent: JobIntelAI/0.1",
            "Accept: text/html, text/plain, application/xhtml+xml",
            "Accept-Encoding: gzip, deflate",
            "Connection: close",
        ]
        options = {
            pycurl.URL: destination.url,
            pycurl.PROXY: "",
            pycurl.NOPROXY: "",
            pycurl.FOLLOWLOCATION: 0,
            pycurl.HTTP_CONTENT_DECODING: 0,
            pycurl.HTTP_VERSION: pycurl.CURL_HTTP_VERSION_1_1,
            pycurl.SSL_VERIFYPEER: 1,
            pycurl.SSL_VERIFYHOST: 2,
            pycurl.CAINFO_BLOB: self.ca,
            pycurl.CONNECTTIMEOUT_MS: max(
                1,
                math.ceil(
                    min(policy.connect_timeout, remaining_budget(deadline, time.monotonic)) * 1000
                ),
            ),
            pycurl.PREREQFUNCTION: response.prerequest,
            pycurl.HEADERFUNCTION: response.header,
            pycurl.WRITEFUNCTION: response.receive,
        }
        if proxy:
            self.proxy_options(options, headers, destination, response, proxy)
        else:
            options[pycurl.RESOLVE] = [
                f"{destination.host}:{destination.port}:{destination.pinned_authority.rsplit(':', 1)[0]}"
            ]
        options[pycurl.HTTPHEADER] = headers
        for key, value in options.items():
            curl.setopt(key, value)

    @staticmethod
    def proxy_options(options, headers, destination, response, proxy):
        address = f"[{response.peer}]" if response.peer.version == 6 else str(response.peer)
        options[pycurl.PROXY] = f"http://{address}:{proxy[1]}"
        if destination.route:
            route = f"{ROUTE_HEADER}: {destination.route}"
            if destination.scheme == "https":
                options[pycurl.PROXYHEADER] = [route]
            else:
                headers.append(route)
        elif destination.scheme == "https":
            options[pycurl.CONNECT_TO] = [
                f"{destination.host}:{destination.port}:{destination.pinned_authority}"
            ]
        else:
            parsed = urlsplit(destination.url)
            target = f"http://{destination.pinned_authority}{parsed.path or '/'}"
            options[pycurl.URL] = target + (f"?{parsed.query}" if parsed.query else "")
            options[pycurl.REQUEST_TARGET] = options[pycurl.URL]

    def get(self, destination, policy, remaining):
        deadline = time.monotonic() + remaining
        proxy = self.selected_proxy(destination)
        if (self.mode == "policy-proxy") != bool(destination.route) or (
            destination.route and proxy != destination.proxy
        ):
            raise FetchError("proxy_capability", 503)
        peer = (
            self.proxy_resolver.resolve(*proxy, min(policy.connect_timeout, remaining))[0]
            if proxy
            else destination.address
        )
        response = CurlResponse(policy, peer)
        with pycurl.Curl() as curl:
            self.options(curl, destination, policy, deadline, proxy, response)
            try:
                transfer(curl, response, deadline)
            except FetchError as error:
                response.close()
                if destination.route and curl.getinfo(pycurl.HTTP_CONNECTCODE) not in {0, 200}:
                    rpc_failure({"code": response.headers.get("jobintel-egress-error")})
                if response.activity is not None:
                    error.http_status = response.status or None
                raise
        if (
            destination.route
            and destination.scheme == "http"
            and response.headers.get("jobintel-egress-error")
        ):
            response.close()
            rpc_failure({"code": response.headers["jobintel-egress-error"]})
        response.seek(0)
        return response
