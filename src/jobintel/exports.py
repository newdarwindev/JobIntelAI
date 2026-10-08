"""Read-only exports with immutable row provenance and spreadsheet-neutralized CSV."""

import csv
import io
import json
import unicodedata
from hashlib import sha256

from sqlalchemy import func, select

from jobintel import db
from jobintel.analytics import skill_counts
from jobintel.compatibility import stored_requirement
from jobintel.export_selection import ExportInput
from jobintel.service import Service

SKILL_COLUMNS = ["skill", "N", "n", "must_n", "preferred_n", "experience_n", "other_n"]
SKILL_PROVENANCE = [
    "applied_slice",
    "historical",
    "denominator",
    "job_ids",
    "snapshot_ids",
    "run_ids",
    "source_hashes",
    "configurations",
    "profile_id",
    "profile_revision_id",
]
REQUIREMENT_COLUMNS = [
    "job_id",
    "company",
    "role",
    "official_url",
    "applied",
    "snapshot_id",
    "source_url",
    "content_hash",
    "raw_source_sha256",
    "fetched_at",
    "run_id",
    "configuration",
    "schema_version",
    "provenance",
    "requirement_id",
    "raw_text",
    "normalized_skill_or_requirement",
    "skills",
    "source_skills",
    "operator",
    "requirement_type",
    "category",
    "experience_obligation",
    "production_obligation",
    "explicit_production_required",
    "years_required",
    "version_constraints",
    "confidence",
    "notes",
    "evidence_quote",
    "evidence_start",
    "evidence_end",
    "match_run_id",
    "match_id",
    "profile_id",
    "profile_revision_id",
    "profile_content_hash",
    "match_status",
    "candidate_sources",
    "branches",
    "explanation",
    "as_of",
    "eligibility",
    "N",
    "matched_jobs_N",
    "applied_slice",
    "historical",
    "denominator",
    "selected_profile_id",
    "selected_profile_revision_id",
]


def spreadsheet_cell(value):
    if isinstance(value, (dict, list, bool)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = "" if value is None else str(value)
    visible = text.lstrip()
    while visible and (visible[0].isspace() or unicodedata.category(visible[0]) in {"Cc", "Cf"}):
        visible = visible[1:]
    return "'" + text if visible.startswith(("=", "+", "-", "@")) else text


def csv_text(rows, columns):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        extrasaction="ignore",
        quoting=csv.QUOTE_ALL,
        lineterminator="\r\n",
    )
    writer.writeheader()
    writer.writerows({key: spreadsheet_cell(row.get(key)) for key in columns} for row in rows)
    return output.getvalue()


def latest_rows(session, model, parent, identifiers, predicates=()):
    timestamp = model.fetched_at if model is db.Snapshot else model.created_at
    ranked = (
        select(
            model.id,
            func.row_number()
            .over(partition_by=parent, order_by=(timestamp.desc(), model.id.desc()))
            .label("position"),
        )
        .where(parent.in_(identifiers), *predicates)
        .subquery()
    )
    return session.scalars(
        select(model).join(ranked, model.id == ranked.c.id).where(ranked.c.position == 1)
    ).all()


def exact_rows(session, model, identifiers):
    rows = session.scalars(select(model).where(model.id.in_(identifiers))).all()
    if {row.id for row in rows} != set(identifiers):
        raise KeyError("selected export row not found")
    return rows


