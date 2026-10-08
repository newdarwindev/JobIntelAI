"""Synthetic Responses envelopes; tests never contact a paid service."""

import json

from jobintel.openai_transport import TransportResponse


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, payload):
        self.requests.append(payload)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(payload, *, status="completed", usage=None, request_id="req-synthetic"):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return TransportResponse(
        {
            "id": "resp-synthetic",
            "model": "synthetic-snapshot",
            "status": status,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": usage,
        },
        request_id,
    )
