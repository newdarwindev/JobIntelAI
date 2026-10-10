"""Administrator-trusted egress contract: bounded, single-use DNS pin leases."""

import secrets
import threading
import time
from urllib.parse import urlsplit

from jobintel.fetch_destinations import DNSResolver, canonical_destination, resolve_destination
from jobintel.fetch_types import FetchError

CAPABILITIES = {
    "protocol": "jobintel-egress-v1",
    "guarantees": [
        "complete-public-dns",
        "connect-revalidation",
        "single-use-pin",
        "exact-host-policy",
    ],
}
CAPABILITY_PATH = "/jobintel-egress/v1/capabilities"
RESOLVE_PATH = "/jobintel-egress/v1/resolve"
ROUTE_HEADER = "JobIntel-Route"


class EgressPolicy:
    def __init__(self, hosts, *, resolver=None, clock=time.monotonic):
        self.hosts = frozenset(hosts)
        self.resolver = resolver or DNSResolver()
        self.clock, self.lock, self.leases = clock, threading.Lock(), {}

    def destination(self, host, scheme):
        if scheme not in {"http", "https"} or not isinstance(host, str):
            raise FetchError("invalid_url", 422)
        authority = f"[{host}]" if ":" in host else host
        url = canonical_destination(f"{scheme}://{authority}/")
        parsed = urlsplit(url)
        if parsed.hostname != host or parsed.port is not None or parsed.path != "/":
            raise FetchError("invalid_url", 422)
        if host not in self.hosts:
            resolve_destination(url, RefusingResolver(), 3)
        destination = resolve_destination(url, self.resolver, 3)
        if destination.host not in self.hosts:
            raise FetchError("proxy_denied")
        return destination

    def issue(self, host, scheme):
        destination = self.destination(host, scheme)
        token = secrets.token_hex(32)
        with self.lock:
            self.leases = {k: v for k, v in self.leases.items() if v[1] > self.clock()}
            if len(self.leases) >= 1024:
                raise FetchError("proxy_denied")
            self.leases[token] = (destination, self.clock() + 10)
        return {
            "host": destination.host,
            "scheme": scheme,
            "address": destination.address,
            "route": token,
        }

    def consume(self, token, host, scheme):
        with self.lock:
            lease = self.leases.pop(token, None)
        if not lease or lease[1] <= self.clock():
            raise FetchError("proxy_denied")
        pinned = lease[0]
        if (pinned.host, pinned.scheme) != (host, scheme):
            raise FetchError("proxy_denied")
        current = self.destination(host, scheme)
        if current.address != pinned.address:
            raise FetchError("blocked_destination", 422)
        return pinned


class RefusingResolver:
    def resolve(self, *_):
        raise FetchError("proxy_denied")
