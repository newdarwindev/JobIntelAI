"""Own the browser fixture stack outside Playwright's forcibly terminated web server."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.acquisition_environment import fixture_environment
from scripts.responses_environment import emulator_environment, write_evidence


def main():
    with TemporaryDirectory(prefix="jobintel-browser-services-") as directory:
        with (
            fixture_environment(directory) as fixtures,
            emulator_environment(
                ca_bundle="/etc/ssl/certs/ca-certificates.crt" if os.getenv("HTTPS_PROXY") else None
            ) as emulator,
        ):
            environment = {
                **os.environ,
                "UI_FIXTURE_PROXY": fixtures["proxy"],
                "UI_FIXTURE_CA": str(fixtures["ca"]),
                "UI_FIXTURE_PROJECT": fixtures["project"],
                "UI_RESPONSES_BASE": emulator["base"],
            }
            try:
                result = subprocess.run(
                    ["npx", "playwright", "test", *sys.argv[1:]], env=environment
                )
            finally:
                output = Path("work/acquisition-browser-diagnostics.json")
                output.parent.mkdir(exist_ok=True)
                evidence = {
                    "commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], text=True
                    ).strip(),
                    "transport": "production policy-proxy via trusted Compose DNS/pinning gateway",
                    "diagnostics": fixtures["diagnostics"](),
                }
                output.write_text(json.dumps(evidence, indent=2) + "\n")
                write_evidence(
                    "work/responses-browser-diagnostics.json",
                    {
                        "commit": evidence["commit"],
                        "mode": "emulator",
                        "inference": False,
                        "diagnostics": emulator["diagnostics"](),
                    },
                )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
