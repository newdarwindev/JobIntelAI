"""Versioned bounded reads; legacy API shapes remain available explicitly."""

import base64
import json
from typing import Literal

from pydantic import Field
from sqlalchemy import and_, func, or_, select

from jobintel import db
from jobintel.schemas import StrictModel


class PageInput(StrictModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


class RegistryInput(PageInput):
    q: str = Field(default="", max_length=200)
    pipeline: Literal["all", "Awaiting source", "Source ready", "Extracted"] = "all"


def encode_cursor(scope, keys):
    return base64.urlsafe_b64encode(json.dumps([scope, keys]).encode()).decode().rstrip("=")


def decode_cursor(value, scope, width):
    try:
        data = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        valid = (
            isinstance(data, list)
            and len(data) == 2
            and data[0] == scope
            and isinstance(data[1], list)
            and len(data[1]) == width
            and all(isinstance(k, str) and 0 < len(k) <= 200 for k in data[1])
        )
        if not valid:
            raise ValueError
        return data[1]
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("invalid cursor for this catalogue selection") from error


def page_rows(session, statement, columns, request, scope, *, descending=True):
    if request.cursor:
        keys = decode_cursor(request.cursor, scope, len(columns))
        compare = [c < k if descending else c > k for c, k in zip(columns, keys, strict=True)]
        statement = statement.where(
            or_(
                *[
                    and_(*[columns[j] == keys[j] for j in range(i)], condition)
                    for i, condition in enumerate(compare)
                ]
            )
        )
    ordered = [c.desc() if descending else c.asc() for c in columns]
    rows = session.execute(statement.order_by(*ordered).limit(request.limit + 1)).mappings().all()
    more = len(rows) > request.limit
    visible = [dict(row) for row in rows[: request.limit]]
    cursor = encode_cursor(scope, [visible[-1][c.key] for c in columns]) if more else None
    return visible, {"limit": request.limit, "next_cursor": cursor, "has_more": more}


def latest_metadata(model, parent, columns):
    stamp = model.fetched_at if model is db.Snapshot else model.created_at
    return select(
        *columns,
        func.row_number()
        .over(partition_by=parent, order_by=(stamp.desc(), model.id.desc()))
        .label("position"),
    ).subquery()


def registry_statement():
    snapshots = latest_metadata(
        db.Snapshot,
        db.Snapshot.job_id,
        [
            db.Snapshot.id.label("snapshot_id"),
            db.Snapshot.job_id,
            db.Snapshot.content_hash,
            db.Snapshot.fetched_at,
        ],
    )
    runs = latest_metadata(
        db.ExtractionRun,
        db.ExtractionRun.snapshot_id,
        [
            db.ExtractionRun.id.label("run_id"),
            db.ExtractionRun.snapshot_id,
            db.ExtractionRun.configuration,
        ],
    )
    count = (
        select(func.count(db.RequirementRow.id))
        .where(db.RequirementRow.run_id == runs.c.run_id)
        .correlate(runs)
        .scalar_subquery()
    )
    return (
        select(
            db.Job.job_id,
            db.Job.payload,
            snapshots.c.snapshot_id,
            snapshots.c.content_hash,
            snapshots.c.fetched_at,
            runs.c.run_id,
            runs.c.configuration,
            count.label("requirement_count"),
        )
        .outerjoin(snapshots, and_(db.Job.job_id == snapshots.c.job_id, snapshots.c.position == 1))
        .outerjoin(
            runs,
            and_(runs.c.snapshot_id == snapshots.c.snapshot_id, runs.c.position == 1),
        )
    )


def registry_summary(row):
    return {
        **row["payload"],
        "snapshot": {
            "id": row["snapshot_id"],
            "content_hash": row["content_hash"],
            "fetched_at": row["fetched_at"],
        }
        if row["snapshot_id"]
        else None,
        "extraction": {
            "run_id": row["run_id"],
            "configuration": row["configuration"],
            "requirement_count": row["requirement_count"],
        }
        if row["run_id"]
        else None,
    }


def registry_page(session, request):
    statement = registry_statement()
    if request.q:
        statement = statement.where(
            or_(
                func.lower(db.Job.job_id).contains(request.q.lower(), autoescape=True),
                db.Job.identity.contains(request.q.casefold(), autoescape=True),
            )
        )
    views = statement.subquery()
    statement = select(views)
    if request.pipeline == "Extracted":
        statement = statement.where(views.c.run_id.is_not(None))
    elif request.pipeline == "Source ready":
        statement = statement.where(views.c.snapshot_id.is_not(None), views.c.run_id.is_(None))
    elif request.pipeline == "Awaiting source":
        statement = statement.where(views.c.snapshot_id.is_(None))
    scope = ["registry-v2", request.q, request.pipeline]
    collation = "C" if session.bind.dialect.name == "postgresql" else "BINARY"
    key = views.c.job_id.collate(collation).label("job_id")
    rows, page = page_rows(session, statement, [key], request, scope, descending=False)
    totals = registry_totals(session)
    return {
        "catalogue_version": 2,
        "jobs": [registry_summary(r) for r in rows],
        "page": page,
        "totals": totals,
    }


def registry_totals(session):
    views = registry_statement().subquery()
    row = (
        session.execute(
            select(
                func.count().label("registered"),
                func.count(views.c.snapshot_id).label("snapshotted"),
                func.count(views.c.run_id).label("extracted"),
                func.coalesce(func.sum(views.c.requirement_count), 0).label("requirements"),
            ).select_from(views)
        )
        .mappings()
        .one()
    )
    return dict(row)


def catalogue_page(service, kind, request, owner=None):
    statements = {
        "snapshots": snapshot_summaries,
        "acquisition": acquisition_summaries,
        "attempts": extraction_summaries,
        "runs": run_summaries,
        "revisions": revision_summaries,
        "evaluations": evaluation_summaries,
    }
    statement, columns = statements[kind](owner)
    if kind in {"snapshots", "acquisition", "attempts"}:
        service.job(owner)
    rows, page = page_rows(
        service.session, statement, columns, request, ["catalogue-v2", kind, owner]
    )
    return {"catalogue_version": 2, "items": rows, "page": page}


def snapshot_summaries(job_id):
    model = db.Snapshot
    count = (
        select(func.count(db.ExtractionRun.id))
        .where(db.ExtractionRun.snapshot_id == model.id)
        .scalar_subquery()
    )
    return select(
        model.id,
        model.fetched_at,
        model.content_hash,
        model.source_url,
        model.fetch_status,
        count.label("run_count"),
    ).where(model.job_id == job_id), [model.fetched_at, model.id]


def run_summaries(snapshot_id):
    model = db.ExtractionRun
    count = (
        select(func.count(db.RequirementRow.id))
        .where(db.RequirementRow.run_id == model.id)
        .scalar_subquery()
    )
    return select(
        model.id,
        model.created_at,
        model.configuration,
        model.schema_version,
        count.label("requirement_count"),
    ).where(model.snapshot_id == snapshot_id), [model.created_at, model.id]


def acquisition_summaries(job_id):
    model = db.AcquisitionAttempt
    columns = [
        model.id,
        model.created_at,
        model.status,
        model.http_status,
        model.error_code,
        model.retryable,
        model.original_url,
        model.requested_url,
        model.final_url,
        model.snapshot_id,
        model.fetch_id,
        model.sequence,
    ]
    return select(*columns).where(model.job_id == job_id), [model.created_at, model.id]


def extraction_summaries(job_id):
    model = db.ExtractionAttempt
    return select(
        model.id,
        model.created_at,
        model.snapshot_id,
        model.run_id,
        model.configuration,
        model.status,
        model.error_code,
        model.retryable,
    ).where(model.job_id == job_id), [model.created_at, model.id]


def revision_summaries(profile_id):
    model = db.CandidateEvidenceRow
    return select(model.id, model.profile_id, model.created_at).where(
        model.profile_id == profile_id
    ), [model.created_at, model.id]


def evaluation_summaries(_owner):
    model = db.EvaluationRun
    return select(
        model.id,
        model.created_at,
        model.payload["dataset"].as_string().label("dataset"),
        model.payload["status"].as_string().label("status"),
    ).select_from(model), [model.created_at, model.id]


def snapshot_detail(service, job_id, snapshot_id):
    row = service.session.get(db.Snapshot, snapshot_id)
    if row is None or row.job_id != job_id:
        raise KeyError(snapshot_id)
    return {
        "id": row.id,
        "job_id": row.job_id,
        "clean_text": row.clean_text,
        "content_hash": row.content_hash,
        "source_url": row.source_url,
        "fetched_at": row.fetched_at,
    }
