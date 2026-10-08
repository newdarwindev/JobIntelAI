# Data model

| Table | Key / references | Stored information |
| --- | --- | --- |
| jobs | job_id PK; identity and nonnull official_url unique | Validated registry JSON, canonical identity/URL |
| posting_snapshots | id PK; job_id FK | Raw/clean content, URL, UTC time, hash, fetch status |
| extraction_runs | id PK; snapshot_id FK | Config, time, full validated extraction JSON |
| requirements | id PK; run_id FK | Typed requirement JSON with raw text, skill group, quote/offsets |
| skills | canonical PK | Versioned taxonomy record |
| candidate_evidence | id PK; profile_id index | Immutable submitted profile payload including explicit records/completeness |
| matches | id PK; requirement_id + candidate_evidence_id FKs | Status, explanation, sourced records, time |
| evaluation_runs | id PK | Config results, metric denominators, local elapsed time, null usage where absent |

The first migration is frozen generated SQLAlchemy DDL, not a call to current
`Base.metadata.create_all`. Schema migrations run separately from startup. FKs are
also enabled in SQLite service connections. Rows store JSON after Pydantic validation;
SQL does not currently validate those JSON schemas independently.

Profile submissions are stored as snapshot payloads, while requirement rows are
individually addressable. Preserve historical IDs across new migrations and query
changes. Revision and predicate implementation requirements live in [issue #5](https://github.com/newdarwindev/JobIntelAI/issues/5).

Snapshot immutability is enforced by supported service behavior (no update/delete
endpoint); this service contract does not guarantee protection against direct SQL writes.
Do not claim a database-level guarantee. New source snapshots exclude stale runs
from current views. Re-extraction appends runs; analytics selects only the latest.
