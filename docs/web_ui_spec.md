# Mock web UI acceptance specification

## Scope decision — 2026-10-08

The user requested all required web interfaces, mocks, complete GitHub Actions
browser workflows, successful videos in README.md, and persistent agent rules.
This explicitly extends the original backend-only v1 scope. The original brief is
retained. The six screens below expose that backend's contracts; this extension
does not complete the live HTTP/OpenAI or portfolio experiment release gates.

The UI is dependency-free HTML/CSS/JavaScript served by FastAPI at `/ui/`. Mocking
happens at the existing `FixtureProvider` boundary: the browser calls real migrated
API/services with authored synthetic data. Domain logic is not replaced by static
success responses. Unknown fixture hashes fail explicitly. The demo launcher runs
Alembic before serving a disposable SQLite database, binds to loopback, and removes
the database on exit. Demo fixture/reset routes exist only with `demo=True`; the
normal API exposes neither. Candidate profiles and gap projections are held in
the current browser session; refreshing clears them and evaluation display state.
Job/snapshot/extraction persistence lasts for the lifetime of the demo server.

## Required interfaces and contracts

| Screen | Required behavior | Journey |
| --- | --- | --- |
| Overview | Empty onboarding, registry/success/pending counts, complete 20-posting replay, direct navigation | UI01, UI03, UI08 |
| Job registry | CSV/JSON import, typed applied state, atomic conflict/rejection, duplicates, search and pipeline filters | UI01 |
| Source & extraction | Manual text/HTML, URL stub/manual fallback, immutable hash/timestamp/URL, history, source-change invalidation, exact Unicode quote highlighting, MUST/PREFERRED/EXPERIENCE/OTHER, ANY/ALL, raw/normalized configurations, separate responsibilities, provenance JSON | UI02, UI03, UI07 |
| Candidate evidence | Strict sourced JSON, explicit completeness, separate capability/production axes, four states, contradiction abstention, ANY/ALL, selected/corpus matches, source-linked JSON export | UI04 |
| Corpus analytics | Successful latest-source n/N, explicit pending/excluded totals, applied slices, alternative groups, distinct-job category coverage, current-profile group gaps with UNKNOWN separate, JSON and formula-safe CSV with snapshot/run/profile provenance | UI05 |
| Evaluation lab | Select raw/normalized fixture configs, reject empty selection, frozen 20-posting comparison, precision/recall numerators/denominators, type/evidence denominators, null unavailable metrics, elapsed replay time, run ID and JSON export | UI06 |

All screens require visible busy/error/empty states, labelled controls, keyboard
access, responsive layouts, deep links to postings, and escaped untrusted content.
Failing mutations preserve the source/prior run, enable retry, and never show a
success-looking empty result. No third-party assets or hosted scripts are needed.
HTML is cleaned server-side and is never inserted as executable source markup.
The Unicode UI regression injects an authored API read fixture with an emoji
prefix; transport-error regressions inject transient HTTP/connection failures.
The rest of the browser pipeline uses the real fixture-backed service.

Category coverage and candidate gaps are **UI session projections** of real latest
extractions/matches, not newly persisted backend analytics. Gap denominator is
matched jobs in the current slice, with one count per job/group/state. Category
denominator is successfully extracted jobs in that slice. These do not promote
planned backend V27/V30 to complete. Applied slicing and formula-safe UI exports
are implemented; remote/positive-response slicing and live experiments are not.

## Executable coverage and evidence

`web_ui_workflows.json` is the machine-readable workflow inventory. Every ID maps
to one complete test in `tests/e2e/workflows.spec.mjs` and runs on desktop Chromium
and mobile Chromium. Unit/API regressions cover domain edge cases beneath these
journeys; listing an existing S/V scenario here is traceability, not promotion of
every target scenario. Passing journeys are executable acceptance evidence for the
mock UI only. No skipped/xfail tests count as delivery.

`npm run test:ui` records **all** attempts. `npm run record:ui` refuses incomplete,
failed, skipped, unmapped, or video-less suites; it selects only the successful
attempt for each workflow/project. Videos are copied to stable README-linked paths
with SHA-256, source-content hash, attempt index, timestamp, and local/Actions origin
in `docs/ui-recordings/manifest.json`. `npm run check:ui` rejects stale source
evidence, missing/corrupt videos, missing README links, and coverage mismatch.

The Actions workflow runs every journey on pushes, pull requests, and manual
dispatch, uploads reports/traces/videos even on failure, and supplies verified
README evidence only after all journeys pass. Trusted successful default-branch
pushes automatically commit the README/video refresh; pull requests and forks have
read-only permissions and downloadable evidence. Publishing needs repository
Actions write permission and a default branch allowing bot commits. If branch
protection rejects the push, the publishing job fails explicitly while the verified
artifact remains available; apply that artifact through the repository's approved
PR process. Never use `pull_request_target` to execute untrusted browser tests.
