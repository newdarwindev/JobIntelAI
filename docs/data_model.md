# Data model

| Table | Key / references | Stored information |
| --- | --- | --- |
| jobs | job_id PK; identity and nonnull official_url unique | Validated registry JSON, canonical identity/URL |
| posting_snapshots | id PK; job_id FK | Raw/clean content, URL, UTC time, hash, fetch status |
| acquisition_attempts | id PK; job_id + nullable snapshot_id FKs; unique fetch_id/sequence | Original/requested/final URL, UTC time, status/HTTP/error/retryability, redirect/retry/wait metadata and successful body hash/type/charset/size |
| extraction_runs | id PK; snapshot_id FK | Config, time, full validated extraction JSON |
| extraction_attempts | id PK; job_id + snapshot_id + nullable run_id FKs | UTC time, configuration, success/failure, safe error code and retryability; no source/provider/error body |
| requirements | id PK; run_id FK | Typed requirement JSON with raw text, skill group, quote/offsets |
| skills | canonical PK | Versioned taxonomy record |
| candidate_evidence | id PK; profile_id index | Immutable submitted profile payload including explicit records/completeness |
| match_runs | id PK; extraction_run_id + snapshot_id + profile_revision_id FKs | Immutable match result, source/profile hashes, assessment date and predicate explanations |
| matches | id PK; requirement_id + candidate_evidence_id + nullable match_run_id FKs | Status, explanation, sourced records, time |
| evaluation_runs | id PK | Config results, metric denominators, local elapsed time, null usage where absent |

The first migration is frozen generated SQLAlchemy DDL, not a call to current
`Base.metadata.create_all`. Schema migrations run separately from startup. FKs are
also enabled in SQLite service connections. Rows store JSON after Pydantic validation;
SQL does not currently validate those JSON schemas independently.

Candidate snapshot IDs are immutable revision IDs. Explicit imports reuse identical
validated payloads within a profile and append changed payloads. Requirements remain
individually addressable; each new match row links to its coherent match run. Legacy
matches retain nullable match-run references rather than invented provenance.
A match run binds an exact extraction/source and candidate revision, with hashes and
assessment date. Historical source/profile/match rows remain readable after changes.

Snapshot immutability is enforced by supported service behavior (no update/delete
endpoint); this service contract does not guarantee protection against direct SQL writes.
Acquisition history has the same supported-service immutability boundary. Failed
fetches commit attempts without changing sources; successful attempts link to the
saved/reused snapshot. Snapshot and attempt writes share one transaction. Reusing
a manual snapshot through HTTP retains its original status/time; the new attempt
records HTTP provenance separately. FKs and per-fetch sequence uniqueness are
verified on SQLite/PostgreSQL. Raw body text is stored only in usable snapshots,
not duplicated in attempt payloads; URLs/history remain private local data.
Do not claim a database-level guarantee. New source snapshots exclude stale runs
from current views. Re-extraction appends runs; analytics selects only the latest.

Expected API/CLI extraction failures append an outcome without changing successful
runs; successes link the new run. The extraction work uses a savepoint and the
attempt shares the outer transaction. SQLite service connections issue explicit
BEGIN so releasing a savepoint cannot commit work before the outer attempt write or
commit; failure regressions exercise this on SQLite/PostgreSQL. Legacy runs need no
invented attempts. Acquisition attempts now also retain server `recorded_at` for
ordering independently of injected/event clocks; legacy nulls use their original
event timestamp. Existing history is neither backfilled nor rewritten.

Analytics reads these immutable rows through shared window-function selection.
It does not store or overwrite a cached aggregate; refresh recomputes current
source/run/revision eligibility. See [coverage semantics](analytics.md).
