from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, Text, create_engine
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
    created_at: Mapped[str] = mapped_column(String(40), default=now)
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


class MatchRow(Base):
    __tablename__ = "matches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
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
    engine = create_engine(url)
    # Enforce foreign keys in SQLite as PostgreSQL does by default.
    if engine.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return sessionmaker(engine, expire_on_commit=False)