class ExportService:
    def __init__(self, session):
        self.session = session

    def selection(self, request):
        jobs = self.session.scalars(select(db.Job).order_by(db.Job.job_id)).all()
        if not set(request.job_ids) <= {job.job_id for job in jobs}:
            raise KeyError("selected job not found")
        jobs = [
            job
            for job in jobs
            if (not request.job_ids or job.job_id in request.job_ids)
            and (request.applied is None or job.payload.get("applied") is request.applied)
        ]
        if request.profile_revision_id:
            profile = self.session.get(db.CandidateEvidenceRow, request.profile_revision_id)
            if profile is None or profile.profile_id != request.profile_id:
                raise KeyError("selected candidate revision not found")
        if request.historical:
            matches = exact_rows(self.session, db.MatchRun, request.match_run_ids)
            run_ids = set(request.run_ids) | {match.extraction_run_id for match in matches}
            runs = exact_rows(self.session, db.ExtractionRun, run_ids)
            snapshots = exact_rows(self.session, db.Snapshot, {run.snapshot_id for run in runs})
            selected_jobs = {snapshot.job_id for snapshot in snapshots}
            jobs = [job for job in jobs if job.job_id in selected_jobs]
        else:
            matches = []
            snapshots = latest_rows(
                self.session, db.Snapshot, db.Snapshot.job_id, [job.job_id for job in jobs]
            )
            runs = latest_rows(
                self.session,
                db.ExtractionRun,
                db.ExtractionRun.snapshot_id,
                [row.id for row in snapshots],
            )
        snapshots = {row.id: row for row in snapshots if row.job_id in {job.job_id for job in jobs}}
        runs = {run.id: run for run in runs if run.snapshot_id in snapshots}
        if not request.match_run_ids and request.profile_revision_id:
            matches = latest_rows(
                self.session,
                db.MatchRun,
                db.MatchRun.extraction_run_id,
                list(runs),
                [db.MatchRun.profile_revision_id == request.profile_revision_id],
            )
        self.validate_matches(request, matches, runs)
        return (
            jobs,
            snapshots,
            runs,
            [match for match in matches if match.extraction_run_id in runs],
        )

    @staticmethod
    def validate_matches(request, matches, runs):
        for match in matches:
            if (
                request.profile_revision_id
                and match.profile_revision_id != request.profile_revision_id
            ):
                raise ValueError("match run differs from the selected candidate revision")
            if (
                match.extraction_run_id in runs
                and match.snapshot_id != runs[match.extraction_run_id].snapshot_id
            ):
                raise ValueError("stored match/source provenance differs")

    def records(self, jobs, snapshots, runs, matches):
        jobs_by_id = {job.job_id: job for job in jobs}
        matches_by_id = {match.id: match for match in matches}
        candidates = {
            row.id: Service.candidate_output(row)
            for row in self.session.scalars(
                select(db.CandidateEvidenceRow).where(
                    db.CandidateEvidenceRow.id.in_({m.profile_revision_id for m in matches})
                )
            )
        }
        matched = {}
        for row in self.session.scalars(
            select(db.MatchRow)
            .where(db.MatchRow.match_run_id.in_(matches_by_id))
            .order_by(db.MatchRow.match_run_id, db.MatchRow.id)
        ):
            match = matches_by_id[row.match_run_id]
            if row.candidate_evidence_id != match.profile_revision_id:
                raise ValueError("stored match/candidate provenance differs")
            matched.setdefault(row.requirement_id, []).append(
                (row, match, candidates[match.profile_revision_id])
            )
        rows = []
        for row in self.session.scalars(
            select(db.RequirementRow)
            .where(db.RequirementRow.run_id.in_(runs))
            .order_by(db.RequirementRow.id)
        ):
            run = runs[row.run_id]
            if row.payload not in run.payload["requirements"]:
                raise ValueError("stored requirement/run provenance differs")
            snapshot = snapshots[run.snapshot_id]
            base = requirement_record(jobs_by_id[snapshot.job_id], snapshot, run, row)
            linked = matched.get(row.id, [])
            for match_row, match, candidate in linked or [(None, None, None)]:
                if match is not None and match.extraction_run_id != run.id:
                    raise ValueError("stored match/requirement provenance differs")
                rows.append({**base, **match_record(match_row, match, candidate)})
        return rows

    def export(self, request: ExportInput):
        jobs, snapshots, runs, matches = self.selection(request)
        rows = self.records(jobs, snapshots, runs, matches)
        views = job_views(jobs, snapshots, runs)
        eligible = [job for job in views if job["extraction"] is not None]
        report = skill_counts(distinct_job_requirements(eligible))
        matched_jobs = {snapshots[m.snapshot_id].job_id for m in matches}
        selected = request.model_dump(exclude={"format", "legacy_skills_csv", "kind"})
        metadata = {
            "export_schema_version": 1,
            "kind": request.kind,
            "selection": selected,
            "N": report["N"],
            "matched_jobs_N": len(matched_jobs),
            "denominator": "distinct jobs with successful selected-source extraction",
            "registered_jobs_N": len({job.job_id for job in jobs}),
            "jobs": views,
        }
        candidate_ids = {match.profile_revision_id for match in matches}
        if request.profile_revision_id:
            candidate_ids.add(request.profile_revision_id)
        profiles = [
            Service.candidate_output(row)
            for row in self.session.scalars(
                select(db.CandidateEvidenceRow)
                .where(db.CandidateEvidenceRow.id.in_(candidate_ids))
                .order_by(db.CandidateEvidenceRow.id)
            )
        ]
        metadata["profiles"] = profiles
        if request.kind == "skills":
            result = {
                **report,
                **metadata,
                **corpus_summaries(eligible, rows, len(matched_jobs)),
                "scope": "Selected source runs in the loaded corpus; counts are distinct jobs.",
            }
        else:
            selected_rows = [
                row for row in rows if request.kind != "matches" or row["match_run_id"] is not None
            ]
            result = {
                **metadata,
                "rows": selected_rows,
                "match_runs": [match.payload for match in sorted(matches, key=lambda m: m.id)],
            }
            if request.kind == "evidence":
                if len(views) != 1:
                    raise ValueError("evidence export requires one eligible source/run view")
                result.update(views[0])
            if request.kind == "matches" and len(matches) == 1:
                result.update(matches[0].payload)
                result["profile"] = profiles[0]["profile"]
        if request.format == "json":
            return result
        return render_csv(result, request)


def requirement_record(job, snapshot, run, row):
    requirement = stored_requirement(row.payload, run.schema_version).model_dump(mode="json")
    evidence = requirement["evidence"]
    return {
        **job.payload,
        **requirement,
        "snapshot_id": snapshot.id,
        "source_url": snapshot.source_url,
        "content_hash": snapshot.content_hash,
        "raw_source_sha256": sha256(snapshot.raw_text.encode()).hexdigest(),
        "fetched_at": snapshot.fetched_at,
        "run_id": run.id,
        "configuration": run.configuration,
        "schema_version": run.schema_version,
        "provenance": run.provenance,
        "requirement_id": row.id,
        "evidence_quote": evidence["quote"],
        "evidence_start": evidence["start"],
        "evidence_end": evidence["end"],
    }


