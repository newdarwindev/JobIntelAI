# JobIntel AI

Evidence-grounded job requirements and candidate skill-gap analysis. The target
system ingests postings, extracts structured requirements with source quotes,
normalizes skills, matches candidate evidence and measures extraction quality.
Every claim needs evidence; every corpus count needs an explicit denominator.

Implementation work and acceptance criteria are tracked in [GitHub issues](https://github.com/newdarwindev/JobIntelAI/issues). See [the issue map](docs/implementation_plan.md) for dependencies.

## Mock web workspace and recorded acceptance workflows

The spec-driven UI exposes six screens: overview, CSV/JSON job registry, immutable
source/evidence workbench, candidate evidence matching, corpus analytics/exports,
and fixture evaluation. It uses the real API with the deterministic fixture
provider. The
authorized frontend scope extension and limitations are in
[the UI acceptance specification](docs/web_ui_spec.md).

After the Python install below, start the isolated synthetic sandbox:

```bash
python scripts/serve_ui.py
# Open http://127.0.0.1:8000/ui/
```

Select **Load synthetic corpus** to process all 20 authored postings, or import a
sample registry and walk through source capture, extraction, and matching yourself.
The launcher migrates a disposable SQLite database before serving and deletes it
on exit. Normal `uvicorn jobintel.api:app` also serves `/ui/` against its configured
database, without synthetic fixture/reset endpoints. Candidate display state lives in the current browser session; the selected evaluation
run ID reloads its saved report after refresh. Corpus categories, gaps and coverage are
computed from saved source/extraction/match outcomes and survive refresh for the
explicitly selected candidate revision. No API keys, third-party UI assets, or paid
calls are needed.

Run every complete workflow on desktop and mobile Chromium (Node 22+):

```bash
npm ci
npx playwright install --with-deps chromium
npm run test:ui
npm run record:ui
npm run check:ui
```

Local Playwright defaults to `.venv/bin/python`; set `UI_PYTHON=python` if using an
activated environment elsewhere. `UI_BROWSER_PATH` can select a local Chromium
binary. The [Actions workflow](.github/workflows/web-ui.yml) runs all journeys,
retains reports/videos/failure traces as artifacts, and commits passing README
videos on trusted default-branch pushes. PR/fork runs publish downloadable evidence
without write permissions. Bot publication requires Actions write permission and
a branch policy permitting its commit; protected branches can apply the verified
artifact via their PR process. Recording-only bot commits on the default branch skip CI; PR updates still run the full suite.

**Every UI change must update its workflow and successful recordings.** This is
mandatory in [AGENTS.md](AGENTS.md), with a source-hash/video-integrity gate and the
[machine-readable coverage map](docs/web_ui_workflows.json). Videos below are linked
as files because GitHub Markdown does not reliably render inline HTML video tags.

<!-- UI-RECORDINGS:START -->

Successful browser attempts: **16/16**, recorded 2026-10-09.
Source: [GitHub Actions run](https://github.com/newdarwindev/JobIntelAI/actions/runs/37928713698) · commit `33b045f1e7e227380a56f97750ad39f3e3a69f07`.
Source content SHA-256: `3de74c9b22d4dd74ba59bf2328ead8691f1209ce6a9a5ba37160d3445be14964`. [Machine-readable provenance](docs/ui-recordings/manifest.json).

| Complete workflow | Desktop Chromium | Mobile Chromium |
| --- | --- | --- |
| UI01 · Atomic registry import and discovery | [Watch](docs/ui-recordings/UI01-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI01-mobile-chromium.webm) |
| UI02 · Source capture, URL fallback and immutable history | [Watch](docs/ui-recordings/UI02-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI02-mobile-chromium.webm) |
| UI03 · Grounded extraction, aliases and operators | [Watch](docs/ui-recordings/UI03-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI03-mobile-chromium.webm) |
| UI04 · Candidate evidence and four matching states | [Watch](docs/ui-recordings/UI04-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI04-mobile-chromium.webm) |
| UI05 · Corpus slices, gaps and safe provenance exports | [Watch](docs/ui-recordings/UI05-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI05-mobile-chromium.webm) |
| UI06 · Fixture and source-reviewed evaluation diagnostics | [Watch](docs/ui-recordings/UI06-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI06-mobile-chromium.webm) |
| UI07 · Provider and connection failure recovery | [Watch](docs/ui-recordings/UI07-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI07-mobile-chromium.webm) |
| UI08 · Keyboard navigation, responsive layout and inert input | [Watch](docs/ui-recordings/UI08-desktop-chromium.webm) | [Watch](docs/ui-recordings/UI08-mobile-chromium.webm) |

<!-- UI-RECORDINGS:END -->

## Architecture and evidence trace

```mermaid
flowchart LR
    Import[CSV / JSON] --> Snapshot[Raw + clean snapshot / SHA-256]
    Snapshot --> Extract[Provider → strict schema → evidence guard]
    Extract --> Normalize[Canonical aliases + ANY / ALL groups]
    Normalize --> Match[Candidate capability + production evidence]
    Normalize --> Counts[Corpus n/N counts]
    Normalize --> Eval[Golden evaluation]
    Match --> API[FastAPI / CLI / JSON / CSV]
    Counts --> API
    Eval --> API
```

For `SYN-01`, the source says “Python is required.” and “Postgres is nice to have.”
Extraction retains both exact quotes and `[start:end]` offsets in the immutable
clean source. Python is MUST; Postgres is PREFERRED and normalizes to PostgreSQL.
The synthetic candidate has explicit strong Python capability and production
evidence, producing COVERED. PostgreSQL has no record in an incomplete profile,
producing UNKNOWN. Nothing is inferred from an employer name.

“AWS or Azure” remains one ANY group, not two independent must-haves. Quote integrity is enforced. See [the full spec](docs/specification.md) for evidence and matching contracts.

## Quick start: offline, no Docker or API key

Run from this checkout's root with Python 3.11+ (CI tests 3.11 and 3.12):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements.lock.txt -e '.[dev]'
mkdir -p local_data
python -m alembic upgrade head
jobintel demo
jobintel evaluate
python -m pytest -q
uvicorn jobintel.api:app --host 127.0.0.1 --port 8000
```

Default SQLite database: `local_data/jobintel.db`. Private inputs and generated
outputs are ignored. Commands write JSON/CSV to `results/generated/`; `jobintel
export` exports current counts. Repeating the demo reuses jobs/latest identical
snapshots and appends extraction/match runs. `.env.example` documents settings;
the Python application reads exported variables, not `.env` automatically.

In a second terminal:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/jobs/SYN-01
curl --fail http://127.0.0.1:8000/analytics/skills
curl --fail -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' -d '{}'
```

Candidate imports are private local database revisions. Save one with
`jobintel candidate-import --input local_data/profile.json`, list it with
`jobintel candidate-revisions --profile-id PROFILE`, and explicitly select it using
`jobintel match --job-id JOB --profile-id PROFILE --revision-id REVISION --run-id EXTRACTION`.
Read historical results with `jobintel match-run --run-id MATCH_RUN`.
The browser saves/reloads the selected revision ID and displays sourced tenure and
eligibility alongside separate capability and production evidence.

## Explicit OpenAI extraction

Fixture replay stays the offline default. For separately authorized live execution,
export `JOBINTEL_PROVIDER=openai`, an explicit structured-output-compatible
`JOBINTEL_OPENAI_MODEL`, and `OPENAI_API_KEY` from secure runtime configuration.
Never put credentials in postings, configuration files, public artifacts or CLI
arguments. `JOBINTEL_OPENAI_TIMEOUT` defaults to 30 seconds (allowed: 1–120).
The HTTP adapter uses the existing packaged httpx dependency and the
[Responses Structured Outputs contract](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

`JOBINTEL_CONFIGURATION` selects `openai_structured_v1` (raw terms) or
`openai_normalized_v1` (deterministic taxonomy aliases, default). Both use the
packaged `job-requirements-v1` prompt and grounded extraction schema v2. Missing
keys/models and mismatched configurations fail before requests. The synthetic
`demo` command/launcher requires fixture replay. No failure substitutes fixtures.

After importing a job and saving its snapshot, the same extraction is available via
`jobintel extract --provider openai --configuration openai_normalized_v1 --job-id ID`
or `POST /jobs/ID/extract` with `{"configuration":"openai_normalized_v1"}` on an
explicitly configured OpenAI app. `create_app(provider_name="openai", model=...,
transport=...)` supports injectable fake transports. `/health` reports the selected
provider/configuration and configuration readiness; it makes no paid readiness call
and does not establish upstream reachability. Startup rejects missing configuration.

New runs retain source/snapshot IDs, provider/model (requested and returned),
configuration/prompt versions and hashes, schema/taxonomy hashes, request/response
IDs, bounded attempt metadata, actual supplied usage, and measured local elapsed
seconds. Missing usage, provider-only latency and cost remain null. Historical
runs migrated from older versions retain null provenance rather than invented data.
`/evaluate` and `jobintel evaluate --provider openai --configurations
openai_structured_v1 openai_normalized_v1` preserve per-posting provenance and fail
atomically; the authored fixture labels do not establish independent live quality.

Typed errors carry `detail.code`, `retryable` and a redacted message: refusal and
invalid evidence use 422; malformed JSON, invalid schema, truncation, quota,
rate-limit and provider failure use 502; timeout uses 504. Only malformed output
gets one schema retry. Quota/refusal/invalid evidence are not retryable; transient
network/rate-limit failures are retryable by an explicit caller, without hidden
transport retries. A failed extraction/evaluation keeps previous runs unchanged.
Fake transport, semantic, API/CLI and migrated database regressions are in
`tests/unit/test_openai*` and `tests/integration/test_openai_boundary.py` (V12–V19).

## PostgreSQL / Docker

```bash
docker compose up -d --build
docker compose exec api jobintel demo
docker compose exec api jobintel evaluate
curl --fail --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
docker compose down
```

Compose waits for PostgreSQL, runs Alembic in a one-shot service, then starts the
API on loopback. The database volume survives `down`; generated CLI output in the
API container does not survive its recreation. Demo credentials are local only.
If Docker's default config directory is read-only (as in some cloud tasks), use an
existing writable Docker config or prefix commands with
`DOCKER_CONFIG="$PWD/local_data/docker-config"` after creating that directory.

If build containers cannot reach package hosts, prepare wheels on a Linux x86_64
Python 3.12 host and use the offline override (the base image still needs to be
available). Wheels are ignored generated files; recreate them when dependencies
or the target platform change. Downloading with pip retains TLS/artifact validation.

```bash
python -m pip wheel --wheel-dir build/wheels -c requirements.lock.txt \
  -r requirements.lock.txt 'setuptools>=75' wheel .
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --build
```

Use the same two `-f` options for subsequent Compose commands in that workflow.

For the **optional local, required CI** PostgreSQL test, start a disposable database:

```bash
docker run --rm -d --name jobintel-test-db \
  -e POSTGRES_USER=jobintel -e POSTGRES_PASSWORD=ci-only \
  -e POSTGRES_DB=jobintel_test -p 127.0.0.1:55432:5432 postgres:16-alpine
# Wait until this reports accepting connections:
docker exec jobintel-test-db pg_isready -U jobintel -d jobintel_test
TEST_DATABASE_URL=postgresql+psycopg://jobintel:ci-only@localhost:55432/jobintel_test \
  python -m pytest -q
docker stop jobintel-test-db
```

CI provisions its own PostgreSQL service. Do not point test commands at private or
production databases. See [validation evidence](docs/validation.md) for checks
actually executed in this workspace; a workflow file is not proof of remote CI.

## API and input registry

Example CSV (companies and roles are fictional):

```csv
job_id,company,role,official_url,status,applied
SYN-01,Synthetic Company 01,Backend / AI Engineer,,,
```

`POST /jobs/import` accepts exactly one of `{"jobs":[...]}` or `{"csv_text":"..."}`.
Create a manual source with `POST /jobs/{id}/snapshots` and `{"text":"..."}` or
`{"text":"<main>...</main>","format":"html"}`. A fixture extractor accepts only
bundled known content hashes; arbitrary sources need an explicitly configured
live provider for extraction. URL acquisition uses a bounded public-destination
HTTP transport with saved attempts and manual recovery. See the
[acquisition contract](docs/acquisition.md) for time/size limits and proxy support.
The demo uses authored offline HTTP/DNS responses and performs no URL crawling.

| Endpoint | Interface |
| --- | --- |
| GET /health | DB connection + migrated schema readiness |
| POST /jobs/import | Atomic JSON/CSV import, duplicate/conflict handling |
| GET /jobs | Ordered registry with current snapshots and extractions |
| GET /jobs/{id}/history | Immutable sources, extraction runs and acquisition attempts |
| POST /jobs/{id}/snapshots | Manual text/HTML, provenance/hash |
| POST /jobs/{id}/fetch | Bounded HTTP acquisition, 201 source/hash or typed manual fallback |
| POST /jobs/{id}/extract | `{}` defaults to normalized fixture replay |
| GET /jobs/{id} | Latest source, current requirements and evidence |
| POST /jobs/{id}/match | Candidate payload as in `data/sample_candidate.json` |
| POST /candidate/validate | Strict sourced-profile validation, no database write |
| GET /analytics/skills | Saved-source n/N, categories, candidate gaps, coverage; applied/remote slices |
| POST /exports | Shared JSON/CSV counts, requirements, evidence and saved-revision matches |
| POST /evaluate | Fixture/reviewed dataset, typed failures, persisted evaluation report |
| GET /evaluation-runs/{id} | Exact saved report and diagnostics without provider requests |

OpenAPI schemas are available at `/docs` when running locally. Error contracts and
target live behaviors are documented in [specification §12](docs/specification.md).

Export saved requirements with `jobintel export --kind requirements --output
results/generated`. Counts, matches and explicit historical runs use the same
[API/CLI/browser export contract](docs/exports.md). JSON retains exact values;
spreadsheet CSV protects formula prefixes. The default `jobintel export` keeps its
original skills CSV columns and filenames.

## Automated checks

GitHub Actions runs Ruff lint/format, a **C901 complexity gate of 10**, ShellCheck,
actionlint, tests on Python 3.11/3.12 with PostgreSQL, migration drift checks,
fixture reproducibility, repeated CLI smoke, package builds and Docker/API smoke.
Lint failures block the downstream jobs. No paid providers or private data are used.

```bash
python scripts/check.py
bash scripts/install_actionlint.sh
shellcheck scripts/*.sh
local_data/bin/actionlint -color
```

Add `--require-postgres` to the Python check command with a disposable
`TEST_DATABASE_URL` for the complete backend CI path. See [CI policy](docs/ci.md).

## Data model and structured output

Jobs → snapshots → extraction runs → requirements; matches reference a requirement
and candidate profile snapshot. Skills hold canonical aliases; evaluation runs
hold metrics. JSON payloads keep the first schema compact while FKs retain traceability.
See [data model](docs/data_model.md) and [architecture](docs/architecture.md).

Requirement fields: exact `raw_text`, normalized name, `skills`, SINGLE/ANY/ALL,
MUST/PREFERRED/EXPERIENCE/OTHER, category, evidence quote/offsets, explicit production
predicate (true/false/unknown), years range (or unknown), confidence and ambiguity
notes. Pydantic rejects unknown fields; source validation rejects unmatched quotes.
Current capability and historical production evidence stay separate in matching.

## Evaluation and corpus example

The fixed 20-posting corpus has 22 labelled requirements. The verified fixture run
produced this table; gold and replay responses share authored definitions, so these
numbers **are not independent LLM quality measurements**:

| Fixture configuration | Precision | Recall | Type accuracy | Evidence accuracy | Unsupported span rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw aliases | 18/22 | 18/22 | 18/18 | 18/18 | 0/22 |
| Deterministic normalized | 22/22 | 22/22 | 22/22 | 22/22 | 0/22 |

Type/evidence accuracy use aligned-pair denominators. Semantic hallucination,
abstention, tokens and cost are unavailable, represented by null. Test cases inject
wrong types, duplicate predictions and invalid evidence to verify metric failures.
Read [evaluation methodology](docs/evaluation.md) and the saved
[fixture report](results/fixture_evaluation.json).

`jobintel evaluate --dataset reviewed` uses 25 frozen source-reviewed cases and
a sourced synthetic candidate. It measures semantic, abstention, filter, responsibility
and matching agreement with explicit counts. The bounded fixture provider has no
response for five cases: the command saves their diagnostics and exits 1. Reports
retain failures and remain retrievable through `/evaluation-runs/{id}` or
`jobintel evaluate --run-id ID`. UI06 reloads saved evaluations after refresh.
The source reviewer and limitations are recorded in the methodology; this replay
run supplies no live-model quality claim. See the [saved diagnostic JSON](results/reviewed_fixture_evaluation.json)
and [human-readable errors](results/reviewed_fixture_evaluation.txt). Do not substitute fixture measurements for independently reviewed model results.

The opt-in [experiment command](docs/experiments.md) freezes snapshots and labels,
checks call/token/USD reservations, checkpoints failures and rescores saved outputs
without requests. The [complete fake report](results/experiments/fake/report.json)
and [reproduced scores](results/experiments/fake/scores.json) include corpus, source,
schema and configuration hashes. These A/B/C values are plumbing measurements:
the fake provider supplies identical raw predictions, then C applies normalization.

| Fake configuration | Aligned / predicted | Aligned / gold | Type | Evidence | Failures / cases | Tokens / priced cost |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A · free-form audit path | 18/22 | 18/22 | 18/18 | 18/18 | 0/20 | unavailable |
| B · strict evidence path | 18/22 | 18/22 | 18/18 | 18/18 | 0/20 | unavailable |
| C · strict + normalization | 22/22 | 22/22 | 22/22 | 22/22 | 0/20 | unavailable |

Local replay duration is in the report; it measures no LLM latency. Semantic and
abstention metrics are null. The alias trade-off above does not predict a live
winner. [Issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9) requires
separately authorized live reports and independent reviewer audit for closure.

`jobintel experiment freeze --dataset reviewed` packages the 25-case benchmark for
opt-in A/B/C comparisons. The reviewed fake diagnostic run preserves five unavailable
fixture inputs per configuration and uses counted semantic/abstention/matching
metrics; its [complete report](results/experiments/reviewed-fake/report.json),
[saved scores](results/experiments/reviewed-fake/scores.json) and
[comparison](results/experiments/reviewed-fake/comparison.md) are fixture evidence.
Live execution requires separate paid-call authorization, dated model-specific
pricing and secure runtime credentials. The [experiment protocol](docs/experiments.md)
describes planning, failure checkpoints, credential-free rescoring and hash-bound
reviewer publication with a measured README table. Fake results establish no live
model quality.

After the demo, N=20 successful latest-source extractions. Python appears in 5/20
jobs (MUST 3/20, PREFERRED 1/20, EXPERIENCE 1/20). AWS OR Azure appears as a separate
alternative group, not two independent MUST frequencies. These are selected-corpus
counts, not labor-market conclusions. [Example CSV](results/example_skill_counts.csv).

## Trade-offs and privacy

Snapshots survive disappearing URLs and allow model/config changes without rewriting
sources. Exact aliases are simple to audit; they do not erase distinct products or
version predicates. Confidence cannot compensate for absent evidence. SQLite keeps
the demo easy, while PostgreSQL integration checks the intended storage. HTTP first
and manual fallback avoid making browser infrastructure the core project.

No private search log, correspondence, employer data or unauthorized third-party
postings belong in Git. Store private inputs outside the checkout or in `local_data/`.
This is unauthenticated single-user local tooling; do not expose it publicly.
See [privacy and copyright](docs/privacy_and_copyright.md).

Implementation priorities and release acceptance are maintained in [GitHub issues](https://github.com/newdarwindev/JobIntelAI/issues), linked by [the issue map](docs/implementation_plan.md).

- [Full specification](docs/specification.md)
- [Acceptance scenarios](docs/testing_scenarios.md): regression references and issue traceability
- [Implementation plan](docs/implementation_plan.md)
- [Agent instructions](AGENTS.md)
- [Original uploaded brief](docs/source_brief.txt)
