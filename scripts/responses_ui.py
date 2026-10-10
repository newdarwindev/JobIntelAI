"""Test-launcher-only scenario control; absent from normal and demo entrypoints."""

from fastapi import HTTPException

from jobintel.openai_transport import EMULATOR_MODEL, EMULATOR_TOKEN, HttpOpenAITransport
from jobintel.providers import selected_provider
from scripts.responses_emulator.server import SCENARIOS
from scripts.responses_environment import request


def install(app, base, root):
    fixture = app.state.provider
    fixture_configuration = app.state.configuration
    emulator = selected_provider(
        root,
        "openai",
        model=EMULATOR_MODEL,
        transport=HttpOpenAITransport(
            EMULATOR_TOKEN, 1, mode="emulator", endpoint=base + "/v1/responses"
        ),
    )

    @app.post("/responses-fixture/{scenario}")
    def select(scenario: str):
        if scenario == "fixture":
            app.state.provider = fixture
            app.state.configuration = fixture_configuration
            return {"execution_mode": "fixture"}
        if scenario not in SCENARIOS:
            raise HTTPException(422, "unknown authored scenario")
        request(base, "/control", {"scenario": scenario})
        app.state.provider = emulator
        app.state.configuration = "openai_normalized_v1"
        return {"execution_mode": "emulator"}

    @app.get("/responses-fixture-diagnostics")
    def diagnostics():
        return request(base, "/diagnostics")
