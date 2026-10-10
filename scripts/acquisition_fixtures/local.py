"""Fast real-socket integration harness using the same container service code."""

from contextlib import contextmanager

from scripts.acquisition_fixtures.certificates import certificates
from scripts.acquisition_fixtures.client import acquirer
from scripts.acquisition_fixtures.origin import servers
from scripts.acquisition_fixtures.proxy import server


@contextmanager
def local_fixtures(directory, source):
    trust = certificates(directory)
    origins = servers("127.0.0.1", 0, 0, trust, source)
    proxy = server("127.0.0.1", 0, "127.0.0.1", origins[0].server_port, origins[1].server_port)
    try:
        yield {
            "proxy": f"http://127.0.0.1:{proxy.server_port}",
            "ca": trust / "ca.pem",
            "origin": origins[0].diagnostics,
            "proxy_diagnostics": proxy.diagnostics,
            "gateway": proxy,
        }
    finally:
        for instance in [proxy, *origins]:
            instance.shutdown()
            instance.server_close()


def local_acquirer(fixtures, **options):
    return acquirer(fixtures["proxy"], fixtures["ca"], **options)
