from sqlalchemy import select

from jobintel import db
from jobintel.analytics import skill_counts
from jobintel.matching import match_requirement
from jobintel.registry import identity, normalize_url
from jobintel.schemas import CandidateProfile, Extraction, JobInput, Requirement, SnapshotInput
from jobintel.snapshots import clean_text, content_hash, validate_grounding


class Conflict(ValueError):
    pass


class Service:
    def __init__(self, session, provider):
        self.session = session
        self.provider = provider

    def job(self, job_id: str):
        job = self.session.get(db.Job, job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def import_jobs(self, jobs: list[JobInput]) -> dict:
        imported = duplicate = 0
        for item in jobs:
            item = item.model_copy(update={"official_url": normalize_url(item.official_url)})
            existing = self.session.get(db.Job, item.job_id)
            if existing:
                if existing.payload != item.model_dump():
                    raise Conflict("job_id already exists with different metadata")
                duplicate += 1
                continue
            candidates = self.session.scalars(
                select(db.Job).where(db.Job.identity == identity(item))
            ).all()
            if item.official_url:
                candidates += self.session.scalars(
                    select(db.Job).where(db.Job.official_url == item.official_url)
                ).all()
            if candidates:
                raise Conflict(
                    "duplicate URL or company+role under a different job_id; resolve explicitly"
                )
            self.session.add(
                db.Job(
                    job_id=item.job_id,
                    identity=identity(item),
                    official_url=item.official_url,
                    payload=item.model_dump(),
                )
            )
            self.session.flush()
            imported += 1
        return {"imported": imported, "duplicates": duplicate}

    def latest_snapshot(self, job_id):
        self.job(job_id)
        return self.session.scalar(
            select(db.Snapshot)
            .where(db.Snapshot.job_id == job_id)
            .order_by(db.Snapshot.fetched_at.desc(), db.Snapshot.id.desc())
            .limit(1)
        )

    def snapshot(self, job_id: str, item: SnapshotInput):
        job = self.job(job_id)
        text = clean_text(item.text, item.format == "html")
        if not text:
            raise ValueError("snapshot is empty after cleaning")
        source_url = normalize_url(item.source_url) if item.source_url else job.official_url
        latest = self.latest_snapshot(job_id)
        if (
            latest
            and latest.raw_text == item.text
            and latest.source_url == source_url
            and latest.clean_text == text
        ):
            return latest
        snapshot = db.Snapshot(
            job_id=job_id,
            source_url=source_url,
            raw_text=item.text,
            clean_text=text,
            content_hash=content_hash(text),
            fetch_status="manual",
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def latest_run(self, snapshot_id):
        return self.session.scalar(
            select(db.ExtractionRun)
            .where(db.ExtractionRun.snapshot_id == snapshot_id)
            .order_by(db.ExtractionRun.created_at.desc(), db.ExtractionRun.id.desc())
            .limit(1)
        )

    def extract(self, job_id: str, configuration: str):
        snapshot = self.latest_snapshot(job_id)
        if snapshot is None:
            raise Conflict("create a snapshot before extraction")
        extraction = self.provider.extract(snapshot.clean_text, configuration)
        # The persistence boundary revalidates even a replaceable/misbehaving provider.
        extraction = Extraction.model_validate(extraction.model_dump(mode="json"))
        validate_grounding(snapshot.clean_text, extraction)
        run = db.ExtractionRun(
            snapshot_id=snapshot.id,
            configuration=configuration,
            payload=extraction.model_dump(mode="json"),
        )
        self.session.add(run)
        self.session.flush()
        for requirement in extraction.requirements:
            self.session.add(
                db.RequirementRow(run_id=run.id, payload=requirement.model_dump(mode="json"))
            )
        self.session.flush()
        return {
            "run_id": run.id,
            "snapshot_id": snapshot.id,
            "configuration": configuration,
            **run.payload,
        }

    def get_job(self, job_id: str):
        job = self.job(job_id)
        snapshot = self.latest_snapshot(job_id)
        run = self.latest_run(snapshot.id) if snapshot else None
        return {
            **job.payload,
            "snapshot": None
            if snapshot is None
            else {
                "id": snapshot.id,
                "content_hash": snapshot.content_hash,
                "fetched_at": snapshot.fetched_at,
                "source_url": snapshot.source_url,
                "fetch_status": snapshot.fetch_status,
                "clean_text": snapshot.clean_text,
            },
            "extraction": None
            if run is None
            else {"run_id": run.id, "configuration": run.configuration, **run.payload},
        }

    def match(self, job_id: str, profile: CandidateProfile):
        snapshot = self.latest_snapshot(job_id)
        run = self.latest_run(snapshot.id) if snapshot else None
        if run is None:
            raise Conflict("extract the latest snapshot before matching")
        candidate = db.CandidateEvidenceRow(
            profile_id=profile.profile_id, payload=profile.model_dump()
        )
        self.session.add(candidate)
        self.session.flush()
        results = []
        for row in self.session.scalars(
            select(db.RequirementRow).where(db.RequirementRow.run_id == run.id)
        ):
            result = match_requirement(
                Requirement.model_validate(row.payload), profile, self.provider.taxonomy
            )
            result["requirement_id"] = row.id
            self.session.add(
                db.MatchRow(
                    requirement_id=row.id, candidate_evidence_id=candidate.id, payload=result
                )
            )
            results.append(result)
        return {"profile_id": profile.profile_id, "run_id": run.id, "matches": results}

    def analytics(self):
        jobs = []
        for job_id in self.session.scalars(select(db.Job.job_id).order_by(db.Job.job_id)):
            item = self.get_job(job_id)
            if item["extraction"] is not None:
                jobs.append({"job_id": job_id, "requirements": item["extraction"]["requirements"]})
        return skill_counts(jobs)

    def seed_taxonomy(self):
        for record in self.provider.taxonomy.records:
            if self.session.get(db.Skill, record["canonical"]) is None:
                self.session.add(db.Skill(canonical=record["canonical"], payload=record))
