"""Resolve once per attempt, reject mixed answers, then pass a numeric pinned IP."""

import ipaddress
import queue
import re
import socket
import threading
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

from jobintel.fetch_types import FetchError
from jobintel.registry import normalize_url

TRANSITION_NETWORKS = [
    ipaddress.ip_network(value)
    for value in ["64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32"]
]


def public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not getattr(address, "is_site_local", False)
        and not getattr(address, "ipv4_mapped", None)
        and not any(address in network for network in TRANSITION_NETWORKS)
        and "%" not in value
    )


def canonical_destination(value):
    if len(value) > 8192 or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
    ):
        raise FetchError("invalid_url", 422)
    try:
        if urlsplit(value).username is not None or urlsplit(value).password is not None:
            raise FetchError("invalid_url", 422)
        parsed = urlsplit(normalize_url(value))
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        validate_host(host)
        authority = f"[{host}]" if ":" in host else host
        if parsed.port is not None:
            authority += f":{parsed.port}"
        return urlunsplit(
            (
                parsed.scheme,
                authority,
                quote(parsed.path, safe="/%:@!$&'()*+,;=-._~"),
                quote(parsed.query, safe="/?%:@!$&'()*+,;=-._~"),
                "",
            )
        )
    except (ValueError, UnicodeError, AttributeError) as error:
        raise FetchError("invalid_url", 422) from error


def validate_host(host):
    if host == "localhost" or host.endswith(".localhost"):
        raise FetchError("blocked_destination", 422)
    if ":" in host:
        ipaddress.ip_address(host)
        return
    labels = host.split(".")
    if len(host) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ValueError("invalid hostname")


class DNSResolver:
    def resolve(self, host, port, timeout):
        results = queue.Queue(maxsize=1)

        def lookup():
            try:
                values = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                results.put([record[4][0] for record in values])
            except OSError:
                results.put(None)

        threading.Thread(target=lookup, daemon=True).start()
        try:
            addresses = results.get(timeout=timeout)
        except queue.Empty:
            raise FetchError("dns_timeout", 504, True) from None
        if not addresses:
            raise FetchError("dns_failure", 502, True)
        return addresses


@dataclass(frozen=True)
class Destination:
    url: str
    host: str
    port: int
    address: str
    scheme: str

    @property
    def authority(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return (
            host if self.port == (443 if self.scheme == "https" else 80) else f"{host}:{self.port}"
        )

    @property
    def pinned_authority(self):
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{host}:{self.port}"


def resolve_destination(url, resolver, timeout):
    parsed = urlsplit(url)
    host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        literal = str(ipaddress.ip_address(host))
    except ValueError:
        addresses = resolver.resolve(host, port, timeout)
    else:
        addresses = [literal]
    if not addresses or not all(public_address(value) for value in addresses):
        raise FetchError("blocked_destination", 422)
    addresses = {str(ipaddress.ip_address(value)) for value in addresses}
    return Destination(url, host, port, sorted(addresses)[0], parsed.scheme)
