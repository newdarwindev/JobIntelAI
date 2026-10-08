# Persisted corpus analytics

`GET /analytics/skills` and `jobintel analytics` return the same JSON from saved
database rows, without invoking extraction, matching or any provider. The browser
uses this report for categories, gaps, coverage and corpus JSON downloads. Reports
are recomputed on read and sent with `Cache-Control: no-store`; no session gap cache
or new cached aggregate table determines the result.

## Source, revision and slice selection

Default selection is the latest snapshot per registered job and latest successful
extraction on that exact snapshot, using UTC timestamps then IDs as deterministic
tie breakers. An empty successful extraction remains eligible. New snapshots exclude
older source results; re-extraction excludes prior match runs. Failures never replace
usable sources/extractions or create successful empty results.

Select **both** `profile_id` and `profile_revision_id` to request gaps. For each
current extraction, the latest saved match run for that exact immutable revision is
eligible. A newer match for another revision does not replace it. No revision is
selected implicitly; missing/wrong revisions return 404, incomplete selection 422.
Repeated runs do not multiply jobs. Empty matched extractions count as matched jobs
even though they have no match rows or gap groups.

| Filter | Meaning |
| --- | --- |
| `applied=true/false` | Exact registry boolean; null is excluded from either filter |
| `remote=true` | Grounded schema-v2 `work_mode.value=remote` on selected extraction |
| `remote=false` | Grounded `hybrid` or `onsite`; null/legacy metadata is excluded |

Filters combine with AND. Every denominator is recomputed afterwards. Remote slices
exclude jobs without a grounded current extraction, including pending/failed/stale
sources. Unknown work mode is never interpreted as nonremote. The optional positive
response extension requires a future typed registry import field; free-form status
and notes do not establish that fact. Unsupported analytics query fields are rejected
with 422 rather than silently acting as a filter.

```bash
jobintel analytics
jobintel analytics --applied true --remote true \
  --profile-id synthetic-candidate --revision-id SAVED_REVISION_ID
```

The CLI emits exact API JSON to stdout; redirect private reports to ignored
`local_data/` or outside the checkout. API query names use `profile_revision_id`;
CLI uses `--revision-id`. Explicit provider environment settings do not cause
analytics to instantiate or call a provider. JSON retains source/profile/run links
and clean source/profile data through the shared export metadata; it is private
local output, not a public corpus report.

## Counts and denominators

Skill N is distinct jobs with a successful selected-source extraction. Skills count
once per job and once per job/type; type counts can overlap. ANY remains a separate
alternative group and its branches do not become independent MUST mentions. ALL
branches remain individual mentions. Category coverage counts each successful job
once per stored requirement category, with n, N, fraction and job IDs.

Gap N is **matched jobs for the selected revision/current extraction**, separately
reported as `matched_jobs_N`. Each group/state counts distinct jobs and keeps
COVERED/PARTIAL/MISSING/UNKNOWN separate. Group identity includes normalized wording,
sorted skill branches, operator, type/category, experience/production obligations,
explicit production predicate, years and normalized version constraints. Quote offsets
do not divide equivalent predicates; differing versions/obligations/types do. ANY/ALL
groups retain all branches. Duplicate contexts can put a job in multiple states for
a group; state counts are independent and are not asserted to partition gap N.
Categories can likewise overlap. These are corpus frequencies, not suitability scores
or labor-market estimates. Zero denominators produce null fractions, not invented 0%.

## Coverage accounting

`coverage.registered_total` is all registry jobs; `registered_selected` is the
filtered registry. `excluded = registered_total - registered_selected`. The following
**mutually exclusive** buckets sum to `registered_selected`, in this precedence:

| Bucket | Condition |
| --- | --- |
| successful | Current successful extraction with requirements |
| successfully_empty | Current successful extraction with zero requirements |
| acquisition_failed | No usable snapshot; latest saved acquisition attempt failed |
| pending_source | No snapshot or recorded acquisition failure |
| extraction_failed | Snapshot without current success; latest attempt on it failed |
| stale | Current snapshot has no successful extraction/failed attempt, but an older source was extracted |
| pending_extraction | Snapshot awaits extraction, without current failure or historical extraction |

`successful_N = successful + successfully_empty`; `pending` sums both pending
buckets; `failed` sums acquisition/extraction failure buckets. Stale is separate.
`unmatched = successful_N - matched_N`; without a selected revision all successful
jobs are unmatched. `success_fraction` divides by selected registry jobs and
`matched_fraction` divides matched jobs by successful N.

`latest_acquisition_failed` and `latest_extraction_failed` explicitly **overlap**
these buckets: a failed retry may coexist with a current usable source/extraction.
Extraction failures refer to the current snapshot; failures on older sources remain
in history and do not classify the new source. Acquisition ordering uses server
recording time, sequence and ID; legacy rows with unknown recording time use their
original event timestamp. History is not rewritten to invent chronology.

## Failure history and transactions

Expected API/CLI extraction failures append immutable `extraction_attempts` with
source/configuration/time, safe error code and retryability. Existing HTTP error
envelopes remain intact. Successful attempts link the new run; no body, provider
payload or exception text enters attempt rows or outcome logs. Missing jobs and
absent-source prerequisites remain 404/409 without attempts. History is readable in
`GET /jobs/{id}/history`; no supported history update/delete operation exists.

Extraction work uses a savepoint within the caller's transaction. Expected failures
roll that work back and commit only the failure outcome. SQL/attempt/outer-commit
failures roll everything back and return sanitized 503. SQLite uses explicit BEGIN
so savepoint release cannot commit before the outer transaction. Regression tests
verify the same behavior on SQLite and PostgreSQL. Legacy successful runs remain
eligible without fabricated attempt history; historical unrecorded failures cannot
be recovered. Direct `Service.extract` calls keep their exception/rollback contract;
the observed API and CLI extraction boundaries record attempts.

## Shared exports and verification

The shared selection/aggregation functions serve current and explicit historical
exports too. Export JSON/CSV accepts `remote`, and CLI export accepts `--remote`;
CSV provenance includes `remote_slice` alongside the applied slice. The original
seven-column legacy skills CSV stays available. Historical exports use their
explicit saved-source work-mode metadata; ordinary analytics always uses current
sources. See [exports.md](exports.md) for spreadsheet transformations.

Window queries bulk-select snapshots, successful runs, revision matches and latest
outcomes. SQL statement counts stay constant from one to 24 selected jobs on both
SQLite/PostgreSQL; processing and payload memory still scale with the selected corpus.
This is local single-user tooling, not a claim of large-scale performance.

V27–V30 tests use authored mixed corpora with failures, pending/empty/stale sources,
duplicates, ANY/ALL, two revisions and repeated runs. They check counts, nulls,
API/CLI equality, grounded slices, migrations and rollback. UI05 runs complete
desktop/mobile selection, refresh, failure-accounting and CSV journeys. No paid
calls or real private data enter CI, videos or public reports.
