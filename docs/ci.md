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
