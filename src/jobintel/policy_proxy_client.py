"""A declared trusted proxy resolves destinations; ordinary proxies fail closed."""

import json
import re
import time
from dataclasses import replace
from urllib.parse import urlsplit

import pycurl

from jobintel.egress_policy import CAPABILITIES, CAPABILITY_PATH, RESOLVE_PATH
from jobintel.fetch_destinations import DNSResolver, resolve_destination
from jobintel.fetch_types import FetchError


class PinResolver:
    def __init__(self, address):
        self.address = address

    def resolve(self, *_):
        return [self.address]


def rpc(proxy, path, timeout, *, payload=None, proxy_resolver=None):
    started = time.monotonic()
    resolver = proxy_resolver or DNSResolver()
    addresses = resolver.resolve(*proxy, timeout)
    budget = timeout - (time.monotonic() - started)
    if budget <= 0:
        raise FetchError("proxy_capability", 503)
    host = f"[{addresses[0]}]" if ":" in addresses[0] else addresses[0]
    body = bytearray()

    def receive(part):
        if len(body) + len(part) > 4096:
            return 0
        body.extend(part)
        return len(part)

    try:
        with pycurl.Curl() as curl:
            curl.setopt(pycurl.URL, f"http://{host}:{proxy[1]}{path}")
            curl.setopt(pycurl.PROXY, "")  # This is the selected gateway, never an origin route.
            curl.setopt(pycurl.TIMEOUT_MS, max(1, int(budget * 1000)))
            curl.setopt(
                pycurl.HTTPHEADER,
                ["Content-Type: application/json", f"Host: {proxy[0]}:{proxy[1]}"],
            )
            curl.setopt(pycurl.WRITEFUNCTION, receive)
            if payload is not None:
                curl.setopt(pycurl.POSTFIELDS, json.dumps(payload))
            curl.perform()
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        value = json.loads(body)
        if status != 200:
            return rpc_failure(value)
        if not isinstance(value, dict):
            raise FetchError("proxy_capability", 503)
        return value
    except FetchError:
        raise
    except (ValueError, pycurl.error):
        raise FetchError("proxy_capability", 503) from None


def rpc_failure(value):
    code = value.get("code") if isinstance(value, dict) else None
    statuses = {
        "blocked_destination": 422,
        "proxy_denied": 502,
        "dns_failure": 502,
        "dns_timeout": 504,
    }
    if code not in statuses:
        raise FetchError("proxy_capability", 503)
    raise FetchError(code, statuses[code], code in {"dns_failure", "dns_timeout"})


def capability(proxy, timeout, proxy_resolver=None):
    value = rpc(proxy, CAPABILITY_PATH, timeout, proxy_resolver=proxy_resolver)
    if value != CAPABILITIES:
        raise FetchError("proxy_capability", 503)


def policy_destination(url, proxy, timeout, proxy_resolver=None):
    started = time.monotonic()
    capability(proxy, timeout, proxy_resolver)
    parsed = urlsplit(url)
    value = rpc(
        proxy,
        RESOLVE_PATH,
        max(0.001, timeout - (time.monotonic() - started)),
        payload={"host": parsed.hostname, "scheme": parsed.scheme},
        proxy_resolver=proxy_resolver,
    )
    if value.get("host") != parsed.hostname or value.get("scheme") != parsed.scheme:
        raise FetchError("proxy_capability", 503)
    if not isinstance(value.get("address"), str) or not re.fullmatch(
        r"[a-f0-9]{64}", str(value.get("route"))
    ):
        raise FetchError("proxy_capability", 503)
    destination = resolve_destination(url, PinResolver(value["address"]), timeout)
    if destination.address != value["address"]:
        raise FetchError("proxy_capability", 503)
    return replace(destination, route=value["route"], proxy=proxy)
