"""A declared trusted proxy resolves destinations; ordinary proxies fail closed."""

import http.client
import json
import re
import socket
import threading
import time
from dataclasses import replace
from urllib.parse import urlsplit

from jobintel.egress_policy import CAPABILITIES, CAPABILITY_PATH, RESOLVE_PATH
from jobintel.fetch_destinations import DNSResolver, resolve_destination
from jobintel.fetch_types import FetchError


class PinResolver:
    def __init__(self, address):
        self.address = address

    def resolve(self, *_):
        return [self.address]


def expire(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def rpc(proxy, path, timeout, *, payload=None, proxy_resolver=None):
    started = time.monotonic()
    resolver = proxy_resolver or DNSResolver()
    addresses = resolver.resolve(*proxy, timeout)
    budget = timeout - (time.monotonic() - started)
    if budget <= 0:
        raise FetchError("proxy_capability", 503)
    connection = http.client.HTTPConnection(addresses[0], proxy[1], timeout=budget)
    guard = None
    try:
        connection.connect()
        budget = timeout - (time.monotonic() - started)
        if budget <= 0:
            raise FetchError("proxy_capability", 503)
        guard = threading.Timer(budget, expire, args=(connection.sock,))
        guard.daemon = True
        guard.start()
        connection.request(
            "GET" if payload is None else "POST",
            path,
            body=json.dumps(payload) if payload is not None else None,
            headers={"Content-Type": "application/json", "Host": f"{proxy[0]}:{proxy[1]}"},
        )
        response = connection.getresponse()
        data = response.read(4097)
        if len(data) > 4096:
            raise FetchError("proxy_capability", 503)
        value = json.loads(data)
        if response.status != 200:
            return rpc_failure(value)
        if not isinstance(value, dict):
            raise FetchError("proxy_capability", 503)
        return value
    except FetchError:
        raise
    except (OSError, ValueError, http.client.HTTPException):
        raise FetchError("proxy_capability", 503) from None
    finally:
        if guard:
            guard.cancel()
        connection.close()


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
