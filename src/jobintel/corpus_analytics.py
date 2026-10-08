"""Shared persisted-source analytics with bounded queries and explicit coverage."""

from collections import Counter

from pydantic import model_validator
from sqlalchemy import func, select

from jobintel import db
from jobintel.export_selection import ExportInput
from jobintel.exports import ExportService, latest_rows
from jobintel.schemas import StrictModel


class AnalyticsInput(StrictModel):
    applied: bool | None = None
    remote: bool | None = None
    profile_id: str | None = None
    profile_revision_id: str | None = None

    @model_validator(mode="after")
    def paired_revision(self):
        if (self.profile_id is None) != (self.profile_revision_id is None):
            raise ValueError("select both profile_id and profile_revision_id")
        return self


BUCKETS = (
    "successful",
    "successfully_empty",
    "pending_source",
    "pending_extraction",
    "acquisition_failed",
    "extraction_failed",
    "stale",
)


def coverage_bucket(view, acquisition, extraction, historical_jobs):
    if view["extraction"] is not None:
        return "successful" if view["extraction"]["requirements"] else "successfully_empty"
    if view["snapshot"] is None:
        return "acquisition_failed" if acquisition else "pending_source"
    if extraction:
        return "extraction_failed"
    return "stale" if view["job_id"] in historical_jobs else "pending_extraction"


def latest_acquisition(session, job_ids):
    model = db.AcquisitionAttempt
    ranked = (
        select(
            model.id,
            func.row_number()
            .over(
                partition_by=model.job_id,
                order_by=(
                    func.coalesce(model.recorded_at, model.created_at).desc(),
                    model.sequence.desc(),
                    model.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(model.job_id.in_(job_ids))
        .subquery()
    )
    return session.scalars(
        select(model).join(ranked, model.id == ranked.c.id).where(ranked.c.position == 1)
    ).all()


class AnalyticsService:
    def __init__(self, session):
        self.session = session
        self.exporter = ExportService(session)

    def report(self, request):
        selection = ExportInput(**request.model_dump())
        report = self.exporter.export(selection)
        return {
            **report,
            "analytics_schema_version": 1,
            "coverage": self.coverage(report["jobs"], report["matched_jobs_N"]),
        }

    def coverage(self, views, matched_N):
        job_ids = [v["job_id"] for v in views]
        acquisition = {
            a.job_id for a in latest_acquisition(self.session, job_ids) if a.status == "failed"
        }
        extraction = {
            a.snapshot_id
            for a in latest_rows(
                self.session,
                db.ExtractionAttempt,
                db.ExtractionAttempt.snapshot_id,
                [v["snapshot"]["id"] for v in views if v["snapshot"]],
            )
            if a.status == "failed"
        }
        historical_jobs = set(
            self.session.scalars(
                select(db.Snapshot.job_id)
                .join(db.ExtractionRun, db.ExtractionRun.snapshot_id == db.Snapshot.id)
                .where(db.Snapshot.job_id.in_(job_ids))
                .distinct()
            )
        )
        buckets = Counter(dict.fromkeys(BUCKETS, 0))
        counts = Counter()
        for view in views:
            failed = bool(view["snapshot"] and view["snapshot"]["id"] in extraction)
            buckets[
                coverage_bucket(view, view["job_id"] in acquisition, failed, historical_jobs)
            ] += 1
            counts["latest_acquisition_failed"] += view["job_id"] in acquisition
            counts["latest_extraction_failed"] += failed
        total = self.session.scalar(select(func.count()).select_from(db.Job))
        N = buckets["successful"] + buckets["successfully_empty"]
        return {
            "registered_total": total,
            "registered_selected": len(views),
            "excluded": total - len(views),
            "buckets": dict(buckets),
            "pending": buckets["pending_source"] + buckets["pending_extraction"],
            "failed": buckets["acquisition_failed"] + buckets["extraction_failed"],
            "stale": buckets["stale"],
            "successful_N": N,
            "matched_N": matched_N,
            "unmatched": N - matched_N,
            "latest_acquisition_failed": counts["latest_acquisition_failed"],
            "latest_extraction_failed": counts["latest_extraction_failed"],
            "success_fraction": N / len(views) if views else None,
            "matched_fraction": matched_N / N if N else None,
        }
