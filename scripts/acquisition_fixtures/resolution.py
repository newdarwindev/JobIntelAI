"""Authored DNS answers for isolated origins; no external resolution."""

from jobintel.fetch_types import FetchError
from scripts.acquisition_fixtures.proxy import HOSTS, PIN


class FixtureResolver:
    def __init__(self, repeat=1):
        self.rebindings = 0
        self.repeat = repeat

    def resolve(self, host, port, timeout):
        if host == "private.example.test":
            return ["10.0.0.1"]
        if host == "mixed.example.test":
            return [PIN, "127.0.0.1"]
        if host == "denied.example.test":
            return ["93.184.216.35"]
        if host == "rebind.example.test":
            self.rebindings += 1
            return [PIN] if self.rebindings <= self.repeat else ["127.0.0.1"]
        if host not in HOSTS or port not in {80, 443}:
            raise FetchError("dns_failure")
        return [PIN]
