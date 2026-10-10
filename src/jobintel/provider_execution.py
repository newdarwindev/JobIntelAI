"""Separate extraction protocol identity from the service executing it."""


def execution_mode(provider):
    if provider.name == "local":
        return "local-inference"
    return (
        getattr(getattr(provider, "transport", None), "mode", "hosted")
        if provider.name == "openai"
        else "fixture"
    )


def execution_status(provider):
    mode = execution_mode(provider)
    ready = provider.transport.ready() if mode in {"emulator", "local-inference"} else True
    return {
        "execution_mode": mode,
        "live_llm": mode in {"hosted", "local-inference"},
        "provider_ready": ready,
    }
