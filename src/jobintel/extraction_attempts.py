"""Persist expected failures in the caller's transaction; SQL failures still roll back."""

from sqlalchemy import select

from jobintel import db
from jobintel.openai_transport import ProviderError
from jobintel.providers import ProviderUnavailable
from jobintel.snapshots import GroundingError


def failure_code(error):
    if isinstance(error, ProviderError):
        return error.code, error.retryable
    if isinstance(error, ProviderUnavailable):
        return "provider_unavailable", False
    return "invalid_evidence" if isinstance(error, GroundingError) else "validation_error", False


def attempt_extract(service, job_id, configuration):
    snapshot = service.latest_snapshot(job_id)
    if snapshot is None:
        from jobintel.service import Conflict

        raise Conflict("create a snapshot before extraction")
    result, error = None, None
    try:
        with service.session.begin_nested():
            result = service.extract(job_id, configuration, snapshot=snapshot)
    except (ProviderError, ProviderUnavailable, ValueError) as caught:
        error = caught
    code, retryable = failure_code(error) if error else (None, False)
    service.session.add(
        db.ExtractionAttempt(
            job_id=job_id,
            snapshot_id=snapshot.id,
            configuration=configuration,
            status="failed" if error else "success",
            error_code=code,
            retryable=retryable,
            run_id=result["run_id"] if result else None,
        )
    )
    service.session.flush()
    return result, error


def history(session, job_id):
    return [
        {
            "attempt_id": row.id,
            "snapshot_id": row.snapshot_id,
            "run_id": row.run_id,
            "timestamp": row.created_at,
            "configuration": row.configuration,
            "status": row.status,
            "error_code": row.error_code,
            "retryable": row.retryable,
        }
        for row in session.scalars(
            select(db.ExtractionAttempt)
            .where(db.ExtractionAttempt.job_id == job_id)
            .order_by(db.ExtractionAttempt.created_at.desc(), db.ExtractionAttempt.id.desc())
        )
    ]
