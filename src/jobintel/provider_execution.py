"""Separate extraction protocol identity from the service executing it."""


def execution_mode(provider):
    return (
        getattr(getattr(provider, "transport", None), "mode", "hosted")
        if provider.name == "openai"
        else "fixture"
    )


def execution_status(provider):
    mode = execution_mode(provider)
    ready = provider.transport.ready() if mode == "emulator" else True
    return {"execution_mode": mode, "live_llm": mode == "hosted", "provider_ready": ready}
