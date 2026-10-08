# Saved-data export contract

`POST /exports`, `jobintel export` and browser evidence, match and corpus downloads
use `ExportService`. Exports read migrated saved data; they do not extract, match,
invoke a provider or print source/candidate contents. API downloads use `no-store`.

## Selection and provenance

The request selects `kind` (`skills`, `requirements`, `matches` or `evidence`) and
`format` (`json` or `csv`). Defaults are current `skills` JSON, all registered jobs
and no candidate selection. Optional `job_ids` restrict the corpus; `applied: true`
or `false` selects explicit registry values and excludes unknown metadata.

Current exports select the latest snapshot and its latest successful extraction
for each job. A new snapshot or extraction excludes older matching runs. To include
matches, select **both** `profile_id` and `profile_revision_id`; only the latest
match of that exact revision against the selected extraction is eligible. An
unmatched requirement has a null match state, while an evaluated unknown predicate
has the literal `UNKNOWN` state. Match exports require an explicit revision or
historical match-run selection. Evidence exports require exactly one `job_id` and
one source/run view.

Historical requests require `historical: true` and explicit `run_ids` and/or
`match_run_ids`. Match IDs imply their extraction and snapshot IDs; a selected
candidate revision must agree with every selected match. Extraction IDs without
`historical: true`, or history without IDs, are rejected. Job/applied filters still
apply. Historical counts merge selected runs by job and deduplicate repeated
requirements; separate source/run views and requirement/match rows remain auditable.

JSON includes schema version, selection, `N`, `matched_jobs_N`, registered-job count,
denominator description, source views and selected canonical candidate revisions.
`N` counts distinct jobs with successful selected-source extraction, including jobs
with no candidate requirements. `matched_jobs_N` counts distinct jobs with eligible
saved matching runs. Both recompute after filtering. Requirement/match records carry
job, immutable snapshot, clean/raw SHA-256, extraction configuration/provenance,
requirement, match and candidate revision/hash IDs, raw wording, exact Unicode
code-point offsets/quotes, obligations, versions, ANY/ALL operator, states and
candidate sources. JSON source views retain filters, responsibilities and sourced
metadata. CSV groups/versions/sources remain JSON arrays/objects in one cell, so an
ANY group is never split into independent MUST rows.

Skills JSON keeps alternatives separate from independent skill counts. Skills CSV
keeps the original seven columns first and appends slice/source/run/profile
provenance. Requirement/match CSV has one row per saved requirement and eligible
match; unmatched requirements appear only in requirement/evidence exports. A
successful empty extraction has no requirement rows. JSON retains its denominator
and any eligibility-only match run; header-only CSV intentionally invents no rows.
Use the companion JSON to retain metadata for an empty CSV.

## Spreadsheet transformation

JSON preserves exact authored strings and nulls. CSV is UTF-8, quotes every field,
uses CRLF records, and prefixes a single apostrophe to any cell whose first visible
character is `=`, `+`, `-` or `@`, including after leading whitespace, Unicode
control or format characters. The original characters follow the apostrophe
unchanged. This applies to every column, including company, role, raw quote, skill,
source URL, candidate ID and explanation. Nested objects are serialized as JSON;
their field values stay inside that inert structured cell. Booleans use JSON
`true`/`false`; null and empty strings both become empty CSV cells. `UNKNOWN` stays
a literal state. Use JSON when distinguishing null from empty or recovering exact
strings matters; do not strip the protective apostrophe before spreadsheet import.

## API and CLI examples

```json
{"kind":"requirements","format":"csv","applied":true}
```

```json
{"kind":"matches","profile_id":"saved-profile","profile_revision_id":"saved-revision"}
```

```json
{"kind":"matches","historical":true,"match_run_ids":["saved-match-run"]}
```

```bash
jobintel export --kind requirements --applied true --output results/generated
jobintel export --kind matches --profile-id saved-profile --revision-id saved-revision
jobintel export --kind matches --historical --match-run-id saved-match-run
jobintel export --kind evidence --job-id SYN-01
```

The CLI writes both `<kind>.json` and `<kind>.csv` from one selected report.
`--job-id`, `--run-id` and `--match-run-id` may be repeated. `jobintel export` without
`--kind` preserves the `skill_counts.json`/`skill_counts.csv` filenames and exact
original seven-column CSV interface. The API also offers `legacy_skills_csv: true`
for that compatibility interface; JSON still contains complete provenance.

Generated exports can contain private posting and candidate data. CLI paths inside
the checkout must be ignored (`results/generated/` or `local_data/`); paths outside
the checkout are allowed. Browser downloads use the user's local download folder.
Installed distributions and containers outside a checkout do not require Git.
Inside a checkout, Git must be available to verify that the output is ignored.
Only synthetic public fixtures belong in Git or CI evidence.

V31–V32 regressions: `tests/integration/test_exports.py` and
`tests/unit/test_export_csv.py`. UI03/UI04/UI05 verify actual downloads through this
contract; UI05 checks persisted selection after refresh, API equivalence, slicing,
formula handling and explicit stale-run history. These exports do not complete the
analytics coverage contract. Remote filtering now uses grounded selected-source
work-mode metadata in both JSON/CSV and CLI `--remote true|false`; unknown metadata
is excluded. `remote_slice` is included in CSV provenance. The optional positive
response extension needs an explicitly typed import field and is not inferred from
free-form status. See [the shared analytics contract](analytics.md).
