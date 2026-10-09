import os
from pathlib import Path


def database_url() -> str:
    return os.getenv("JOBINTEL_DATABASE_URL", "sqlite:///./local_data/jobintel.db")


def fixture_root() -> Path:
    # CLI/API working directory is the repository root (or /app in Docker).
    return Path(os.getenv("JOBINTEL_FIXTURE_ROOT", "data"))


def openai_key() -> str:
    """Accept a runtime environment key or a mounted secret, never both ambiguously."""
    value, filename = os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_API_KEY_FILE", "")
    if value.strip() and filename:
        raise ValueError("select only OPENAI_API_KEY or OPENAI_API_KEY_FILE")
    if filename:
        try:
            value = Path(filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise ValueError("OPENAI_API_KEY_FILE must be a readable UTF-8 secret file") from None
    if not value.strip():
        raise ValueError("OPENAI_API_KEY or OPENAI_API_KEY_FILE is required for OpenAI")
    return value.strip()
