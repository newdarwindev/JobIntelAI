import json
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from jobintel import db
from jobintel.acquisition import HttpAcquirer
from jobintel.acquisition_service import AcquisitionService
from jobintel.config import database_url, fixture_root
from jobintel.corpus_analytics import AnalyticsInput
from jobintel.evaluation_runs import run_report
from jobintel.evaluation_store import get_report, list_reports, save_report
from jobintel.export_selection import ExportInput
from jobintel.exports import ExportService
from jobintel.extraction_attempts import attempt_extract
from jobintel.normalization import Taxonomy
from jobintel.openai_transport import ProviderError
from jobintel.providers import ProviderUnavailable, selected_configuration, selected_provider
from jobintel.registry import parse_csv
from jobintel.schemas import (
    CandidateProfile,
    EvaluateInput,
    ExtractInput,
    ImportInput,
    MatchSelection,
    SnapshotInput,
)
from jobintel.service import Conflict, Service
from jobintel.snapshots import GroundingError
from jobintel.synthetic_fetch import synthetic_acquirer
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
            yield Service(session, request.app.state.provider, request.app.state.taxonomy)
            session.commit()
        except KeyError as error:
            session.rollback()
            raise HTTPException(404, "job, candidate revision or match run not found") from error
        except Conflict as error:
            session.rollback()
            raise HTTPException(409, str(error)) from error
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(409, "registry conflict or missing prerequisite") from error
        except ProviderError as error:
            session.rollback()
            raise HTTPException(error.status, error.detail()) from error
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
            session.execute(select(db.ExtractionRun.provenance).limit(1))
            session.execute(select(db.MatchRun.id).limit(1))
            session.execute(select(db.AcquisitionAttempt.id).limit(1))
            session.execute(select(db.ExtractionAttempt.id).limit(1))
    except SQLAlchemyError as error:
        raise HTTPException(503, "database unavailable or migrations required") from error
    provider = request.app.state.provider
    acquisition = request.app.state.acquirer.readiness()
    return JSONResponse(
        {
            "status": "ok" if acquisition["ready"] else "not_ready",
            "database": "ok",
            "provider": provider.name,
            "live_llm": provider.name == "openai",
            "provider_ready": True,
            "configuration": request.app.state.configuration,
            "acquisition": acquisition,
        },
        status_code=200 if acquisition["ready"] else 503,
    )


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
    return payload.model_dump(mode="json")


@router.post("/candidates/import", status_code=201)
def import_candidate(payload: CandidateProfile, svc: ServiceDependency):
    return svc.import_candidate(payload)


@router.get("/candidates/{profile_id}/revisions")
def candidate_revisions(profile_id: str, svc: ServiceDependency):
    return svc.candidate_revisions(profile_id)


@router.get("/candidates/{profile_id}/revisions/{revision_id}")
def candidate_revision(profile_id: str, revision_id: str, svc: ServiceDependency):
    return svc.candidate(profile_id, revision_id)


@router.get("/match-runs/{match_run_id}")
def match_run(match_run_id: str, svc: ServiceDependency):
    return svc.match_run(match_run_id)


@router.post("/jobs/{job_id}/snapshots", status_code=201)
def snapshots(job_id: str, payload: SnapshotInput, svc: ServiceDependency):
    snapshot = svc.snapshot(job_id, payload)
    return {"snapshot_id": snapshot.id, "content_hash": snapshot.content_hash}


@router.post("/jobs/{job_id}/fetch")
def fetch(job_id: str, request: Request, svc: ServiceDependency):
    report, status = AcquisitionService(svc).fetch(job_id, request.app.state.acquirer)
    return JSONResponse(report, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/jobs/{job_id}/extract")
def extract(job_id: str, payload: ExtractInput, request: Request, svc: ServiceDependency):
    configuration = payload.configuration or request.app.state.configuration
    result, error = attempt_extract(svc, job_id, configuration)
    if error:
        return extraction_failure(error)
    return result


def extraction_failure(error):
    if isinstance(error, ProviderError):
        return JSONResponse({"detail": error.detail()}, status_code=error.status)
    status = 501 if isinstance(error, ProviderUnavailable) else 422
    return JSONResponse({"detail": str(error)}, status_code=status)


@router.get("/jobs/{job_id}")
def job(job_id: str, svc: ServiceDependency):
    return svc.get_job(job_id)


@router.post("/jobs/{job_id}/match")
def match(job_id: str, payload: CandidateProfile | MatchSelection, svc: ServiceDependency):
    return svc.match(job_id, payload)


@router.get("/analytics/skills")
def analytics(svc: ServiceDependency, selection: Annotated[AnalyticsInput, Query()]):
    return JSONResponse(
        svc.analytics(**selection.model_dump()), headers={"Cache-Control": "no-store"}
    )


@router.post("/exports")
def exports(payload: ExportInput, svc: ServiceDependency):
    result = ExportService(svc.session).export(payload)
    if payload.format == "csv":
        return Response(
            result,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="jobintel-{payload.kind}.csv"',
                "Cache-Control": "no-store",
            },
        )
    return Response(
        json.dumps(result, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/evaluate")
def evaluate(payload: EvaluateInput, request: Request, svc: ServiceDependency):
    svc.session.execute(select(db.EvaluationRun.id).limit(1))
    configurations = payload.configurations or [request.app.state.configuration]
    if payload.configurations is None and request.app.state.provider.name == "fixture":
        configurations = ["fixture_raw", "fixture_normalized"]
    report = run_report(
        request.app.state.provider,
        request.app.state.fixture_root,
        configurations,
        dataset=payload.dataset,
        pricing=payload.pricing,
    )
    saved = save_report(svc.session, report)
    errors = [r["error"] for result in report["results"] for r in result["per_case"] if r["error"]]
    if errors and request.app.state.provider.name == "openai":
        return JSONResponse(
            {"detail": errors[0], **saved},
            status_code=errors[0]["status"],
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(saved, headers={"Cache-Control": "no-store"})


@router.get("/evaluation-runs")
def evaluation_runs(svc: ServiceDependency):
    return JSONResponse(list_reports(svc.session), headers={"Cache-Control": "no-store"})


@router.get("/evaluation-runs/{run_id}")
def evaluation_run(run_id: str, svc: ServiceDependency):
    return JSONResponse(get_report(svc.session, run_id), headers={"Cache-Control": "no-store"})


def create_app(
    url: str | None = None,
    root=None,
    *,
    demo: bool = False,
    provider_name=None,
    configuration=None,
    transport=None,
    model=None,
    acquirer=None,
) -> FastAPI:
    root = root or fixture_root()
    app = FastAPI(title="JobIntel AI", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = db.session_factory(url or database_url())
    app.state.fixture_root = root
    app.state.provider = selected_provider(root, provider_name, transport=transport, model=model)
    app.state.configuration = selected_configuration(app.state.provider, configuration)
    app.state.taxonomy = Taxonomy(root / "taxonomy.json")
    app.state.acquirer = (
        acquirer if acquirer is not None else synthetic_acquirer(root) if demo else HttpAcquirer()
    )
    if not demo:
        app.state.acquisition_mode = getattr(app.state.acquirer.transport, "mode", "injected")
    if demo and app.state.provider.name != "fixture":
        raise ValueError("the synthetic demo requires fixture provider")
    app.include_router(router)
    configure_web_ui(app, demo)
    return app


app = create_app()
