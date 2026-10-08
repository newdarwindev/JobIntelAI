"""Bounded, injectable acquisition that returns auditable outcomes on refusal."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from jobintel.fetch_content import read_posting, remaining_budget
from jobintel.fetch_destinations import DNSResolver, canonical_destination, resolve_destination
from jobintel.fetch_transport import HttpTransport
from jobintel.fetch_types import FetchError, FetchPolicy, FetchResult

REDIRECTS = {301, 302, 303, 307, 308}


def retry_after(value, now, cap):
    if not value:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            delay = (parsed - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, min(delay, cap))


def response_error(status):
    if status == 429:
        return FetchError("rate_limit", 503, True)
    if 500 <= status <= 599:
        return FetchError("server_error", 502, True)
    if status in {401, 403}:
        return FetchError("access_denied", 403)
    if status != 200:
        return FetchError("http_error", 502)
    return None


class HttpAcquirer:
    def __init__(
        self,
        *,
        transport=None,
        resolver=None,
        policy=None,
        sleep=time.sleep,
        clock=time.monotonic,
        now=lambda: datetime.now(UTC),
    ):
        self.transport = transport if transport is not None else HttpTransport()
        self.resolver = resolver if resolver is not None else DNSResolver()
        self.policy = policy or FetchPolicy()
        self.sleep, self.clock, self.now = sleep, clock, now

    def fetch(self, url):
        result = FetchResult(url, url)
        deadline = self.clock() + self.policy.total_timeout
        try:
            current = canonical_destination(url)
            result.final_url = current
            self.walk(result, current, deadline)
        except FetchError as error:
            result.error = error
            if not result.events:
                result.events.append(self.event(result.final_url, 0, 0))
            result.events[-1].update(
                status="failed", error_code=error.code, retryable=error.retryable
            )
        return result

    def walk(self, result, current, deadline):
        visited = {current}
        for hop in range(self.policy.redirects + 1):
            target = self.fetch_url(result, current, hop, deadline)
            if target is None:
                return
            if target in visited:
                raise FetchError("redirect_loop", 422)
            if hop == self.policy.redirects:
                raise FetchError("redirect_limit", 422)
            visited.add(target)
            current = target

    def fetch_url(self, result, url, hop, deadline):
        for attempt in range(self.policy.attempts):
            try:
                return self.request(result, url, hop, attempt, deadline)
            except FetchError as error:
                if not error.retryable or attempt == self.policy.attempts - 1:
                    raise
                event = result.events[-1]
                delay = event.get("retry_after_seconds")
                if delay is None:
                    delay = min(self.policy.backoff * 2**attempt, self.policy.retry_after_cap)
                if delay >= remaining_budget(deadline, self.clock):
                    raise FetchError("deadline", 504, True) from None
                event["wait_seconds"] = delay
                self.sleep(delay)
        raise RuntimeError("unreachable acquisition retry state")

    def event(self, url, hop, attempt):
        return {
            "requested_url": url,
            "timestamp": self.now().isoformat(),
            "status": "failed",
            "http_status": None,
            "error_code": None,
            "retryable": False,
            "redirect_index": hop,
            "retry_index": attempt,
            "wait_seconds": 0,
        }

    def request(self, result, url, hop, attempt, deadline):
        event = self.event(url, hop, attempt)
        result.events.append(event)
        result.final_url = url
        try:
            budget = remaining_budget(deadline, self.clock)
            destination = resolve_destination(
                url, self.resolver, min(self.policy.connect_timeout, budget)
            )
            with self.transport.get(
                destination, self.policy, remaining_budget(deadline, self.clock)
            ) as response:
                event["http_status"] = response.status
                if response.status in REDIRECTS:
                    target = self.redirect(url, response.headers.get("location"))
                    event.update(status="redirect", redirect_url=target)
                    return target
                error = response_error(response.status)
                if error:
                    event["retry_after_seconds"] = retry_after(
                        response.headers.get("retry-after"), self.now(), self.policy.retry_after_cap
                    )
                    raise error
                text, is_html, metadata = read_posting(response, self.policy, deadline, self.clock)
                result.text, result.is_html = text, is_html
                event.update(status="success", **metadata)
                return None
        except FetchError as error:
            if self.clock() >= deadline:
                error = FetchError("deadline", 504, True)
            event.update(status="failed", error_code=error.code, retryable=error.retryable)
            raise error

    @staticmethod
    def redirect(url, location):
        if not location:
            raise FetchError("invalid_redirect", 422)
        target = canonical_destination(urljoin(url, location))
        if urlsplit(url).scheme == "https" and urlsplit(target).scheme != "https":
            raise FetchError("invalid_redirect", 422)
        return target
