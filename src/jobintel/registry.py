import csv
import io
from urllib.parse import urlsplit, urlunsplit

from jobintel.schemas import JobInput


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("official URL must be HTTP(S), without user credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("only standard HTTP(S) ports are supported")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "https" and port == 443)
        or (parsed.scheme.lower() == "http" and port == 80)
    ):
        host += f":{port}"
    # Preserve path case, trailing slashes and query parameters: these may be meaningful.
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, ""))


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
