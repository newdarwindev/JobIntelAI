"""Commit failed attempts as outcomes, while snapshot/attempt writes stay atomic."""

from sqlalchemy import select

from jobintel import db
from jobintel.fetch_content import usable_text
from jobintel.fetch_types import FetchError
from jobintel.outcomes import outcome
from jobintel.registry import normalize_url
from jobintel.schemas import SnapshotInput


class AcquisitionService:
    def __init__(self, service):
        self.service, self.session = service, service.session

    @outcome("fetch")
    def fetch(self, job_id, acquirer):
        job = self.service.job(job_id)
        if not job.official_url:
            raise ValueError("job has no official_url; use the manual source editor")
        result = acquirer.fetch(job.official_url)
        snapshot = None
        if result.error is None:
            try:
                item = SnapshotInput(
                    text=result.text,
                    source_url=result.final_url,
                    format="html" if result.is_html else "text",
                )
                usable_text(item.text, result.is_html)
                normalize_url(item.source_url)
            except (ValueError, FetchError) as error:
                result.error = (
                    error if isinstance(error, FetchError) else FetchError("invalid_text", 422)
                )
                result.events[-1].update(
                    status="failed", error_code=result.error.code, retryable=False
                )
            else:
                snapshot = self.service.snapshot(job_id, item, fetch_status="http")
        fetch_id = db.new_id()
        records = [
            self.record(job_id, fetch_id, index, result, event, snapshot)
            for index, event in enumerate(result.events)
        ]
        self.session.add_all(records)
        self.session.flush()
        report = {
            "fetch_id": fetch_id,
            "status": "failed" if result.error else "success",
            "snapshot_id": snapshot.id if snapshot else None,
            "content_hash": snapshot.content_hash if snapshot else None,
            "attempts": [attempt_output(row) for row in records],
        }
        if result.error:
            report["detail"] = result.error.detail()
        return report, result.error.status if result.error else 201

    @staticmethod
    def record(job_id, fetch_id, index, result, event, snapshot):
        return db.AcquisitionAttempt(
            job_id=job_id,
            fetch_id=fetch_id,
            sequence=index,
            snapshot_id=snapshot.id if snapshot and event["status"] == "success" else None,
            created_at=event["timestamp"],
            original_url=result.original_url,
            requested_url=event["requested_url"],
            final_url=result.final_url,
            status=event["status"],
            http_status=event["http_status"],
            error_code=event["error_code"],
            retryable=event["retryable"],
            payload={
                key: value
                for key, value in event.items()
                if key
                not in {
                    "timestamp",
                    "requested_url",
                    "status",
                    "http_status",
                    "error_code",
                    "retryable",
                }
            },
        )

    def history(self, job_id):
        return [
            attempt_output(row)
            for row in self.session.scalars(
                select(db.AcquisitionAttempt)
                .where(db.AcquisitionAttempt.job_id == job_id)
                .order_by(
                    db.AcquisitionAttempt.created_at.desc(),
                    db.AcquisitionAttempt.fetch_id.desc(),
                    db.AcquisitionAttempt.sequence,
                )
            )
        ]


def attempt_output(row):
    return {
        "attempt_id": row.id,
        "fetch_id": row.fetch_id,
        "sequence": row.sequence,
        "job_id": row.job_id,
        "snapshot_id": row.snapshot_id,
        "timestamp": row.created_at,
        "recorded_at": row.recorded_at,
        "original_url": row.original_url,
        "requested_url": row.requested_url,
        "final_url": row.final_url,
        "status": row.status,
        "http_status": row.http_status,
        "error_code": row.error_code,
        "retryable": row.retryable,
        **row.payload,
    }
