"""Own the browser fixture stack outside Playwright's forcibly terminated web server."""

import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from jobintel.experiments import code_provenance
from scripts.acquisition_environment import fixture_environment
from scripts.browser_services import normal_api
from scripts.responses_environment import emulator_environment, request, write_evidence


def main():
    # Validate fixture declarations before starting costly provider services.
    subprocess.run(["npx", "playwright", "test", "--list", *sys.argv[1:]], check=True)
    with TemporaryDirectory(prefix="jobintel-browser-services-") as directory:
        with (
            fixture_environment(directory) as fixtures,
            emulator_environment(
                ca_bundle="/etc/ssl/certs/ca-certificates.crt" if os.getenv("HTTPS_PROXY") else None
            ) as emulator,
            ExitStack() as persistent,
        ):
            normal = {}
            try:
                for mode in ["fixture", "emulator", "local"]:
                    normal[mode] = persistent.enter_context(normal_api(mode, fixtures))
                environment = {
                    **os.environ,
                    "UI_FIXTURE_PROXY": fixtures["proxy"],
                    "UI_FIXTURE_CA": str(fixtures["ca"]),
                    "UI_FIXTURE_PROJECT": fixtures["project"],
                    "UI_RESPONSES_BASE": emulator["base"],
                    "UI_NORMAL_SERVICES": json.dumps(normal),
                }
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
                write_evidence(
                    "work/persistent-browser-services.json",
                    {
                        "code_provenance": code_provenance(),
                        "services": normal,
                        "emulator_diagnostics": request(
                            normal["emulator"]["control_base"], "/diagnostics"
                        )
                        if "emulator" in normal
                        else None,
                    },
                )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
