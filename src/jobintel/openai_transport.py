"""One injectable HTTP transport for the OpenAI Responses API, with no hidden retries."""

from dataclasses import dataclass
from typing import Protocol

import httpx


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
    def __init__(self, api_key: str, timeout: float = 30, *, transport=None):
        self._api_key = api_key
        self.timeout = timeout
        self._transport = transport

    def complete(self, payload: dict) -> TransportResponse:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
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


def http_error(response):
    if response.status_code == 429:
        try:
            error = response.json().get("error", {})
            quota = error.get("code") == "insufficient_quota"
        except (ValueError, AttributeError):
            quota = False
        return ProviderError("quota" if quota else "rate_limit", 502, not quota)
    return ProviderError("provider_failure", 502, response.status_code >= 500)
