"""Credential-free standard-port URL identity, shared without schema dependencies."""

from urllib.parse import urlsplit, urlunsplit


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("official URL must be HTTP(S), without user credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("only standard HTTP(S) ports are supported")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "https" and port == 443)
        or (parsed.scheme.lower() == "http" and port == 80)
    ):
        host += f":{port}"
    # Preserve path case, trailing slashes and query parameters: these may be meaningful.
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, ""))
