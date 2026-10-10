import csv
import io

from jobintel.schemas import JobInput
from jobintel.url_identity import normalize_url as normalize_url


def identity(job: JobInput) -> str:
    return "|".join(v.strip().casefold() for v in [job.company, job.role])


def parse_csv(value: str) -> list[JobInput]:
    reader = csv.DictReader(io.StringIO(value))
    if not {"job_id", "company", "role"}.issubset(reader.fieldnames or []):
        raise ValueError("CSV requires job_id, company, role headers")
    jobs = []
    for row in reader:
        applied = row.get("applied", "").strip().lower()
        if applied not in {"", "true", "false"}:
            raise ValueError("applied must be true, false, or empty")
        jobs.append(
            JobInput(
                job_id=row["job_id"],
                company=row["company"].strip(),
                role=row["role"].strip(),
                official_url=row.get("official_url") or None,
                status=row.get("status") or None,
                applied=None if not applied else applied == "true",
            )
        )
    return jobs
