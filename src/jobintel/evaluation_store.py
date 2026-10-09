"""Append-only evaluation report reads shared by API and CLI."""

from sqlalchemy import select

from jobintel import db


def save_report(session, report):
    record = db.EvaluationRun(payload=report)
    session.add(record)
    session.flush()
    return {"evaluation_run_id": record.id, **report}


def get_report(session, run_id):
    record = session.get(db.EvaluationRun, run_id)
    if record is None:
        raise KeyError(run_id)
    return {"evaluation_run_id": record.id, **record.payload}


def list_reports(session):
    records = session.scalars(
        select(db.EvaluationRun).order_by(
            db.EvaluationRun.created_at.desc(), db.EvaluationRun.id.desc()
        )
    )
    return {
        "evaluation_runs": [
            {
                "evaluation_run_id": r.id,
                "created_at": r.created_at,
                "dataset": r.payload.get("dataset", "fixture"),
                "status": r.payload.get("status", "completed"),
            }
            for r in records
        ]
    }