def match_record(row, run, candidate):
    if row is None:
        return dict.fromkeys(
            [
                "match_run_id",
                "match_id",
                "profile_id",
                "profile_revision_id",
                "profile_content_hash",
                "match_status",
                "candidate_sources",
                "branches",
                "explanation",
                "as_of",
                "eligibility",
            ]
        )
    return {
        "match_run_id": run.id,
        "match_id": row.id,
        "profile_id": candidate["profile_id"],
        "profile_revision_id": candidate["profile_revision_id"],
        "profile_content_hash": candidate["content_hash"],
        "match_status": row.payload["status"],
        "candidate_sources": row.payload.get("candidate_sources", []),
        "branches": row.payload.get("branches", []),
        "explanation": row.payload.get("explanation"),
        "as_of": run.payload.get("as_of"),
        "eligibility": run.payload.get("eligibility"),
    }


def job_views(jobs, snapshots, runs):
    views = []
    by_snapshot = {}
    for run in sorted(runs.values(), key=lambda r: (r.created_at, r.id), reverse=True):
        by_snapshot.setdefault(run.snapshot_id, []).append(run)
    for job in jobs:
        sources = sorted(
            [s for s in snapshots.values() if s.job_id == job.job_id],
            key=lambda s: (s.fetched_at, s.id),
            reverse=True,
        )
        if not sources:
            views.append({**job.payload, "snapshot": None, "extraction": None})
        for source in sources:
            for run in by_snapshot.get(source.id, [None]):
                views.append(
                    {
                        **job.payload,
                        "snapshot": {
                            "id": source.id,
                            "content_hash": source.content_hash,
                            "source_url": source.source_url,
                            "fetched_at": source.fetched_at,
                            "raw_source_sha256": sha256(source.raw_text.encode()).hexdigest(),
                            "clean_text": source.clean_text,
                        },
                        "extraction": Service.run_output(run) if run else None,
                    }
                )
    return views


def distinct_job_requirements(jobs):
    combined = {}
    for job in jobs:
        requirements = combined.setdefault(job["job_id"], {})
        for requirement in job["extraction"]["requirements"]:
            requirements[json.dumps(requirement, sort_keys=True)] = requirement
    return [
        {"job_id": job_id, "requirements": list(requirements.values())}
        for job_id, requirements in sorted(combined.items())
    ]


def corpus_summaries(jobs, rows, matched_N):
    categories = {}
    gaps = {}
    for job in jobs:
        for category in {r["category"] for r in job["extraction"]["requirements"]}:
            categories.setdefault(category, set()).add(job["job_id"])
    for row in rows:
        if row["match_status"] is None:
            continue
        key = (row["normalized_skill_or_requirement"], row["operator"])
        group = gaps.setdefault(
            key, {state: set() for state in ["COVERED", "PARTIAL", "MISSING", "UNKNOWN"]}
        )
        group[row["match_status"]].add(row["job_id"])
    return {
        "clusters": {
            "N": len({job["job_id"] for job in jobs}),
            "clusters": [
                {"category": category, "n": len(ids)}
                for category, ids in sorted(categories.items())
            ],
        },
        "gaps": {
            "N": matched_N,
            "groups": [
                {
                    "requirement": key[0],
                    "operator": key[1],
                    **{state: len(ids) for state, ids in states.items()},
                }
                for key, states in sorted(gaps.items())
            ],
        },
    }


def render_csv(result, request):
    if request.kind != "skills":
        rows = [
            {
                **row,
                "N": result["N"],
                "matched_jobs_N": result["matched_jobs_N"],
                "applied_slice": request.applied,
                "historical": request.historical,
                "denominator": result["denominator"],
                "selected_profile_id": request.profile_id,
                "selected_profile_revision_id": request.profile_revision_id,
            }
            for row in result["rows"]
        ]
        return csv_text(rows, REQUIREMENT_COLUMNS)
    eligible = [job for job in result["jobs"] if job["extraction"]]
    provenance = {
        "applied_slice": request.applied,
        "denominator": result["denominator"],
        "historical": request.historical,
        "profile_id": request.profile_id,
        "profile_revision_id": request.profile_revision_id,
        "job_ids": sorted({job["job_id"] for job in eligible}),
        "snapshot_ids": sorted({job["snapshot"]["id"] for job in eligible}),
        "run_ids": sorted({job["extraction"]["run_id"] for job in eligible}),
        "source_hashes": sorted({job["snapshot"]["content_hash"] for job in eligible}),
        "configurations": sorted({job["extraction"]["configuration"] for job in eligible}),
    }
    columns = SKILL_COLUMNS if request.legacy_skills_csv else SKILL_COLUMNS + SKILL_PROVENANCE
    return csv_text([{**row, **provenance} for row in result["skills"]], columns)
