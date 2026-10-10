# Automated quality gates

`.github/workflows/test.yml` runs on every push and pull request, with manual
`workflow_dispatch` support. It has read-only repository permissions, bounded
timeouts and cancels superseded runs for the same ref. There are no paid calls.
Runners use Ubuntu 24.04 explicitly; checkout v5 and setup-python v6 use Node 24.

| Job | Blocking checks |
| --- | --- |
| Quality | Ruff lint, Ruff format, McCabe C901, ShellCheck and actionlint |
| Python 3.11 / 3.12 | Dependency consistency, authored fixture reproducibility, complete pytest suite including PostgreSQL, SQLite/PostgreSQL migration drift, repeated CLI demo/export/evaluation, wheel and sdist builds |
| Container | Compose validation, normal Docker image build, PostgreSQL/migrations startup, CLI demo/evaluation and actual HTTP evidence/normalization/analytics/evaluation smoke |

The container job also runs `scripts/runtime_smoke.py` against online and prepared
offline-wheel builds. It verifies named dev data/output persistence across container
recreation, explicit reset, demo-only route isolation and mounted OpenAI configuration
with a synthetic key. No extraction/evaluation call is made on the OpenAI profile.
The runtime driver waits for migrations and API readiness; health checks stay local.

The container gate also runs `python -m scripts.acquisition_smoke`: a disposable
PostgreSQL/API/origin/proxy stack exercises actual fetch routes and verified TLS.
Its JSON evidence records passed service cases and sanitized routing diagnostics.
Both Python versions run the real-socket origin tests against SQLite/PostgreSQL
alongside the fast transport doubles. The web workflow launches containerized
acquisition fixtures for every desktop/mobile journey and uploads origin/proxy
diagnostics on every outcome. Fixtures never make external acquisition/LLM calls.

Python and container jobs depend on the quality gate. The container job also waits
for both Python versions. Every command preserves its exit code: failed checks fail
the workflow, rather than merely reporting findings. Container diagnostics run on
failure, cleanup runs regardless of outcome. Remote success must be observed, not
inferred from a successful local check or push.

## Linting policy

Ruff checks undefined/unused names and imports, syntax/control-flow errors, import
ordering, bugbear pitfalls (including strict zip), Python 3.11 modernization,
comprehension mistakes, unnecessary constructs and Ruff-specific correctness rules.
`ruff format --check` rejects formatting drift. Both use `pyproject.toml`.

**C901 enforces maximum cyclomatic complexity 10 per function.** This applies to
application code, scripts, tests and migrations. There are no complexity exemptions
or baseline suppressions. A function above 10 must be decomposed around meaningful
responsibilities while preserving behavior; do not increase the limit to make a
change pass. API creation, route handlers and transactional dependencies are separate
functions for this reason. Formatting does not substitute for complexity checks.

ShellCheck checks repository shell scripts and actionlint also inspects workflow
shell commands, expressions, events, job dependencies and action inputs. actionlint
1.7.7 is pinned and verified against its official release checksum before execution.
Python tool versions are pinned in `requirements.lock.txt`.

## Run locally

From the repository root, activate `.venv` and install development dependencies:

```bash
python -m pip install -c requirements.lock.txt -e '.[dev]'
python scripts/check.py
bash scripts/install_actionlint.sh
shellcheck scripts/*.sh
local_data/bin/actionlint -color
```

`check.py` uses a temporary SQLite DB and temporary outputs for smoke/build checks;
it never migrates or seeds the default private/local DB. It regenerates authored
fixtures in a temporary directory and compares bytes, never overwriting `data/`.
Without `TEST_DATABASE_URL`, pytest explicitly skips its PostgreSQL test.

For the full Python CI suite, start the disposable PostgreSQL database documented
in the README, wait for readiness, then:

```bash
TEST_DATABASE_URL=postgresql+psycopg://jobintel:ci-only@localhost:55432/jobintel_test \
  python scripts/check.py --require-postgres
```

`--require-postgres` fails if a PostgreSQL test URL is absent; it cannot turn the
required CI integration check into a silent skip. Use a disposable database only.

To verify containers, run the README Compose quick start, seed with `jobintel demo`,
then `python scripts/container_smoke.py`. On this cloud machine use the offline
wheel/Compose override if build-container DNS is unavailable. GitHub's container
job validates the ordinary online Dockerfile and Compose path.

Required new regressions and backend result publication are tracked in
[issue #10](https://github.com/newdarwindev/JobIntelAI/issues/10). Live experiment evidence is tracked separately in
[issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9); ordinary CI uses no paid calls.

The Python matrix uploads `backend-evidence-python-*` artifacts on every outcome:
JUnit, command diagnostics and JSON pass/fail/error/skip counts with commit/config
provenance. `scripts/check.py --junitxml path.xml` emits the same local test result.
The CLI smoke also freezes, runs and rescores a complete fake experiment, checking
exact saved-score reproduction without another provider call.

Each matrix artifact includes `summary.json` (actual command exit code, Python,
commit and Actions run/attempt), `junit.xml`, `check.log`, `release-audit.json` and
`publication-probes/`. The two synthetic publication probes intentionally exercise
success and failure: success is 1 pass / 0 fail / 1 skip, failure is 1 pass / 1 fail /
1 skip with exit code 1. The harness requires those exact outcomes; an unexpected
probe result fails CI. These diagnostic probes are separate from acceptance tests.
Nested JUnit suite totals are counted from leaf cases without double-counting.

`MANIFEST.in` bundles licensed authored fixtures and migration/configuration files
in the source release. The release audit rejects private runtime paths, database/key
files and unknown or modified corpus files; tests build with injected ignored private
sentinels to verify their exclusion. It is a deterministic archive/corpus check, not
an automatic legal or secret-content review. The installed wheel is exercised from a
fresh unpacked source release with the README migration/demo/evaluation/export path
and API readiness/analytics, outside the original checkout. Only counts and archive
hashes enter CI evidence; temporary databases and generated candidate/posting outputs
are not uploaded. Every artifact has 30-day retention and PR/fork runs remain read-only.

The container gate also runs `scripts.acquisition_public_smoke` on the hosted
runner's authorized direct-egress gateway host. Its production policy proxy
resolves and pins the immutable public SYN-01 URL, while the client refuses local
destination DNS. Exact body hash/bytes and verified TLS are required; failures
fail CI. `work/acquisition-public.json` is uploaded alongside the controlled
service outcome on all attempts. A restricted inherited proxy without the
gateway contract must report `proxy_capability`, not readiness success.

The container gate also runs `python -m scripts.responses_smoke` against a disposable
API/PostgreSQL/Responses service stack. It uploads `work/responses-service.json` on
all outcomes with actual case counts, commit/config/model identity and safe request
checks. Python 3.11/3.12 test real provider-process sockets; browser UI07 uses the
container emulator and uploads `work/responses-browser-diagnostics.json`. These
are authored contract checks, with no paid calls or model-quality claim.

The separate `Local CPU inference` workflow executes `scripts.local_smoke` for
local-provider changes or on demand. Its two-CPU/five-GiB engine uses pinned
licensed weights and a checksum-verified cache. It uploads actual unseen pipeline
checks, complete three-case reviewed outcomes, startup/memory measurements and
commit/config/model provenance on every outcome. Model errors remain evaluation
results; perfect metrics are not a CI requirement. See [local inference](local_inference.md).
