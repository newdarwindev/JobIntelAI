from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobintel import db
from jobintel.api import create_app
from jobintel.providers import FixtureProvider
from jobintel.schemas import JobInput, SnapshotInput
from jobintel.service import Service
from jobintel.snapshots import GroundingError

DATA = Path(__file__).resolve().parents[2] / "data"


def test_unmigrated_database_is_not_healthy(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'unmigrated.db'}", DATA)) as client:
        assert client.get("/health").status_code == 503


def test_service_revalidates_provider_and_keeps_prior_run(tmp_path):
    factory = db.session_factory(f"sqlite:///{tmp_path / 'unit.db'}")
    db.Base.metadata.create_all(factory.kw["bind"])
    provider = FixtureProvider(DATA)
    text = (DATA / "sample_jobs/SYN-01.txt").read_text()
    with factory.begin() as session:
        service = Service(session, provider)
        service.import_jobs([JobInput(job_id="one", company="Demo", role="Engineer")])
        service.snapshot("one", SnapshotInput(text=text))
        service.extract("one", "fixture_normalized")

    class BadProvider:
        def extract(self, text, configuration):
            result = provider.extract(text, configuration)
            wrong = result.requirements[0].evidence.model_copy(update={"start": 0})
            result.requirements[0] = result.requirements[0].model_copy(update={"evidence": wrong})
            return result

    with pytest.raises(GroundingError):
        with factory.begin() as session:
            Service(session, BadProvider()).extract("one", "fixture_normalized")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(db.ExtractionRun)) == 1
        assert session.scalar(select(func.count()).select_from(db.RequirementRow)) == 2
    factory.kw["bind"].dispose()
