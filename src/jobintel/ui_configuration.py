"""Public UI capabilities derived from the configured provider, never credentials."""

from jobintel.provider_config import CONFIGURATIONS
from jobintel.provider_execution import execution_mode, execution_status

LABELS = {
    "fixture": "Fixture replay",
    "emulator": "Responses contract emulator",
    "local-inference": "Local CPU inference",
    "hosted": "Hosted OpenAI",
}


def ui_configuration(app):
    provider = app.state.provider
    mode = execution_mode(provider)
    status = execution_status(provider)
    demo = app.state.demo
    timeout = getattr(getattr(provider, "transport", None), "timeout", 0)
    extract_timeout = max(20, 2 * timeout + 10)
    return {
        "contract_version": 1,
        "demo": demo,
        "provider": provider.name,
        "execution_mode": mode,
        "execution_label": LABELS[mode],
        "live_llm": status["live_llm"],
        "model": getattr(provider, "model", None),
        "readiness": "unverified"
        if mode == "hosted"
        else "ready"
        if status["provider_ready"]
        else "unavailable",
        "default_configuration": app.state.configuration,
        "configurations": [
            {
                "id": name,
                "label": "Normalized aliases" if policy.normalize else "Raw aliases",
                "normalize": policy.normalize,
            }
            for name, policy in CONFIGURATIONS.items()
            if policy.provider == provider.name
        ],
        "request_limits": {
            "extraction_seconds": extract_timeout,
            "evaluation_seconds": max(20, extract_timeout * 50 + 10) if mode != "fixture" else 20,
        },
        "actions": {
            "samples": demo,
            "reset": demo,
            "extract": status["provider_ready"],
            "evaluate": status["provider_ready"],
        },
        "acquisition_mode": getattr(app.state, "acquisition_mode", "synthetic" if demo else "http"),
    }
