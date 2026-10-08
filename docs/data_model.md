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

Current profile storage is one snapshot payload per matching request, rather than
one row per evidence record; requirement rows are individually addressable. Target
v1 can split evidence into indexed rows and promote type/skill/filter fields to
columns in new migrations when queries justify it. Preserve historical IDs.

Snapshot immutability is enforced by supported service behavior (no update/delete
endpoint); direct SQL writes are not guarded by a DB trigger in this scaffold.
Do not claim a database-level guarantee. New source snapshots exclude stale runs
from current views. Re-extraction appends runs; analytics selects only the latest.
