import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from jobintel import db
from jobintel.acquisition import FetchNotImplemented, HttpAcquirer
from jobintel.config import database_url, fixture_root
from jobintel.evaluation import run_evaluation
from jobintel.providers import FixtureProvider, ProviderUnavailable
from jobintel.registry import parse_csv
from jobintel.schemas import (
    CandidateProfile,
    EvaluateInput,
    ExtractInput,
    ImportInput,
    SnapshotInput,
)
from jobintel.service import Conflict, Service
from jobintel.snapshots import GroundingError
from jobintel.web_api import configure_web_ui

router = APIRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is created by Alembic, never implicitly at startup.
    yield
    app.state.session_factory.kw["bind"].dispose()


def service(request: Request):
    with request.app.state.session_factory() as session:
        try:
            yield Service(session, request.app.state.provider)
            session.commit()
        except KeyError as error:
            session.rollback()
            raise HTTPException(404, "job not found") from error
        except (Conflict, IntegrityError) as error:
            session.rollback()
            raise HTTPException(409, "registry conflict or missing prerequisite") from error
        except ProviderUnavailable as error:
            session.rollback()
            raise HTTPException(501, str(error)) from error
        except (GroundingError, ValueError) as error:
            session.rollback()
            raise HTTPException(422, str(error)) from error
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(503, "database unavailable or migrations required") from error


ServiceDependency = Annotated[Service, Depends(service, scope="function")]


@router.get("/health")
def health(request: Request):
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
            session.execute(text("SELECT job_id FROM jobs LIMIT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(503, "database unavailable or migrations required") from error
    return {"status": "ok", "database": "ok", "provider": "fixture", "live_llm": False}


@router.post("/jobs/import")
def import_jobs(payload: ImportInput, svc: ServiceDependency):
    return svc.import_jobs(
        payload.jobs if payload.jobs is not None else parse_csv(payload.csv_text)
    )


@router.get("/jobs")
def jobs(svc: ServiceDependency):
    return {"jobs": svc.list_jobs()}


@router.get("/jobs/{job_id}/history")
def history(job_id: str, svc: ServiceDependency):
    return svc.history(job_id)


@router.post("/candidate/validate")
def validate_candidate(payload: CandidateProfile):
    return payload.model_dump()


@router.post("/jobs/{job_id}/snapshots", status_code=201)
def snapshots(job_id: str, payload: SnapshotInput, svc: ServiceDependency):
    snapshot = svc.snapshot(job_id, payload)
    return {"snapshot_id": snapshot.id, "content_hash": snapshot.content_hash}


@router.post("/jobs/{job_id}/fetch")
def fetch(job_id: str, svc: ServiceDependency):
    job = svc.job(job_id)
    if not job.official_url:
        raise HTTPException(422, "job has no official_url; use manual snapshots")
    try:
        HttpAcquirer().fetch(job.official_url)
    except FetchNotImplemented as error:
        raise HTTPException(501, str(error)) from error


@router.post("/jobs/{job_id}/extract")
def extract(job_id: str, payload: ExtractInput, svc: ServiceDependency):
    return svc.extract(job_id, payload.configuration)


@router.get("/jobs/{job_id}")
def job(job_id: str, svc: ServiceDependency):
    return svc.get_job(job_id)


@router.post("/jobs/{job_id}/match")
def match(job_id: str, payload: CandidateProfile, svc: ServiceDependency):
    return svc.match(job_id, payload)


@router.get("/analytics/skills")
def analytics(svc: ServiceDependency, applied: bool | None = None):
    return svc.analytics(applied)


@router.post("/evaluate")
def evaluate(payload: EvaluateInput, request: Request, svc: ServiceDependency):
    report = run_evaluation(
        request.app.state.provider, request.app.state.fixture_root, payload.configurations
    )
    record = db.EvaluationRun(payload=report)
    svc.session.add(record)
    svc.session.flush()
    return {"evaluation_run_id": record.id, **report}


def create_app(url: str | None = None, root=None, *, demo: bool = False) -> FastAPI:
    if os.getenv("JOBINTEL_PROVIDER", "fixture") != "fixture":
        raise RuntimeError(
            "Only fixture provider is implemented; live providers must not silently fall back"
        )
    root = root or fixture_root()
    app = FastAPI(title="JobIntel AI", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = db.session_factory(url or database_url())
    app.state.fixture_root = root
    app.state.provider = FixtureProvider(root)
    app.include_router(router)
    configure_web_ui(app, demo)
    return app


app = create_app()
