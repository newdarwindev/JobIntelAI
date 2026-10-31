"""One loopback FastAPI process for paste, compare, save, and export."""

import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import provider
from .store import Store, digest

app = FastAPI(title="JobIntel AI local")
store = Store(os.environ.get("JOBINTEL_DB", "local_data/jobintel.sqlite3"))
WEB = Path(__file__).parent / "web"


class Input(BaseModel):
    job: str = Field(min_length=20, max_length=200_000)
    candidate: str = Field(min_length=20, max_length=200_000)
    reference_url: str | None = Field(default=None, max_length=2000)


def grounded(items: list[dict], job: str, candidate: str) -> list[dict]:
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError("Invalid comparison count")
    output = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid comparison")
        requirement = item.get("requirement")
        job_quote = item.get("job_quote")
        candidate_quote = item.get("candidate_quote")
        status = item.get("status")
        reason = item.get("reason")
        if (
            not all(
                isinstance(x, str)
                for x in (requirement, job_quote, candidate_quote, status, reason)
            )
            or not requirement
            or not job_quote
            or len(reason) > 1000
            or status not in {"SUPPORTED", "UNKNOWN"}
            or (status == "SUPPORTED" and not candidate_quote)
            or job_quote not in job
            or (candidate_quote and candidate_quote not in candidate)
        ):
            raise ValueError("Invalid evidence or status")
        output.append(
            {
                "requirement": requirement,
                "status": status,
                "reason": reason,
                "job": {
                    "quote": job_quote,
                    "start": job.index(job_quote),
                    "end": job.index(job_quote) + len(job_quote),
                },
                "candidate": (
                    {
                        "quote": candidate_quote,
                        "start": candidate.index(candidate_quote),
                        "end": candidate.index(candidate_quote) + len(candidate_quote),
                    }
                    if candidate_quote
                    else None
                ),
            }
        )
    return output


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/app.js")
def javascript():
    return FileResponse(WEB / "app.js", media_type="text/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "provider_configured": bool(os.getenv("JOBINTEL_OPENAI_API_KEY"))}


@app.post("/api/compare")
def compare(body: Input, idempotency_key: str = Header()):
    try:
        UUID(idempotency_key)
    except ValueError as exc:
        raise HTTPException(422, "Idempotency-Key must be a UUID") from exc
    canonical = body.model_dump_json()
    body_hash = digest(canonical)
    try:
        existing = store.reserve(idempotency_key, body_hash)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if existing:
        return existing
    try:
        result = grounded(provider.compare(body.job, body.candidate), body.job, body.candidate)
        return store.save(
            idempotency_key,
            body_hash,
            body.job,
            body.candidate,
            body.reference_url,
            os.getenv("JOBINTEL_OPENAI_MODEL", "gpt-4o-mini"),
            result,
        )
    except (provider.ProviderError, ValueError) as exc:
        store.reject(idempotency_key)
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/records")
def records():
    return store.recent()


@app.get("/api/records/{record_id}")
def record(record_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", record_id):
        raise HTTPException(404, "Record not found")
    value = store.get(record_id)
    if not value:
        raise HTTPException(404, "Record not found")
    return value


@app.get("/api/records/{record_id}/export")
def export(record_id: str):
    value = record(record_id)
    return JSONResponse(
        value, headers={"Content-Disposition": f'attachment; filename="jobintel-{record_id}.json"'}
    )


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
