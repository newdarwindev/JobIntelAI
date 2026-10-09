# Mock web UI acceptance specification

## Scope decision — 2026-10-08

The user requested all required web interfaces, mocks, complete GitHub Actions
browser workflows, successful videos in README.md, and persistent agent rules.
This explicitly extends the original backend-only v1 scope. The original brief is
retained. The six screens below expose that backend's contracts; this extension
does not establish live model quality or complete portfolio experiment release gates.

The UI is dependency-free HTML/CSS/JavaScript served by FastAPI at `/ui/`. Mocking
happens at the existing `FixtureProvider` boundary: the browser calls real migrated
API/services with authored synthetic data. Domain logic is not replaced by static
success responses. Unknown fixture hashes fail explicitly. The demo launcher runs
Alembic before serving a disposable SQLite database, binds to loopback, and removes
the database on exit. Demo fixture/reset routes exist only with `demo=True`; the
normal API exposes neither. Candidate imports append immutable revisions in the local database. The browser
stores only the explicitly selected profile/revision IDs and reloads that revision
after refresh. Individual match display cards are cleared on refresh. The selected
evaluation run ID also reloads its saved report after refresh; private report bodies
are not copied into browser storage. Saved match runs remain readable by their IDs.
Job/snapshot/extraction persistence lasts for the lifetime of the demo server.

## Required interfaces and contracts

| Screen | Required behavior | Journey |
| --- | --- | --- |
| Overview | Empty onboarding, registry/success/pending counts, complete 20-posting replay, direct navigation | UI01, UI03, UI08 |
| Job registry | CSV/JSON import, typed applied state, atomic conflict/rejection, duplicates, search and pipeline filters | UI01 |
| Source & extraction | Manual text/HTML, bounded URL acquisition/manual recovery, immutable hash/timestamp/URL, source/extraction/attempt history, source-change invalidation, exact Unicode quote highlighting, MUST/PREFERRED/EXPERIENCE/OTHER, ANY/ALL, raw/normalized configurations, separate responsibilities, provenance JSON | UI02, UI03, UI07 |
| Candidate evidence | Strict sourced JSON, immutable revision save/reload/select, separate completeness and capability/production axes, dated tenure and exact-scope eligibility, four states, contradiction abstention, ANY/ALL, selected/corpus matches, source-linked backend JSON/CSV export | UI04 |
| Corpus analytics | Saved latest-source n/N, mutually exclusive coverage and explicit failure overlaps, applied/grounded remote slices, alternatives, distinct-job categories and revision-selected group gaps after refresh, JSON and formula-safe CSV with source/run/profile provenance | UI05 |
| Evaluation lab | Select raw/normalized fixture configs, reject empty selection, original 20-case regression and frozen 25-case source-reviewed benchmark, explicit metric counts, semantic/abstention/matching metrics, null unavailable measurements, per-case failures, report reload after refresh and by ID, JSON export | UI06 |

UI06 must identify exported results as fixture replay rather than live model
quality. The separate `jobintel experiment` CLI preserves `/evaluate` and cannot
enable paid browser calls. The journey checks the exported mode and null usage/cost. Original regression
semantic/abstention metrics remain null. The source-reviewed benchmark displays
reviewed counts, successful-case scope, matching on gold requirements, and five
unsupported replay inputs as preserved failures. It reloads both reports without
new extraction requests; fixtures cannot establish live quality.

UI03 inspects schema-v2 geography/work-mode/filter values with exact source quotes,
highlights metadata evidence, exports explicit version comparators with raw wording,
and verifies that preferred production experience is displayed as preferred.
Experience obligation is shown separately from requirement type and years.
UI04 verifies that a versioned requirement remains UNKNOWN until sourced candidate
version predicates are supported. Missing or ambiguous metadata is shown as unknown.

All screens require visible busy/error/empty states, labelled controls, keyboard
access, responsive layouts, deep links to postings, and escaped untrusted content.
Failing mutations preserve the source/prior run, enable retry, and never show a
success-looking empty result. No third-party assets or hosted scripts are needed.
HTML is cleaned server-side and is never inserted as executable source markup.
The Unicode UI regression injects an authored API read fixture with an emoji
prefix; transport-error regressions inject transient HTTP/connection failures.
The rest of the browser pipeline uses the real fixture-backed service.

