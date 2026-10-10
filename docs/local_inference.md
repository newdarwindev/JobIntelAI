# Local CPU extraction

Use a Linux Docker host with two CPU cores, at least 8 GiB RAM and 20 GiB free
disk for weights, images and build layers. The engine is limited to two CPUs and
5 GiB memory; PostgreSQL and the API need additional headroom. No GPU or hosted
API key is required. The engine has one slot, an 8,192-token context and a
2,048-token output limit. Inputs over 6,000 Unicode characters fail with
`context_limit`, as do inputs with more than 64 nonempty lines; shorter inputs can still exceed the token context and fail
explicitly. Context shifting is disabled. The provider never clips a posting.

```bash
python -m pip install -c requirements.lock.txt -e .
python scripts/runtime.py up --mode local-inference --project jobintel-local
python scripts/runtime.py stop --project jobintel-local
python scripts/runtime.py reset --project jobintel-local
```

Initial startup prepares the model through the inherited verified proxy/CA path.
Preparation has a one-hour download deadline and verifies every byte against the
weight and license hashes. An existing corrupt file fails; remove it explicitly
before preparing it again. Downloads publish atomically under a cache lock.
Each file uses a fresh short-lived registry token so a slow weight stream cannot
leave the subsequent license request with expired authorization.
`JOBINTEL_LOCAL_MODEL_CACHE` selects the host cache (default `local_data/models`).
Stop and reset preserve this shared cache; reset deletes only the selected
project's database/output volumes. To run disconnected, prepare the model and
the README's offline wheels first, then pass `--offline`. Preparation never
contacts a registry in offline mode. `--ca-bundle` supports the existing verified
combined-CA build path. Never commit downloaded weights or private inputs.

The normal PostgreSQL API runs at `http://127.0.0.1:8000`; use `--port` for another
loopback port. It exposes no synthetic seed/reset routes. The engine runs only
on the internal inference network. Use `docker compose exec` or the API for
requests; there is no published engine port. The local provider ignores hosted
keys and model settings. Direct CLI use requires `--provider local` and
`JOBINTEL_LOCAL_ENDPOINT` pointing to a loopback `/v1/chat/completions` service
with the same pinned model. The API accepts `local_structured_v1` and
`local_normalized_v1`; normalization only applies deterministic taxonomy aliases.

## Engine, weights and license

The supported image is [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/tree/f2918cabbffe8abf8e2a90c1c089085fa116c2cf),
build 11541 at revision `f2918cabbffe8abf8e2a90c1c089085fa116c2cf`, pinned to
`sha256:bf3da52e92c083472b3d1c9f9da081f423ab9def95a87ec4bba51940382d75fd`.
The measured host is Linux amd64. Other architectures require their own runtime
verification. The image's MIT license is separate from the model license.

[Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)
uses Apache 2.0. The [Docker verified model package](https://hub.docker.com/r/ai/qwen2.5)
`ai/qwen2.5:1.5B-F16` is pinned to OCI revision
`sha256:b83c287163f67ba50ebebd583ae0f02fa3f9a8ebe5d4596c6d367460a75d88e6`.
Its raw GGUF is 3,093,669,376 bytes (2.88 GiB), SHA-256
`b6eaec3509f1d0373d1f4802654c4a7bfcde0768645d2d45e8885f6922b428ee`.
The accompanying license is also checksum-pinned and retained in the cache.
The OCI digest identifies this exact converted model artifact; an upstream
training checkpoint revision is not inferred from its filename.

The actual engine probe found that this build's Responses endpoint ignores the
requested `text.format` schema and returns prose. Local execution therefore uses
its proven Chat Completions JSON-schema sampler. The adapter parses that protocol
directly; it never treats a Chat response as a Responses envelope. Hosted OpenAI
continues to use Responses. The prompt supplies the schema, one unrelated worked
example and a deterministic line-offset map of the unchanged input. A source-bound
generation schema lets the model choose an exact whole line for requirement wording
and evidence; it constrains their serialized quote/offset pair before sampling.
The model chooses requirements and generates their semantic fields. Version evidence
uses separately generated subspans. The unchanged strict validator rechecks all output;
invalid output is never repaired. Whole-line evidence can include irrelevant context,
so this generation restriction is not a semantic correctness guarantee.

Every output passes schema-v2 and exact Unicode grounding before normalization
and persistence. Schema/malformed/truncated output repeats the original request
at most once. Evidence errors, refusals and wrong-model responses fail explicitly.
Failures append attempts and preserve successful source/extraction history.
Provenance records the actual request hash, provider/protocol, configured image
and weight pins, reported model/fingerprint, prompt/base-schema/source-bound-generation-schema/taxonomy hashes, actual
token usage and engine timing when supplied. Missing usage/timing and unmeasured
compute cost stay null. HTTP/end-to-end durations are measured separately.

## Reproducible evidence

```bash
python -m scripts.local_smoke
```

The runner owns a fresh scoped project. It verifies an authored posting whose
hash is absent from replay data, persists grounded output, matches a sourced
candidate, reads analytics/exports, evaluates and reloads a frozen reviewed
subset, then stops/recreates the service and checks history/readiness. Cleanup
retains the shared weights. `work/local-inference-service.json` includes actual
pass/fail/skip counts, source/config/model/code hashes, startup durations, cgroup
peak memory when available, and every model evaluation outcome.

The subset is fixed before inference: REV-01, REV-23 and REV-25 from the
checksum-pinned source-reviewed corpus. Its review is one automated source-only
reviewer, not a human panel. Metrics cover successful cases; failures remain
separate. Exact quotes alone do not establish semantic correctness, and measured
results do not establish quality on arbitrary postings. The initial unseen probe
correctly extracted Python as MUST with `[0:19]`, but assigned the wrong category;
the model's informational confidence did not prevent that error.

The `Local CPU inference` Actions workflow runs the same service check for local
provider changes or on demand, caches licensed weights, enforces a 30-minute job
limit and uploads sanitized results on every outcome. It makes zero paid calls.
Fast Python checks keep fake HTTP/provider coverage. Default UI recordings cover
fixture and emulator journeys plus a labelled configuration rendering fixture;
they do not count as model-quality evidence. Actual model evidence is separate.


## Recorded measurements

[Published authored results](../results/local-inference/README.md) retain both
runs, including all errors and original development provenance. On this Linux
amd64 host, initial weight/license preparation took 661.09 seconds for 2.88 GiB of
weights plus the 12,624-byte license. This includes the inherited verified proxy
path and varies with network/cache conditions.

The source-bound run started a fresh scoped stack from already prepared weights
in 39.84 seconds (including cache checks, image build and migrations); stop and
recreation with the same weights/database took 16.24 seconds. The unseen model
request reported 59.31 seconds of engine time and 2,173 tokens. Engine cgroup peak
was 708,747,264 bytes. These timings use warm host/filesystem caches; a machine
cold boot was not measured, and cgroup accounting may exclude shared host page
cache. Keep the documented 8 GiB host/5 GiB engine budget rather than sizing from
that observed peak alone.

The fixed reviewed subset accepted 1/3 cases and rejected two with
`invalid_evidence`. The accepted case missed Postgres and marked required Python
as preferred: recall 1/2, type accuracy 0/1, exact gold evidence 1/1 on successful
cases only. The initial run accepted 0/3 (two invalid evidence failures and one
timeout); its fresh-stack/recreation times were 61.95/21.42 seconds and cgroup
peak was 1,448,337,408 bytes. Missing aggregate usage/timing remains null in that
run. These are measured limitations, not evidence of reliable extraction quality.
