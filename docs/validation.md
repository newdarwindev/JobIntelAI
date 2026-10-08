# Validation evidence

Executed in the cloud workspace on 2026-10-08 with Python 3.12.14 and 3.11.16. This records the
current scaffold, not a published environment or remote GitHub Actions run.

| Check | Observed result |
| --- | --- |
| Editable dependency install | Successful; exact tested versions saved in requirements.lock.txt |
| `python -m pip check` | No broken requirements |
| Alembic SQLite upgrade / check | Head applied; no model/migration differences detected |
| Offline CLI demo, repeated | 20 jobs processed; N stays 20, repeated imports/snapshots reused |
| Fixture evaluation | 20 postings, 22 labels, two configurations; raw 18/22 alignment, normalized 22/22 |
| pytest with disposable PostgreSQL 16 | **34 passed, 0 skipped, 0 failed** |
| PostgreSQL integration | Migration and import → source → extraction → analytics verified |
| Offline Docker Compose build/start | Successful using Dockerfile.offline and prepared verified wheels |
| Docker CLI demo / evaluation | Both successful against PostgreSQL |
| Actual HTTP API functional requests | `/health`, evidence/normalization trace for SYN-01, N=20 counts, `/evaluate` passed |
| Repository whitespace check | `git diff --check` clean |
| Ruff lint / format / C901 <= 10 | Passed after decomposing API startup, routes and transactions |
| ShellCheck / actionlint 1.7.7 | Passed; official actionlint archive checksum verified |
| Fixture reproducibility | 25 authored files regenerated in a temporary directory and matched exactly |
| Full Python quality script on 3.11 and 3.12 | Passed on each: 34 tests, PostgreSQL and SQLite migration drift, repeated CLI demo/export/evaluation, wheel + sdist builds |

Without `TEST_DATABASE_URL`, the PostgreSQL test is explicitly skipped (33 passing
tests); CI provides that variable. One installed Starlette version emits a TestClient
deprecation warning about httpx; it did not affect the verified requests or tests.

The normal online Docker build was attempted but Docker build-container DNS could
not reach package hosts. Workspace pip downloads worked with verification enabled.
The documented offline wheel bundle/Compose override restored a working Docker
build without disabling TLS, signatures or checksums. A writable Docker config
directory was also required because the default home directory is read-only.

Not executed / not implemented: paid OpenAI/Anthropic calls, real URL acquisition,
browser fallback, independent semantic hallucination or matching quality metrics,
actual A/B/C live experiments, GitHub-hosted CI, publication/deployment or restoration
in a fresh cloud task. These are not claimed as passing. See the scenario matrix.

The workflow now runs quality gates, Python 3.11/3.12 PostgreSQL checks and a normal
Docker/API smoke on pushes and PRs. The cloud proxy denied connections to
`api.github.com`, so this local evidence does not establish a remote Actions result.

Runtime DBs, package wheels, environments and generated exports remain ignored;
only authored samples and explicitly labelled fixture result artifacts belong in Git.
