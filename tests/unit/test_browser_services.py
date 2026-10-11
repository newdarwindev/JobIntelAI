"""Browser service ownership must override private runtime DB/provider settings."""

from types import SimpleNamespace
from typing import ClassVar

import pytest

from scripts import browser_services, environment


class AuthoredLease:
    calls: ClassVar[list] = []

    def __init__(self, project, **_options):
        self.project = project
        self.record = {"expires_at": 123}
        self.path = SimpleNamespace()
        self.collectors = {}

    def __enter__(self):
        return self

    def __exit__(self, _kind, error, _trace):
        self.calls.append((self.project, "cleanup", error))

    def configure(self, _prefix, settings):
        self.environment = settings

    def command(self, *arguments, **_kwargs):
        self.calls.append((self.project, arguments[0], self.environment))
        return SimpleNamespace(stdout="127.0.0.1:18181\n")

    def ready(self, _info):
        pass


@pytest.mark.parametrize("mode", ["fixture", "emulator"])
def test_normal_browser_api_owns_database_and_never_inherits_hosted_provider(
    monkeypatch, tmp_path, mode
):
    monkeypatch.setenv("JOBINTEL_COMPOSE_DATABASE_URL", "postgresql://private.invalid/private")
    monkeypatch.setenv("JOBINTEL_POSTGRES_PASSWORD", "authored-private-password")
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_CONFIGURATION", "incompatible-private-setting")
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setattr(environment, "Lease", AuthoredLease)
    AuthoredLease.calls = []
    fixtures = {
        "ca": tmp_path / "ca.pem",
        "project": "jobintel-authored-gateway",
        "diagnostics": dict,
    }
    with browser_services.normal_api(mode, fixtures) as service:
        assert service["demo"] is False
        project = service["project"]
    assert AuthoredLease.calls[-1] == (project, "cleanup", None)
    assert all(call[0] == project for call in AuthoredLease.calls)
    assert AuthoredLease.calls[0][1] == "up"
    settings = AuthoredLease.calls[0][2]
    assert (
        settings["JOBINTEL_COMPOSE_DATABASE_URL"]
        == "postgresql+psycopg://jobintel:environment-only@db/jobintel"
    )
    assert settings["JOBINTEL_POSTGRES_PASSWORD"] == "environment-only"
    assert settings["JOBINTEL_PROVIDER"] == ("fixture" if mode == "fixture" else "openai")
    assert settings["JOBINTEL_API_PORT"] == "0"
    if mode == "emulator":
        assert settings["JOBINTEL_RESPONSES_MODE"] == "emulator"


def test_failed_browser_startup_still_removes_only_its_new_project(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setattr(environment, "Lease", AuthoredLease)
    AuthoredLease.calls = []

    def command(self, *arguments, **_kwargs):
        AuthoredLease.calls.append((self.project, arguments[0], None))
        raise RuntimeError("authored startup failure")

    monkeypatch.setattr(AuthoredLease, "command", command)
    fixtures = {"ca": tmp_path / "ca.pem", "project": "jobintel-authored-gateway"}
    with pytest.raises(RuntimeError, match="startup failure"):
        with browser_services.normal_api("fixture", fixtures):
            pytest.fail("failed service yielded")
    assert AuthoredLease.calls[1][:2] == (AuthoredLease.calls[0][0], "cleanup")
    assert isinstance(AuthoredLease.calls[1][2], RuntimeError)
