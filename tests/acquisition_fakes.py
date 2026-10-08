"""Authored offline responses and resolver/clock probes; never real URL crawling."""

import io
from datetime import UTC, datetime

from jobintel.acquisition import HttpAcquirer

PUBLIC = "93.184.216.34"
URL = "https://example.com/authored"


class Resolver:
    def __init__(self, answers=None):
        self.answers = answers or [[PUBLIC]]
        self.calls = []

    def resolve(self, host, port, timeout):
        self.calls.append((host, port, timeout))
        result = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


class Response:
    def __init__(self, status=200, body=b"Python is required.", headers=None, read_error=None):
        self.status, self.headers = (
            status,
            headers if headers is not None else {"content-type": "text/plain"},
        )
        self.body, self.read_error = io.BytesIO(body), read_error
        self.closed, self.reads = False, []

    def read(self, size, timeout):
        self.reads.append((size, timeout))
        if self.read_error:
            raise self.read_error
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, destination, policy, remaining):
        self.calls.append((destination, policy, remaining))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class Clock:
    def __init__(self):
        self.value, self.waits = 0, []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.waits.append(delay)
        self.value += delay


def acquirer(*responses, resolver=None, policy=None):
    transport, clock = Transport(*responses), Clock()
    result = HttpAcquirer(
        transport=transport,
        resolver=resolver or Resolver(),
        policy=policy,
        sleep=clock.sleep,
        clock=clock,
        now=lambda: datetime(2026, 10, 8, tzinfo=UTC),
    )
    return result, transport, clock
