"""Static UI and explicitly selected synthetic-sandbox routes."""

import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete

from jobintel import db
from jobintel.provider_execution import execution_mode
from jobintel.registry import parse_csv

router = APIRouter()
demo_router = APIRouter()


@router.get("/ui/config")
def ui_config(request: Request):
    provider = request.app.state.provider
    return {
        "demo": request.app.state.demo,
        "provider": provider.name,
        "execution_mode": execution_mode(provider),
        "live_llm": execution_mode(provider) == "hosted",
        "acquisition_mode": getattr(
            request.app.state, "acquisition_mode", "synthetic" if request.app.state.demo else "http"
        ),
    }


@demo_router.get("/ui/fixtures")
def ui_fixtures(request: Request):
    root = request.app.state.fixture_root
    return {
        "csv": (root / "sample_registry.csv").read_text(),
        "jobs": [
            item.model_dump() for item in parse_csv((root / "sample_registry.csv").read_text())
        ],
        "sources": {p.stem: p.read_text() for p in (root / "sample_jobs").glob("SYN-*.txt")},
        "candidate": json.loads((root / "sample_candidate.json").read_text()),
    }


@demo_router.post("/ui/reset")
def reset_synthetic_sandbox(request: Request):
    # This router is installed only on the explicitly selected disposable demo.
    with request.app.state.session_factory.begin() as session:
        for table in reversed(db.Base.metadata.sorted_tables):
            session.execute(delete(table))
    return {"reset": True}


def configure_web_ui(app: FastAPI, demo: bool):
    app.state.demo = demo
    app.include_router(router)
    if demo:
        app.include_router(demo_router)
    app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web-ui")
