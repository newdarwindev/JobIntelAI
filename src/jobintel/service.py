import json
from datetime import date
from hashlib import sha256

from sqlalchemy import select

from jobintel import db
from jobintel.analytics import skill_counts
from jobintel.candidate_matching import match_filters
from jobintel.compatibility import stored_extraction, stored_requirement
from jobintel.config import fixture_root
from jobintel.matching import match_requirement
from jobintel.normalization import Taxonomy
from jobintel.providers import extract_result
from jobintel.registry import identity, normalize_url
from jobintel.schemas import CandidateProfile, Extraction, JobInput, MatchSelection, SnapshotInput
from jobintel.snapshots import clean_text, content_hash, validate_grounding


class Conflict(ValueError):
    pass


class Service:
    def __init__(self, session, provider, taxonomy=None):
        self.session = session
        self.provider = provider
        self.taxonomy = taxonomy or Taxonomy(fixture_root() / "taxonomy.json")

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
        result = extract_result(self.provider, snapshot.clean_text, configuration)
        extraction = result.extraction
        # The persistence boundary revalidates even a replaceable/misbehaving provider.
        payload = (
            extraction.model_dump(mode="json") if hasattr(extraction, "model_dump") else extraction
        )
        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
            raise ValueError("providers must return extraction schema v2")
        extraction = Extraction.model_validate(payload)
        validate_grounding(snapshot.clean_text, extraction)
        self.validate_version_products(extraction)
        run = db.ExtractionRun(
            snapshot_id=snapshot.id,
            configuration=configuration,
            schema_version=extraction.schema_version,
            provenance=result.provenance,
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
            "provenance": run.provenance,
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
            "extraction": None if run is None else self.run_output(run),
        }

    @staticmethod
    def candidate_output(candidate):
        profile = CandidateProfile.model_validate(candidate.payload).model_dump(mode="json")
        encoded = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "profile_id": candidate.profile_id,
            "profile_revision_id": candidate.id,
            "content_hash": sha256(encoded.encode()).hexdigest(),
            "created_at": candidate.created_at,
            "profile": profile,
        }

    def import_candidate(self, profile: CandidateProfile):
        payload = profile.model_dump(mode="json")
        existing = self.session.scalars(
            select(db.CandidateEvidenceRow).where(
                db.CandidateEvidenceRow.profile_id == profile.profile_id
            )
        )
        for candidate in existing:
            if (
                CandidateProfile.model_validate(candidate.payload).model_dump(mode="json")
                == payload
            ):
                return self.candidate_output(candidate)
        candidate = db.CandidateEvidenceRow(profile_id=profile.profile_id, payload=payload)
        self.session.add(candidate)
        self.session.flush()
        return self.candidate_output(candidate)

    def candidate(self, profile_id, revision_id):
        candidate = self.session.get(db.CandidateEvidenceRow, revision_id)
        if candidate is None or candidate.profile_id != profile_id:
            raise KeyError(revision_id)
        return self.candidate_output(candidate)

    def candidate_revisions(self, profile_id):
        revisions = self.session.scalars(
            select(db.CandidateEvidenceRow)
            .where(db.CandidateEvidenceRow.profile_id == profile_id)
            .order_by(db.CandidateEvidenceRow.created_at.desc(), db.CandidateEvidenceRow.id.desc())
        )
        return {
            "profile_id": profile_id,
            "revisions": [self.candidate_output(r) for r in revisions],
        }

    def match(self, job_id: str, selection: CandidateProfile | MatchSelection):
        snapshot = self.latest_snapshot(job_id)
        run = self.latest_run(snapshot.id) if snapshot else None
        if run is None:
            raise Conflict("extract the latest snapshot before matching")
        if isinstance(selection, MatchSelection):
            if selection.expected_run_id != run.id:
                raise Conflict("extraction selection is stale; reload and select the current run")
            candidate = self.candidate(selection.profile_id, selection.profile_revision_id)
            as_of = selection.as_of
        else:
            candidate = self.import_candidate(selection)
            as_of = date.today()
        profile = CandidateProfile.model_validate(candidate["profile"])
        match_run = db.MatchRun(
            extraction_run_id=run.id,
            snapshot_id=snapshot.id,
            profile_revision_id=candidate["profile_revision_id"],
            payload={},
        )
        self.session.add(match_run)
        self.session.flush()
        eligibility = match_filters(stored_extraction(run.payload), profile, as_of)
        results = self.match_rows(run, candidate, profile, match_run.id, as_of, eligibility)
        output = {
            "match_run_id": match_run.id,
            "profile_id": profile.profile_id,
            "profile_revision_id": candidate["profile_revision_id"],
            "profile_content_hash": candidate["content_hash"],
            "run_id": run.id,
            "snapshot_id": snapshot.id,
            "content_hash": snapshot.content_hash,
            "as_of": as_of.isoformat(),
            "created_at": match_run.created_at,
            "matches": results,
            "eligibility": eligibility,
        }
        match_run.payload = output
        self.session.flush()
        return output

    def match_rows(self, run, candidate, profile, match_run_id, as_of, eligibility):
        results = []
        rows = self.session.scalars(
            select(db.RequirementRow).where(db.RequirementRow.run_id == run.id)
        ).all()
        rows.sort(key=lambda row: run.payload["requirements"].index(row.payload))
        for row in rows:
            result = match_requirement(
                stored_requirement(row.payload, run.schema_version),
                profile,
                self.taxonomy,
                as_of,
                eligibility,
            )
            result["requirement_id"] = row.id
            self.session.add(
                db.MatchRow(
                    match_run_id=match_run_id,
                    requirement_id=row.id,
                    candidate_evidence_id=candidate["profile_revision_id"],
                    payload=result,
                )
            )
            results.append(result)
        return results

    def match_run(self, match_run_id):
        run = self.session.get(db.MatchRun, match_run_id)
        if run is None:
            raise KeyError(match_run_id)
        return run.payload

    def list_jobs(self):
        return [
            self.get_job(job_id)
            for job_id in self.session.scalars(select(db.Job.job_id).order_by(db.Job.job_id))
        ]

    def history(self, job_id):
        self.job(job_id)
        snapshots = self.session.scalars(
            select(db.Snapshot)
            .where(db.Snapshot.job_id == job_id)
            .order_by(db.Snapshot.fetched_at.desc(), db.Snapshot.id.desc())
        )
        return {
            "job_id": job_id,
            "snapshots": [
                {
                    "id": snapshot.id,
                    "content_hash": snapshot.content_hash,
                    "clean_text": snapshot.clean_text,
                    "fetched_at": snapshot.fetched_at,
                    "source_url": snapshot.source_url,
                    "runs": [
                        {
                            "run_id": run.id,
                            "configuration": run.configuration,
                            "created_at": run.created_at,
                            **self.run_output(run),
                        }
                        for run in self.session.scalars(
                            select(db.ExtractionRun)
                            .where(db.ExtractionRun.snapshot_id == snapshot.id)
                            .order_by(
                                db.ExtractionRun.created_at.desc(), db.ExtractionRun.id.desc()
                            )
                        )
                    ],
                }
                for snapshot in snapshots
            ],
        }

    @staticmethod
    def run_output(run):
        if run.payload.get("schema_version", 1) != run.schema_version:
            raise ValueError("stored extraction schema version mismatch")
        return {
            "run_id": run.id,
            "configuration": run.configuration,
            "stored_schema_version": run.schema_version,
            "provenance": run.provenance,
            **stored_extraction(run.payload).model_dump(mode="json"),
        }

    def validate_version_products(self, extraction):
        taxonomy = self.taxonomy
        for requirement in extraction.requirements:
            for version in requirement.version_constraints:
                canonical = (
                    taxonomy.canonical(version.source_product)
                    if taxonomy
                    else version.source_product
                )
                if version.product not in {version.source_product, canonical}:
                    raise ValueError("version product differs from the sourced taxonomy product")

    def analytics(self, applied=None):
        jobs = []
        for job_id in self.session.scalars(select(db.Job.job_id).order_by(db.Job.job_id)):
            item = self.get_job(job_id)
            if applied is not None and item["applied"] is not applied:
                continue
            if item["extraction"] is not None:
                jobs.append({"job_id": job_id, "requirements": item["extraction"]["requirements"]})
        return skill_counts(jobs)

    def seed_taxonomy(self):
        for record in self.taxonomy.records:
            if self.session.get(db.Skill, record["canonical"]) is None:
                self.session.add(db.Skill(canonical=record["canonical"], payload=record))
