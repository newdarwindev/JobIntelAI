"""Browser service ownership must override private runtime DB/provider settings."""

from types import SimpleNamespace

import pytest

from scripts import browser_services


@pytest.mark.parametrize("mode", ["fixture", "emulator"])
def test_normal_browser_api_owns_database_and_never_inherits_hosted_provider(
    monkeypatch, tmp_path, mode
):
    monkeypatch.setenv("JOBINTEL_COMPOSE_DATABASE_URL", "postgresql://private.invalid/private")
    monkeypatch.setenv("JOBINTEL_POSTGRES_PASSWORD", "authored-private-password")
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_CONFIGURATION", "incompatible-private-setting")
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setattr(browser_services, "require_fresh_projects", lambda *_args: None)
    calls = []

    def command(args, *arguments, **_kwargs):
        calls.append((args, arguments))
        assert args.environment["JOBINTEL_COMPOSE_DATABASE_URL"] == (
            "postgresql+psycopg://jobintel:browser-only@db/jobintel"
        )
        assert args.environment["JOBINTEL_POSTGRES_PASSWORD"] == "browser-only"
        assert args.environment["JOBINTEL_PROVIDER"] == (
            "fixture" if mode == "fixture" else "openai"
        )
        if mode == "emulator":
            assert args.environment["JOBINTEL_RESPONSES_MODE"] == "emulator"
        return SimpleNamespace(stdout="127.0.0.1:18181\n")

    monkeypatch.setattr(browser_services, "command", command)
    fixtures = {"ca": tmp_path / "ca.pem", "project": "jobintel-authored-gateway"}
    with browser_services.normal_api(mode, fixtures) as service:
        assert service["demo"] is False
        project = service["project"]
    assert calls[-1][1] == ("down", "--volumes")
    assert all(call[0].project == project for call in calls)
    assert calls[0][1][:2] == ("up", "-d")


def test_failed_browser_startup_still_removes_only_its_new_project(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBINTEL_PROVIDER", "fixture")
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setattr(browser_services, "require_fresh_projects", lambda *_args: None)
    calls = []

    def command(args, *arguments, **_kwargs):
        calls.append((args.project, arguments))
        if arguments[0] == "up":
            raise RuntimeError("authored startup failure")

    monkeypatch.setattr(browser_services, "command", command)
    fixtures = {"ca": tmp_path / "ca.pem", "project": "jobintel-authored-gateway"}
    with pytest.raises(RuntimeError, match="startup failure"):
        with browser_services.normal_api("fixture", fixtures):
            pytest.fail("failed service yielded")
    assert calls[1] == (calls[0][0], ("down", "--volumes"))
