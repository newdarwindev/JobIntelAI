"""Local synthetic UI sandbox. Migrate an isolated disposable DB before serving."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--acquisition-fixtures",
        action="store_true",
        help="real isolated Compose HTTP/TLS origin and controlled proxy",
    )
    args = parser.parse_args()
    if Path.cwd() != ROOT:
        parser.error("Run from the repository root")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    with TemporaryDirectory(prefix="jobintel-ui-") as directory:
        os.environ["JOBINTEL_DATABASE_URL"] = f"sqlite:///{directory}/demo.db"
        os.environ["JOBINTEL_PROVIDER"] = "fixture"
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        from jobintel.api import create_app
        from scripts.acquisition_environment import diagnostics, fixture_environment
        from scripts.acquisition_fixtures.client import acquirer

        stack = selected_stack(
            args.acquisition_fixtures, directory, fixture_environment, diagnostics
        )
        with stack as fixtures:
            fetcher = acquirer(fixtures["proxy"], fixtures["ca"]) if fixtures else None
            app = create_app(root=ROOT / "data", demo=True, acquirer=fetcher)
            if fixtures:
                app.state.acquisition_mode = "fixture-http"

                @app.get("/acquisition-fixture-diagnostics")
                def acquisition_diagnostics():
                    return fixtures["diagnostics"]()

            try:
                uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
            finally:
                if fixtures:
                    output = ROOT / "work/acquisition-browser-diagnostics.json"
                    output.parent.mkdir(exist_ok=True)
                    output.write_text(json.dumps(fixtures["diagnostics"](), indent=2) + "\n")


def selected_stack(enabled, directory, fixture_environment, diagnostics):
    if not enabled:
        return nullcontext(None)
    if not os.getenv("UI_FIXTURE_PROXY"):
        return fixture_environment(directory)
    ca = Path(os.environ["UI_FIXTURE_CA"])
    project = os.environ["UI_FIXTURE_PROJECT"]
    return nullcontext(
        {
            "proxy": os.environ["UI_FIXTURE_PROXY"],
            "ca": ca,
            "diagnostics": lambda: diagnostics(project, ca.parent),
        }
    )


if __name__ == "__main__":
    main()
