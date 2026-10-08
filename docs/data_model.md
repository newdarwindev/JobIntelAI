# Data model

| Table | Key / references | Stored information |
| --- | --- | --- |
| jobs | job_id PK; identity and nonnull official_url unique | Validated registry JSON, canonical identity/URL |
| posting_snapshots | id PK; job_id FK | Raw/clean content, URL, UTC time, hash, fetch status |
| extraction_runs | id PK; snapshot_id FK | Config, time, full validated extraction JSON |
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
Do not claim a database-level guarantee. New source snapshots exclude stale runs
from current views. Re-extraction appends runs; analytics selects only the latest.
