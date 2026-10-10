"""Exact test DNS answers feed the unchanged production admission and transport."""

import ssl

from jobintel.acquisition import HttpAcquirer
from jobintel.fetch_transport import HttpTransport
from scripts.acquisition_fixtures.resolution import FixtureResolver as FixtureResolver


def acquirer(proxy, ca, policy=None, *, trusted=True, mode="pinned-proxy"):
    context = (
        ssl.create_default_context(cafile=str(ca)) if trusted else ssl.create_default_context()
    )
    return HttpAcquirer(
        resolver=FixtureResolver(),
        policy=policy,
        transport=HttpTransport(
            proxies={"http": proxy, "https": proxy}, context=context, mode=mode
        ),
    )
