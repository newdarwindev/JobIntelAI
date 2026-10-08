import os
from pathlib import Path


def database_url() -> str:
    return os.getenv("JOBINTEL_DATABASE_URL", "sqlite:///./local_data/jobintel.db")


def fixture_root() -> Path:
    # CLI/API working directory is the repository root (or /app in Docker).
    return Path(os.getenv("JOBINTEL_FIXTURE_ROOT", "data"))
