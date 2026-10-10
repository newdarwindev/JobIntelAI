"""One injectable HTTP transport for the OpenAI Responses API, with no hidden retries."""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

LIVE_ENDPOINT = "https://api.openai.com/v1/responses"
EMULATOR_TOKEN = "jobintel-contract-only"
EMULATOR_MODEL = "contract-schema-v2"


def responses_endpoint(mode, endpoint, api_key):
    if mode == "hosted" and endpoint in {None, LIVE_ENDPOINT}:
        return LIVE_ENDPOINT
    if mode != "emulator":
        raise ValueError("Responses mode must be hosted or emulator; hosted endpoint is fixed")
    try:
        address = urlsplit(endpoint or "")
        port = address.port
    except ValueError:
        raise ValueError("emulator requires a scoped local HTTP /v1/responses endpoint") from None
    if (
        address.scheme != "http"
        or address.hostname not in {"localhost", "127.0.0.1", "::1", "responses-emulator"}
        or address.path != "/v1/responses"
        or address.username is not None
        or address.password is not None
        or address.query
        or address.fragment
        or not port
    ):
        raise ValueError("emulator requires a scoped local HTTP /v1/responses endpoint")
    if api_key != EMULATOR_TOKEN:
        raise ValueError("emulator accepts only the fixed development token")
    return endpoint


class ProviderError(RuntimeError):
    def __init__(self, code: str, status: int, retryable: bool):
        self.code = code
        self.status = status
        self.retryable = retryable
        # Upstream bodies/exceptions can contain source data and keys; never expose them.
        super().__init__(f"extraction provider: {code}")

    def detail(self):
        return {"code": self.code, "retryable": self.retryable, "message": str(self)}


@dataclass(frozen=True)
class TransportResponse:
    body: dict
    request_id: str | None = None


class OpenAITransport(Protocol):
    def complete(self, payload: dict) -> TransportResponse: ...


class HttpOpenAITransport:
    def __init__(
        self, api_key: str, timeout: float = 30, *, transport=None, mode="hosted", endpoint=None
    ):
        self.endpoint = responses_endpoint(mode, endpoint, api_key)
        self.mode = mode
        self._api_key = api_key
        self.timeout = timeout
        self._transport = transport

    def complete(self, payload: dict) -> TransportResponse:
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport, trust_env=self.mode == "hosted"
            ) as client:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as error:
            raise ProviderError("timeout", 504, True) from error
        except httpx.RequestError as error:
            raise ProviderError("provider_failure", 502, True) from error
        if response.is_error:
            raise http_error(response)
        try:
            body = response.json()
        except ValueError as error:
            raise ProviderError("malformed_json", 502, True) from error
        if not isinstance(body, dict):
            raise ProviderError("invalid_schema", 502, True)
        return TransportResponse(body, response.headers.get("x-request-id"))

    def ready(self):
        if self.mode != "emulator":
            return True
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                response = client.get(self.endpoint.removesuffix("/v1/responses") + "/health")
            body = response.json()
            return (
                response.status_code == 200
                and isinstance(body, dict)
                and body.get("mode") == "emulator"
            )
        except (httpx.HTTPError, ValueError):
            return False


def http_error(response):
    if response.status_code == 429:
        try:
            error = response.json().get("error", {})
            quota = error.get("code") == "insufficient_quota"
        except (ValueError, AttributeError):
            quota = False
        return ProviderError("quota" if quota else "rate_limit", 502, not quota)
    return ProviderError("provider_failure", 502, response.status_code >= 500)
