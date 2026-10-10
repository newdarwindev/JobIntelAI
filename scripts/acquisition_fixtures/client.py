"""Exact test DNS answers feed the unchanged production admission and transport."""

import ssl

from jobintel.acquisition import HttpAcquirer
from jobintel.fetch_transport import HttpTransport
from jobintel.fetch_types import FetchError
from scripts.acquisition_fixtures.proxy import HOSTS, PIN


class FixtureResolver:
    def __init__(self):
        self.rebindings = 0

    def resolve(self, host, port, timeout):
        if host == "private.example.test":
            return ["10.0.0.1"]
        if host == "mixed.example.test":
            return [PIN, "127.0.0.1"]
        if host == "denied.example.test":
            return ["93.184.216.35"]
        if host == "rebind.example.test":
            self.rebindings += 1
            return [PIN] if self.rebindings == 1 else ["127.0.0.1"]
        if host not in HOSTS or port not in {80, 443}:
            raise FetchError("dns_failure")
        return [PIN]


def acquirer(proxy, ca, policy=None, *, trusted=True):
    context = (
        ssl.create_default_context(cafile=str(ca)) if trusted else ssl.create_default_context()
    )
    return HttpAcquirer(
        resolver=FixtureResolver(),
        policy=policy,
        transport=HttpTransport(proxies={"http": proxy, "https": proxy}, context=context),
    )
