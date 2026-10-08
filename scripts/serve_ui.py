"""Local synthetic UI sandbox. Migrate an isolated disposable DB before serving."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if Path.cwd() != ROOT:
        parser.error("Run from the repository root")
    with TemporaryDirectory(prefix="jobintel-ui-") as directory:
        os.environ["JOBINTEL_DATABASE_URL"] = f"sqlite:///{directory}/demo.db"
        os.environ["JOBINTEL_PROVIDER"] = "fixture"
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        from jobintel.api import create_app

        uvicorn.run(
            create_app(root=ROOT / "data", demo=True),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )


if __name__ == "__main__":
    main()
