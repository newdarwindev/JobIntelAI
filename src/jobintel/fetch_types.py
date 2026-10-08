"""Bounded acquisition policy and safe outcome types; no upstream error text."""

from dataclasses import dataclass, field

MESSAGES = {
    "invalid_url": "URL must be credential-free HTTP(S) on a standard port.",
    "blocked_destination": "The destination is not a public Internet address.",
    "dns_failure": "The destination could not be resolved.",
    "dns_timeout": "Destination resolution timed out.",
    "connect_timeout": "Connecting to the destination timed out.",
    "read_timeout": "Reading the destination timed out.",
    "deadline": "The acquisition time budget was exhausted.",
    "network_failure": "The destination could not be reached.",
    "tls_error": "The destination's TLS certificate or connection could not be verified.",
    "proxy_unsupported": "The configured proxy is not a supported credential-free HTTP proxy.",
    "proxy_denied": "The configured proxy refused the pinned destination.",
    "rate_limit": "The destination rate limit persisted after bounded retries.",
    "server_error": "The destination failed after bounded retries.",
    "access_denied": "The destination denied access.",
    "http_error": "The destination did not return a usable successful response.",
    "captcha": "The destination requires a human access check.",
    "js_only": "The destination requires JavaScript to provide the posting.",
    "unsupported_type": "Only HTML and plain-text postings are supported.",
    "unsupported_encoding": "The content encoding or compression is unsupported or invalid.",
    "body_too_large": "The posting exceeds the bounded response size.",
    "invalid_text": "The response cannot be decoded as supported text.",
    "empty_source": "The response contains no usable posting text.",
    "redirect_loop": "The destination redirected in a loop.",
    "redirect_limit": "The destination exceeded three redirects.",
    "invalid_redirect": "The redirect is missing or changes HTTPS to HTTP.",
}


class FetchError(RuntimeError):
    def __init__(self, code, status=502, retryable=False):
        self.code, self.status, self.retryable = code, status, retryable
        super().__init__(MESSAGES[code])

    def detail(self):
        return {
            "code": self.code,
            "message": f"URL acquisition: {MESSAGES[self.code]} Use the manual source editor.",
            "retryable": self.retryable,
            "manual_fallback": True,
        }


@dataclass(frozen=True)
class FetchPolicy:
    connect_timeout: float = 3
    read_timeout: float = 5
    total_timeout: float = 20
    attempts: int = 3
    redirects: int = 3
    max_bytes: int = 200_000
    backoff: float = 0.5
    retry_after_cap: float = 2

    def __post_init__(self):
        ranges = [
            (self.connect_timeout, 0.001, 10),
            (self.read_timeout, 0.001, 10),
            (self.total_timeout, 0.001, 60),
            (self.attempts, 1, 3),
            (self.redirects, 0, 3),
            (self.max_bytes, 1, 200_000),
            (self.backoff, 0, 10),
            (self.retry_after_cap, 0, 10),
        ]
        if any(not low <= value <= high for value, low, high in ranges):
            raise ValueError("acquisition policy exceeds supported bounds")
        if any(type(value) is not int for value in (self.attempts, self.redirects, self.max_bytes)):
            raise ValueError("attempt, redirect and byte limits must be integers")


@dataclass
class FetchResult:
    original_url: str
    final_url: str
    events: list[dict] = field(default_factory=list)
    text: str | None = None
    is_html: bool = False
    error: FetchError | None = None
