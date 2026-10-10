"""Local-only llama.cpp Chat Completions HTTP; never loads or forwards a hosted key."""

from urllib.parse import urlsplit

import httpx

from jobintel.local_model import MODEL
from jobintel.openai_transport import ProviderError, TransportResponse, http_error

LOCAL_TOKEN = "jobintel-local-only"


def local_endpoint(endpoint):
    try:
        address = urlsplit(endpoint or "")
        port = address.port
    except ValueError:
        raise ValueError(
            "local inference requires a scoped HTTP /v1/chat/completions endpoint"
        ) from None
    if (
        address.scheme != "http"
        or address.hostname not in {"localhost", "127.0.0.1", "::1", "llama-cpp"}
        or address.path != "/v1/chat/completions"
        or address.username is not None
        or address.password is not None
        or address.query
        or address.fragment
        or not port
    ):
        raise ValueError("local inference requires a scoped HTTP /v1/chat/completions endpoint")
    return endpoint


class HttpLocalTransport:
    mode = "local-inference"

    def __init__(self, endpoint, timeout=120, *, transport=None):
        self.endpoint = local_endpoint(endpoint)
        self.timeout = timeout
        self._transport = transport

    def complete(self, payload):
        try:
            with httpx.Client(
                timeout=self.timeout, trust_env=False, transport=self._transport
            ) as client:
                response = client.post(
                    self.endpoint, json=payload, headers={"Authorization": f"Bearer {LOCAL_TOKEN}"}
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
        base = self.endpoint.removesuffix("/v1/chat/completions")
        try:
            with httpx.Client(timeout=1, trust_env=False, transport=self._transport) as client:
                health = client.get(base + "/health")
                if health.status_code != 200 or health.json() != {"status": "ok"}:
                    return False
                response = client.get(base + "/v1/models")
            models = response.json()
            items = models.get("data") if isinstance(models, dict) else None
            return (
                response.status_code == 200
                and isinstance(items, list)
                and any(isinstance(item, dict) and item.get("id") == MODEL for item in items)
            )
        except (httpx.HTTPError, ValueError):
            return False
