import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobintel.api import create_app
from jobintel.normalization import Taxonomy
from jobintel.providers import FixtureProvider
from jobintel.schemas import Extraction

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.fixture
def taxonomy():
    return Taxonomy(DATA / "taxonomy.json")


@pytest.fixture
def provider():
    return FixtureProvider(DATA)


@pytest.fixture
def requirement():
    record = json.loads((DATA / "golden_dataset.json").read_text())[0]
    return Extraction.model_validate(record["extraction"]).requirements[0]


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("JOBINTEL_DATABASE_URL", url)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    with TestClient(create_app(url, DATA)) as client:
        yield client
