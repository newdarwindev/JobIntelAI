"""Test-only API launcher; fixture routes and routing never enter the shipping app."""

import os
from pathlib import Path

import uvicorn

from jobintel.api import create_app
from scripts.acquisition_fixtures.client import acquirer


def main():
    app = create_app(
        demo=True,
        acquirer=acquirer("http://proxy:8088", Path("/run/acquisition-ca.pem")),
    )
    app.state.acquisition_mode = "fixture-http"
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), access_log=False)


if __name__ == "__main__":
    main()
