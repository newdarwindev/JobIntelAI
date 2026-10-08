# Validation evidence

## Mock web UI extension — 2026-10-08

Executed against the authored synthetic fixtures and a disposable migrated API.
The existing backend-first evidence below is retained.

| Check | Observed result |
| --- | --- |
| Python suite, including disposable PostgreSQL 16 | **38 passed, 0 skipped, 0 failed** |
| Complete Playwright suite | **16 passed, 0 skipped, 0 failed, 0 retries** in GitHub Actions and the final local replay — UI01–UI08 on desktop/mobile Chromium |
| Recording selection regression tests | **6 passed** — failed/skipped/incomplete/expected-failure/video-less runs refused; only successful retry selected |
| Successful video publication | **16 videos** in `docs/ui-recordings/`, all README-linked; GitHub Actions origin, source/run provenance and source/video SHA-256 in manifest |
| Video decoding | All 16 verified with ffprobe; desktop 1440×1000, mobile 412×914 (encoder rounds the 915-pixel viewport to an even height) |
| Evidence-integrity gate | Passes current source and video hashes; rejects deliberately stale provenance and corrupt video bytes; originals restored |
| Mock UI functional coverage | Atomic CSV/JSON import, duplicates/conflicts, HTML cleaning/manual URL fallback, immutable source history/stale invalidation, normalized/raw aliases, ANY/ALL, Unicode including non-BMP injected read fixture, four match states, production/tenure abstention, corpus slices/gaps/exports, evaluation/nulls, failures/retry, keyboard/mobile/inert input |
| Offline CLI regression | 20 synthetic postings processed; N=20; evaluation compares two configurations |
| Wheel packaging | Successful; HTML, CSS and JavaScript included in built wheel |
| Actions configuration | YAML parsed; test job has read-only access; trusted default-branch publishing job has scoped contents write; checksum-verified actionlint passed; read-only test job passed; trusted default-branch publisher is intentionally skipped on PR runs |

Actions recorded Chromium **145.0.7632.6** from pinned Playwright 1.58.2.
Browser version **151.0.7922.173** was selected from the installed local Chromium.
The checked-in Playwright config defaults to the pinned Playwright browser in
Actions; `UI_BROWSER_PATH` selected the local binary here. The local recorder used
the installed FFmpeg through a checkout-local Playwright browser-cache path. No
private data, live crawling, paid provider calls, or deployed service was used.
Implementation acceptance and remaining release work are tracked in GitHub issues. The implementation was integrated with the repository's newer
quality scaffold without replacing its checks. The first incremental commit
passed [all repository checks on GitHub](https://github.com/newdarwindev/JobIntelAI/actions/runs/37772935880),
including Python 3.11/3.12 PostgreSQL, packaging and normal Docker/API smoke.

A post-integration local replay initially finished with 15 passed and one desktop
UI08 `apiRequestContext.get` socket disconnect. The trace showed the inert-input
assertions passed before the connection error. That failed suite was retained as
diagnostics and was not published. The complete unchanged suite then passed locally
without retries; Actions independently passed all 16 without retries.

[Browser Actions run 37773290905](https://github.com/newdarwindev/JobIntelAI/actions/runs/37773290905)
passed all 16 journeys and six recording-selection tests, and published only successful
attempts. Its verified `successful-web-ui-recordings` artifact (ID 11549130362,
SHA-256 `ec2a3a2ea6e46d8233de2dd7ee90f2e76fc1c7fd19ff01cbbc05d3dfeba91cff`)
was downloaded and applied to README plus `docs/ui-recordings/`. The integrity gate
passed against the final source hash; all 16 Actions videos passed ffprobe checks.
The manifest uses GitHub's PR merge SHA and records the originating run URL.

[Repository Actions run 37773291088](https://github.com/newdarwindev/JobIntelAI/actions/runs/37773291088)
passed Ruff/format/C901, ShellCheck, actionlint, full Python quality checks on both
3.11 and 3.12 (**38 passed each**, PostgreSQL plus migrations/CLI/packaging), and the
normal Docker Compose / actual HTTP API smoke. No failing test was removed or relaxed.
The PR's publisher stays read-only by design; the verified recordings were applied
in an explicit evidence commit. Future trusted default-branch pushes run the automatic
publication job, subject to the repository's branch policy.

The final local commands were:

```bash
TEST_DATABASE_URL=postgresql+psycopg://jobintel:ci-only@127.0.0.1:55432/jobintel_test \
  .venv/bin/python scripts/check.py --require-postgres
npm run test:recordings
PLAYWRIGHT_BROWSERS_PATH="$PWD/work/playwright-browsers" \
  UI_BROWSER_PATH=/usr/bin/chromium npm run test:ui
npm run record:ui
npm run check:ui
```

The disposable PostgreSQL test container was stopped and removed after validation.

## Earlier backend scaffold validation

Executed in the cloud workspace on 2026-10-08 with Python 3.12.14 and 3.11.16. This historical record describes that local run; later remote runs are linked above.

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

Remaining implementation and experiment acceptance are tracked in [the issue map](implementation_plan.md).
Historical checks above establish only the behavior exercised by those recorded runs.

The workflow now runs quality gates, Python 3.11/3.12 PostgreSQL checks and a normal
Docker/API smoke on pushes and PRs. The cloud proxy denied connections to
`api.github.com`, so this local evidence does not establish a remote Actions result.

Runtime DBs, package wheels, environments and generated exports remain ignored;
only authored samples and explicitly labelled fixture result artifacts belong in Git.
