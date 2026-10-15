# Bounded read API

The browser uses the explicit `/v2` catalogue contract. Existing `/jobs`, job
history, candidate-revision and evaluation-list responses remain compatible for
existing API/CLI clients; those legacy bulk reads are not used for navigation.

All v2 lists default to 20 items and accept `limit=1..100` and an opaque `cursor`.
Responses identify `catalogue_version: 2`, `page.limit`, `page.has_more` and
`page.next_cursor`. Use that cursor with the same selection for the next page;
changing the limit is allowed. Malformed cursors, invalid limits, unknown query
parameters and reuse with another collection, owner, search or filter return 422.
An empty page has no next cursor. Cursors contain identifiers, never source,
profile or prediction bodies. They are untrusted selections, not authorization.

| Endpoint | Bounded content and order |
| --- | --- |
| `GET /v2/jobs` | `jobs`: registry metadata, latest snapshot ID/hash/time, latest run ID/configuration/requirement count; job ID ascending |
| `GET /v2/jobs/{job}/snapshots` | `items`: snapshot metadata and run count; fetched time and ID descending |
| `GET /v2/jobs/{job}/acquisition-attempts` | `items`: saved acquisition identities, URLs and typed outcomes; created time and ID descending |
| `GET /v2/jobs/{job}/extraction-attempts` | `items`: saved extraction identities, configuration and typed outcomes; created time and ID descending |
| `GET /v2/jobs/{job}/snapshots/{snapshot}/runs` | `items`: run identity/configuration/schema/count; created time and ID descending |
| `GET /v2/candidates/{profile}/revisions` | `items`: revision identity/profile/time; created time and ID descending |
| `GET /v2/evaluation-runs` | `items`: evaluation identity/dataset/status/time; created time and ID descending |

The unique ID breaks timestamp ties. Keyset comparisons avoid offset drift when
newer append-only history is added between pages. Pages are fresh reads, rather
than a frozen database snapshot: new older/backdated records can appear later;
refresh from the first page to discover new leading records. Registry predicates
are evaluated at each read, so source/extraction changes may change membership.

Registry `q` is a literal case-insensitive substring of job ID or normalized
company/role identity; `%` and `_` are literal characters. `pipeline` is `all`,
`Awaiting source`, `Source ready` or `Extracted`. This preserves the existing
three-state navigation classification; detailed attempt/coverage semantics are
specified separately. `totals` always covers the entire registry, independently
of page/search/filter: registered, snapshotted, extracted and requirements.
Successful empty runs count as extracted. A newer source invalidates the current
run; historical runs never become current through pagination.

Windowed latest-source/latest-run selection and indexed requirement counts avoid
per-posting detail reads. The registry executes two SELECT statements regardless
of page/corpus size (SQLite also emits its explicit BEGIN). Neither statement
selects raw/clean source text or extraction payloads. Histories and catalogues
select metadata columns and at most `limit + 1` rows, without nested unbounded
run lists or candidate/prediction payloads.

The selected workbench/candidate posting uses `GET /jobs/{id}` for current detail.
`GET /v2/jobs/{job}/snapshots/{snapshot}` loads one exact saved clean source;
`GET /v2/extraction-runs/{run}` loads one full saved extraction. Existing exact
revision, evaluation and export endpoints retain their contracts. Snapshot/run
listing verifies the job/snapshot relationship; unknown or mismatched resources
return 404. No list call invokes a provider or changes stored records.

The browser exposes registry next/previous/first controls and reloadable
search/filter/cursor routes. A posting selected outside the current page remains
available in the bounded selector. Snapshot, run, acquisition, candidate-revision
and evaluation pages retain cursor identities and one visible page; only explicit
snapshot/revision/evaluation inspection reads the selected body. Draft preservation
and durable mutation recovery still apply during page navigation. Corpus batches
enumerate compact summary pages only when the user explicitly starts/replans the
batch; the 20-item execution bound and completed-operation exclusion are unchanged.

Performance evidence must identify both algorithms: legacy compatible bulk reads
versus bounded v2 summaries on identical migrated synthetic corpora. Include
SQLite and PostgreSQL query/response counts, page sizes and source/run provenance.
