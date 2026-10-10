"""Authored public URL only: production gateway on an authorized managed runner."""

import argparse
import hashlib
import json
import subprocess
import threading
from pathlib import Path
from urllib.request import getproxies

from jobintel.acquisition import HttpAcquirer
from jobintel.egress_proxy import gateway
from jobintel.fetch_transport import HttpTransport
from jobintel.fetch_types import FetchPolicy

ROOT = Path(__file__).resolve().parents[1]
URL = "https://raw.githubusercontent.com/newdarwindev/JobIntelAI/194385836fb3a1cec40e3b4637c91caed34f425f/data/sample_jobs/SYN-01.txt"


class NoDestinationDNS:
    def resolve(self, *_):
        raise AssertionError("policy-proxy must not require local destination DNS")


def exercise(transport):
    acquirer = HttpAcquirer(
        transport=transport, resolver=NoDestinationDNS(), policy=FetchPolicy(total_timeout=30)
    )
    ready = acquirer.readiness()
    result = acquirer.fetch(URL)
    return {
        "readiness": ready,
        "outcome": result.error.code if result.error else "success",
        "attempts": len(result.events),
        "http_status": result.events[-1]["http_status"],
        "bytes": len(result.text.encode()) if result.text is not None else None,
        "body_sha256": hashlib.sha256(result.text.encode()).hexdigest()
        if result.text is not None
        else None,
    }


def managed_gateway():
    if any(key in getproxies() for key in ("http", "https", "all")):
        raise RuntimeError(
            "Run on an authorized direct-egress gateway host; inherited proxies cannot be bypassed"
        )
    server = gateway("127.0.0.1", 0, ["raw.githubusercontent.com"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proxy = f"http://127.0.0.1:{server.server_port}"
    try:
        report = exercise(
            HttpTransport(mode="policy-proxy", proxies={"http": proxy, "https": proxy})
        )
        return report
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inherited-proxy",
        action="store_true",
        help="expect explicit unsupported contract in this runtime",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "work/acquisition-public.json")
    args = parser.parse_args()
    report = {
        "mode": "policy-proxy",
        "source": "authored SYN-01 at immutable repository commit",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "passed": 0,
        "failed": 1,
        "skipped": 0,
    }
    try:
        if args.inherited_proxy:
            report.update(exercise(HttpTransport(mode="policy-proxy")))
            assert (
                report["outcome"] == "proxy_capability" and report["readiness"]["ready"] is False
            ), report
            report["case"] = "unsupported inherited proxy fails before origin traffic"
        else:
            report.update(managed_gateway())
            expected = hashlib.sha256(
                (ROOT / "data/sample_jobs/SYN-01.txt").read_bytes()
            ).hexdigest()
            assert (
                report["outcome"] == "success"
                and report["readiness"]["ready"]
                and report["body_sha256"] == expected
            ), report
            report["case"] = "verified public acquisition through trusted production gateway"
        report.update(passed=1, failed=0)
    except BaseException as error:
        report["failure_kind"] = type(error).__name__
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