UI02 calls the actual bounded acquisition/service contract through an explicitly
synthetic HTTP transport and DNS resolver in the demo. It follows an authored redirect,
persists an HTML source with the known SYN-01 clean hash, extracts it and verifies
that its script never executes. Authored 403 and JS-only responses save failure
history while preserving the prior usable source/extraction and unsaved manual
editor text. Reload retains the attempt IDs, original/requested/final URLs, UTC
timestamps, status/error codes and snapshot references; manual save/extract recovers.
`/ui/config` identifies `acquisition_mode=synthetic` for the demo and `http` for
the normal API. The normal API uses the pinned HTTP adapter described in
[acquisition.md](acquisition.md). SSRF, TLS, deadlines, body limits and transactional
edge cases are backend fake-transport regressions, not claims of real URL access
from the browser videos. Rendering and anti-bot bypass are excluded.

Category coverage and candidate gaps come from shared persisted backend selection,
including after refresh. The gap denominator is jobs with an eligible saved match
for the explicit revision/current extraction, distinct from successful-extraction N.
Empty successes count in N and matching an empty extraction counts as a matched job.
Group identity retains type, ANY/ALL, obligations, years and versions; UNKNOWN stays
separate from MISSING. UI05 changes candidate revisions without overwriting either
revision's matches, and verifies identical refreshed backend/download JSON.

UI05 displays mutually exclusive source/extraction coverage buckets, unmatched jobs,
excluded registry totals and explicit overlapping latest-attempt failure counts.
It checks authored acquisition/extraction failures and source-change staleness.
Applied and grounded remote/hybrid/onsite slices recompute every denominator and
exclude unknown metadata. Corpus JSON uses `/analytics/skills`; CSV still uses the
shared export service with identical slice/revision selection. Positive-response
slicing needs a future typed registry field and is outside this optional extension;
free-form status/notes never imply a positive response. Live experiments are separate.
See [the analytics contract](analytics.md) for query and bucket semantics.

UI03 compares evidence JSON with the shared API and requires persisted requirement
IDs. UI04 downloads formula-safe match CSV and verifies equality with the API for
the selected saved revision. UI05 compares corpus JSON and skills/requirement CSV
downloads with the shared API, verifies profile/snapshot/run and slice provenance,
and checks that a selected posting's match export is independent of corpus slices,
retains persisted match counts after refresh, and excludes stale-source extraction.
An explicit historical run selection recovers the original source requirements.
The [export contract](exports.md) documents JSON nulls, CSV transformations and
legacy skills compatibility. V31–V32 backend tests establish CLI equivalence.

## Executable coverage and evidence

UI01 also submits a different job ID with a case/default-port/fragment variant of
an existing official URL. The UI shows 409 and the whole batch is absent, including
its earlier valid row. The saved registry entry remains available after reload (V01).

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
read-only permissions and downloadable evidence. Publication commits use the Git
display name `Stefan Novak` and retain the automation email address for provenance.
Publishing needs repository
Actions write permission and a default branch allowing bot commits. If branch
protection rejects the push, the publishing job fails explicitly while the verified
artifact remains available; apply that artifact through the repository's approved
PR process. Never use `pull_request_target` to execute untrusted browser tests.


UI03 also exports the provider/configuration/schema/taxonomy/source identity and
null fixture usage. UI07 exercises typed 422 refusal, 502 quota and 504 timeout
responses, shows retryability, and verifies that the prior extraction remains
current. These error envelopes are authored browser mocks; adapter and atomic
persistence contracts are exercised with fake transports in backend tests.
The synthetic launcher remains fixture-only. OpenAI is selected explicitly through
API/CLI setup; paid live execution and model quality need separate authorization.

UI04 saves multiple synthetic revisions, refreshes the page, re-matches the selected
revision, selects an older revision without overwriting it, and inspects the persisted
match-run identity. Dated tenure satisfies the years predicate; location evidence is
shown with the job quote and candidate source. Version predicates remain unsupported.
Revision selection clears current projections. Matching sends the selected revision
ID and inspected extraction ID; stale extraction selections fail with 409 and preserve
history. Missing saved revisions are reported; the browser never silently selects a
newest revision after a saved selection disappears.
