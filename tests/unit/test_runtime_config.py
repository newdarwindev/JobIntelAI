"""Runtime boundaries: mounted secrets, explicit providers and scoped data reset."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jobintel.config import openai_key
from jobintel.experiment_cli import selected_experiment_provider

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("runtime_driver", ROOT / "scripts/runtime.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def test_secret_file_and_environment_selection_never_exposes_content(tmp_path, monkeypatch):
    secret = tmp_path / "secret"
    secret.write_text("  synthetic-runtime-secret\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    assert openai_key() == "synthetic-runtime-secret"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-secret")
    with pytest.raises(ValueError, match="select only") as caught:
        openai_key()
    assert "synthetic-" not in str(caught.value)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret.write_bytes(b"\xffprivate-body")
    with pytest.raises(ValueError, match="UTF-8") as caught:
        openai_key()
    assert "private-body" not in str(caught.value)
    secret.unlink()
    with pytest.raises(ValueError, match="readable"):
        openai_key()


@pytest.mark.parametrize("content", ["", "  \n"])
def test_empty_secret_file_fails_before_provider_requests(tmp_path, monkeypatch, content):
    secret = tmp_path / "secret"
    secret.write_text(content)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    with pytest.raises(ValueError, match="required"):
        openai_key()


@pytest.mark.parametrize(
    "mode,environment,expected",
    [
        ("openai", {}, "JOBINTEL_OPENAI_MODEL"),
        ("openai", {"JOBINTEL_OPENAI_MODEL": "synthetic"}, "JOBINTEL_OPENAI_KEY_FILE"),
        ("dev", {"JOBINTEL_PROVIDER": "openai"}, "--mode openai"),
        ("contract-test", {}, "#23/#25"),
        ("local-inference", {}, "#24"),
    ],
)
def test_missing_runtime_prerequisite_never_starts_docker(mode, environment, expected, monkeypatch):
    monkeypatch.setattr(
        driver.subprocess, "run", lambda *_args, **_kw: pytest.fail("Docker invoked")
    )
    with pytest.raises(ValueError, match=expected):
        driver.provider_environment(mode, environment)


def test_demo_never_inherits_live_provider_configuration():
    environment = {"JOBINTEL_PROVIDER": "openai", "JOBINTEL_CONFIGURATION": "openai_structured_v1"}
    selected = driver.provider_environment("demo", environment)
    assert (selected["JOBINTEL_PROVIDER"], selected["JOBINTEL_CONFIGURATION"]) == (
        "fixture",
        "fixture_normalized",
    )


def test_reset_without_explicit_project_cannot_delete_any_volumes(monkeypatch):
    monkeypatch.setattr(
        driver.subprocess, "run", lambda *_args, **_kw: pytest.fail("Docker invoked")
    )
    with pytest.raises(ValueError, match="explicit --project"):
        driver.execute(SimpleNamespace(action="reset", explicit_project=False))


def test_stop_does_not_require_prior_secrets_or_remove_persistent_volumes(monkeypatch):
    calls = []
    monkeypatch.setattr(driver.subprocess, "run", lambda args, **_kw: calls.append(args))
    args = SimpleNamespace(action="stop", project="jobintel-isolated", explicit_project=True)
    driver.execute(args)
    assert calls[0][-1] == "down"
    assert "--volumes" not in calls[0]
    assert "docker-compose.openai.yml" not in calls[0]
    assert calls[0][calls[0].index("--project-name") + 1] == "jobintel-isolated"


def test_cli_rejects_unscoped_project_before_invoking_docker():
    result = subprocess.run(
        [sys.executable, "scripts/runtime.py", "reset", "--project", "unrelated"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--project must begin with jobintel-" in result.stderr


def test_experiment_uses_the_same_mounted_secret_without_an_upstream_request(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_text("synthetic-experiment-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(key))
    provider = selected_experiment_provider("openai", None)
    assert provider.mode == "live"
    assert provider.transport._api_key == "synthetic-experiment-key"


def test_empty_settings_use_compose_defaults_and_custom_password_is_url_encoded(monkeypatch):
    monkeypatch.setenv("JOBINTEL_PROVIDER", "fixture")
    monkeypatch.delenv("JOBINTEL_CONFIGURATION", raising=False)
    monkeypatch.setenv("JOBINTEL_COMPOSE_DATABASE_URL", "")
    monkeypatch.setenv("JOBINTEL_POSTGRES_PASSWORD", "")
    args = SimpleNamespace(mode="dev", port=18080, ca_bundle=None)
    assert (
        ":local-demo-only@db/" in driver.compose_environment(args)["JOBINTEL_COMPOSE_DATABASE_URL"]
    )
    monkeypatch.setenv("JOBINTEL_POSTGRES_PASSWORD", "synthetic@:/ password")
    url = driver.compose_environment(args)["JOBINTEL_COMPOSE_DATABASE_URL"]
    assert "synthetic%40%3A%2F%20password@db" in url


def test_runtime_smoke_refuses_stopped_projects_with_saved_volumes(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "runtime_smoke", ROOT / "scripts/runtime_smoke.py"
    )
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    calls = []

    def existing_volume(command, **_kw):
        calls.append(command)
        return SimpleNamespace(stdout="saved-volume\n" if command[1] == "volume" else "")

    monkeypatch.setattr(smoke.subprocess, "run", existing_volume)
    with pytest.raises(SystemExit, match="unused projects"):
        smoke.require_fresh_projects("jobintel-existing")
    assert all("rm" not in command and "down" not in command for command in calls)
