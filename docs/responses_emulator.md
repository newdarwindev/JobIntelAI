# Responses contract emulator

`contract-test` runs PostgreSQL, explicit migrations, the normal API and a separate
Responses emulator process. It exercises `HttpOpenAITransport` and `OpenAIProvider`
through real sockets. The service replays authored schema-v2 responses from known
synthetic source hashes; it performs no inference or outbound HTTP requests.
Unknown inputs fail explicitly. This is contract evidence, not model quality.

```bash
python scripts/runtime.py up --mode contract-test --project jobintel-contract --port 8003
python scripts/runtime.py status --project jobintel-contract
python scripts/runtime.py stop --project jobintel-contract
python scripts/runtime.py reset --project jobintel-contract
```

Stop preserves data; explicit reset removes only the named project's volumes.
`--offline` builds all three application images from the prepared, pinned local
wheel cache, including the emulator; prepare wheels as described in the README.
The API remains at `http://127.0.0.1:8003`, without demo fixture/reset routes.
Use the ordinary import → snapshot → extract endpoints with an authored source
such as `data/sample_jobs/SYN-01.txt`. The API's extraction configuration is
`openai_normalized_v1`, model `contract-schema-v2`, execution mode `emulator`.
The internal Responses network joins the API to the emulator. A separate control
network publishes the emulator on a random loopback port for local scenario control.

To inspect that port and select a failure, while the runtime is running:

```bash
docker compose -p jobintel-contract -f docker-compose.yml -f docker-compose.responses.yml \
  --profile contract-test port responses-emulator 8033
curl -H 'Authorization: Bearer jobintel-contract-only' -H 'Content-Type: application/json' \
  -d '{"scenario":"quota"}' http://127.0.0.1:EMULATOR_PORT/control
curl http://127.0.0.1:EMULATOR_PORT/diagnostics
```

The fixed development token is public and provides no production authentication.
Never expose these development endpoints to an untrusted network. The emulator
accepts only that token. Selection reads no `OPENAI_API_KEY` or secret file; Compose
does not mount or forward hosted credentials. Hosted mode keeps the fixed verified
HTTPS public Responses endpoint and inherited proxy/CA settings. Emulator mode
accepts only HTTP loopback or the scoped `responses-emulator` Compose hostname, with
no URL credentials, query or fragment. Its local sockets use the explicitly chosen
endpoint without environmental Internet proxies. This cannot select a public host.

For an independently running API, set `JOBINTEL_PROVIDER=openai`,
`JOBINTEL_RESPONSES_MODE=emulator`, `JOBINTEL_RESPONSES_ENDPOINT` to the scoped
`http://127.0.0.1:PORT/v1/responses`, and `JOBINTEL_OPENAI_MODEL=contract-schema-v2`.
The default transport mode remains `hosted`. The emulator validates the exact
strict schema, system prompt, model, input shape, `store=false`, token limit and
development authentication. Diagnostics contain boolean checks and request counts,
never request/response bodies, source text or tokens. Access logging is disabled.

| Authored scenario | API result | Requests per extraction |
| --- | --- | --- |
| success | persisted schema-v2 extraction | 1 |
| malformed_then_success | persisted schema-v2 extraction | 2 |
| refusal, invalid_evidence | 422, nonretryable | 1 |
| malformed_json, malformed_http, invalid_schema, truncated | 502, nonretryable after bounded validation retry | 2 |
| quota | 502, nonretryable | 1 |
| rate_limit, server_error, connection_close | 502, retryable | 1 |
| delay | 504, retryable with the smoke's one-second timeout | 1 |

Selecting a scenario resets its request count; cumulative safe history remains
available until process restart. Failure attempts append to history without changing
the prior successful extraction. There is no retry for transport/HTTP/refusal/grounding
failures and no fallback to fixture or another provider. The service's delay is two
seconds; runtime timeout remains configurable between 1 and 120 seconds.

`/health` and `/ui/config` identify the execution mode and set `live_llm=false` for
the emulator. Health makes a bounded local emulator readiness probe; unavailable
emulator readiness returns 503 while source/history reads remain usable. Hosted
readiness checks configuration only and makes no paid request. Persisted run
provenance and evaluation identities identify `emulator`. Token usage, costs and
LLM time are null; HTTP/end-to-end timing is measured. Evaluation modes explicitly
say authored replay is not model quality. Pricing is rejected for emulator runs.

```bash
python -m scripts.responses_smoke
# Managed proxy build: add --ca-bundle /etc/ssl/certs/ca-certificates.crt
```

This disposable container smoke verifies all error envelopes, grounding, persisted
identity, strict request assertions, preserved runs, stop/start/restart recovery and
evaluation identity. It always writes `work/responses-service.json` and removes its
owned services/volumes. The full Python suite additionally starts a separate local
emulator process against migrated SQLite and PostgreSQL; fast fake transports stay.
UI07 uses the running emulator via the actual API; only the browser-to-API connection
abort remains a browser interception. Scenario selectors exist only in the test
launcher, never normal/demo API entrypoints. All UI journeys retain recordings.
