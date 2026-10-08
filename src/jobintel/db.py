from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def new_id() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity: Mapped[str] = mapped_column(String(500), unique=True)
    official_url: Mapped[str | None] = mapped_column(Text, unique=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Snapshot(Base):
    __tablename__ = "posting_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[str] = mapped_column(String(40), default=now)
    raw_text: Mapped[str] = mapped_column(Text)
    clean_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    fetch_status: Mapped[str] = mapped_column(String(32), default="manual")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("posting_snapshots.id"), index=True)
    configuration: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=2, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


class AcquisitionAttempt(Base):
    __tablename__ = "acquisition_attempts"
    __table_args__ = (
        UniqueConstraint("fetch_id", "sequence", name="uq_acquisition_fetch_sequence"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("posting_snapshots.id"), nullable=True
    )
    fetch_id: Mapped[str] = mapped_column(String(32), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    original_url: Mapped[str] = mapped_column(Text)
    requested_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSON)


class RequirementRow(Base):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Skill(Base):
    __tablename__ = "skills"
    canonical: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class CandidateEvidenceRow(Base):
    __tablename__ = "candidate_evidence"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


class MatchRun(Base):
    __tablename__ = "match_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    extraction_run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("posting_snapshots.id"))
    profile_revision_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_evidence.id"), index=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


class MatchRow(Base):
    __tablename__ = "matches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    match_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("match_runs.id"), index=True, nullable=True
    )
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), index=True)
    candidate_evidence_id: Mapped[str] = mapped_column(ForeignKey("candidate_evidence.id"))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


def session_factory(url: str):
    engine = create_engine(url, hide_parameters=True)
    # Enforce foreign keys in SQLite as PostgreSQL does by default.
    if engine.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return sessionmaker(engine, expire_on_commit=False)
