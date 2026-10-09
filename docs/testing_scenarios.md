# Acceptance scenarios and traceability

Stable S/V IDs provide regression traceability. Implementation acceptance and
remaining work are maintained in [GitHub issues](implementation_plan.md), rather
than executable/planned status tables. Live model experiments require explicit
paid-call authorization; fast CI uses fake transports/providers.

V38 harness regressions in `tests/unit/test_experiments.py` verify frozen inputs,
configuration separation, budget rejection, failure preservation, saved-prediction
rescoring and public-report safeguards. Live reports/reviewer audit are separate
evidence in issue #9.

## Regression references

V20/V33-V37 regressions in `unit/test_reviewed_evaluation.py` and
`integration/test_evaluation_reports.py` cover frozen source annotations, exact
metric counts, semantic/alias/span distinctions, abstentions, filters, responsibilities,
four-state matching, pricing/usage, typed failures and historical API/CLI reports
on migrated SQLite/PostgreSQL. UI06 covers reviewed diagnostics and report reload.

V27–V30 regressions in `unit/test_corpus_analytics.py` and
`integration/test_corpus_analytics_boundary.py` cover mixed failed/pending/empty/stale
sources, duplicate mentions/categories, ANY/ALL, distinct four-state groups, explicit
revisions and repeated source/extraction/match runs. They verify exact API/CLI JSON,
applied and grounded work-mode slices, null zero denominators, constant query counts
on SQLite/PostgreSQL, migration preservation and outer rollback after savepoint
success. UI05 verifies saved categories/gaps after refresh, two revisions, typed
remote slices, failure accounting, stale exclusion and shared CSV selection. Positive
response is not inferred from free-form status; its optional typed import extension
is outside this slice. The [analytics contract](analytics.md) defines every bucket
and overlap; no unavailable historical failure counts are invented.

V02–V07/V09–V11 regressions in `unit/test_acquisition.py`,
`unit/test_fetch_transport.py`, `unit/test_acquisition_cleaning.py` and
`integration/test_acquisition_boundary.py` use authored fake HTTP/DNS/socket responses.
They cover public IPv4/IPv6 pinning and mixed/rebound DNS rejection before HTTP,
proxy refusal without direct fallback, verified TLS, deadlines/retries/redirects,
compression and text limits, access-gate/manual recovery, ATS/table/list/malformed
cleaning, unchanged-clean/different-raw provenance, and atomic attempt/source writes
on migrated SQLite/PostgreSQL. Supported mutation requests are rejected; direct SQL
immutability is not claimed. UI02 exercises redirect success, inert HTML, 403/JS-only
failure history, preserved extraction/unsaved manual text and manual recovery on both
browser projects. Real authorized URL smoke is separate; optional rendering V08 is
excluded. See [the acquisition contract](acquisition.md).

V01/V39-V42 regressions in `integration/test_persistence_privacy.py` exercise
canonical-URL batch atomicity, SQL failures after writes, mid-match/provider failures,
unreachable readiness, migration downgrade/re-upgrade, foreign keys and source/profile
provenance on migrated SQLite and disposable PostgreSQL. Outcome logging waits for
transaction commit and excludes private fields, parameters and exception text.
V43-V44 regressions in `unit/test_ci_evidence.py` and `scripts/check_evidence.py`
check leaf JUnit counts, deliberately failing diagnostic publication, licensed
source/wheel contents and exclusion of private runtime files. These probe skips
test skip reporting only and do not establish any feature acceptance.

V19/V21-V23 regressions are in `unit/test_extraction_v2.py` and
`integration/test_extraction_boundary_v2.py`. They cover non-BMP metadata offsets,
irrelevant/company evidence, independent obligations, version branches, alias
collisions/deduplication, and atomic failures/legacy reads on migrated SQLite and
PostgreSQL. UI03/UI04 inspect the corresponding evidence and abstention contracts.

| ID / brief area | Given → when → expected | Test location |
| --- | --- | --- |
| S01 / registry | CSV with required headers + `applied=false` → import → typed false, optional fields unknown | unit/test_registry_normalization.py |
| S02 / registry | Missing header or invalid applied value → parse → reject, no guessed metadata | unit/test_registry_normalization.py |
| S03 / registry | Host case/default port/fragment → normalize → canonical identity; preserve query/path case/slash | unit/test_registry_normalization.py |
| S04 / registry | Non-HTTP, credentials or unsupported port → validate → reject | unit/test_registry_normalization.py |
| S05 / registry | Same full CSV twice → import → second batch reports 20 duplicates | integration/test_api.py |
| S06 / registry | Same ID with changed metadata → import → 409, no overwrite | integration/test_api.py |
| S07 / registry | Batch creates two casefold-equivalent company/role rows → conflict → entire batch rolled back | integration/test_api.py |
| S08 / cleaning | HTML includes nav/script/cookies/footer and main content → clean → retain description only | unit/test_grounding.py |
| S09 / snapshots | Same raw text and URL submitted twice → snapshot → same ID/hash | integration/test_api.py |
| S10 / source isolation | New snapshot after extracted source → read/analytics → prior extraction not reused; matching blocked | integration/test_api.py |
| S11 / schema | Missing evidence, unknown extra fields, invalid confidence/years/group → parse → validation error | unit/test_grounding.py |
| S12 / evidence | Unicode source and exact code-point offsets → validate → pass; shifted source fails | unit/test_grounding.py |
| S13 / evidence | Invented raw wording or unmatched source quote → validate → reject | unit/test_grounding.py |
| S14 / normalization | Postgres/K8s/GenAI aliases → canonicalize → PostgreSQL/Kubernetes/Generative AI | unit/test_registry_normalization.py |
| S15 / normalization | AWS and AWS Bedrock; unknown version string → normalize → remain distinct/preserved | unit/test_registry_normalization.py |
| S16 / provider boundary | Golden file absent but replay responses present → extract → succeeds without reading gold | unit/test_analytics_evaluation.py |
| S17 / provider boundary | Unseen posting → fixture extract → explicit error/501, never fabricated result | unit/test_analytics_evaluation.py; integration/test_api.py |
| S18 / production match | Strong + confirmed, production required → match → COVERED with source | unit/test_matching.py |
| S19 / production match | Strong + limited/none production, production required → match → PARTIAL | unit/test_matching.py |
| S20 / historical match | Basic current capability + confirmed historical production → match → PARTIAL | unit/test_matching.py |
| S21 / unknown match | Required axis unknown, conflicting records → match → UNKNOWN | unit/test_matching.py |
| S22 / missing match | No skill evidence, incomplete profile → UNKNOWN; explicitly complete → MISSING | unit/test_matching.py |
| S23 / alternatives | Candidate knows only one branch → ANY COVERED; ALL with missing branch MISSING | unit/test_matching.py |
| S24 / unsupported predicates | Years/OTHER requirement but only skill evidence → match → UNKNOWN | unit/test_matching.py |
| S25 / counts | Duplicate mentions and must/preferred overlap in one of two jobs → counts → overall 1/2, each type 1/2 | unit/test_analytics_evaluation.py |
| S26 / alternatives counts | AWS OR Azure requirement → analytics → separate group, no independent branch MUST counts | unit/test_analytics_evaluation.py |
| S27 / empty corpus | No successful extraction → analytics → N=0, no invented percentages | unit/test_analytics_evaluation.py |
| S28 / eval alignment | Duplicate predicted requirement + wrong type → score → precision 1/2, recall 1, type accuracy 0 | unit/test_analytics_evaluation.py |
| S29 / eval missing | Gold requirement but empty predictions → score → recall 0, undefined precision null | unit/test_analytics_evaluation.py |
| S30 / eval evidence | Predicted exact-key item with invalid evidence → score → unsupported span 1, evidence accuracy 0 | unit/test_analytics_evaluation.py |
| S31 / eval honesty | Fixture suite → evaluate → 20 cases, two configs, tokens/cost null | integration/test_api.py |
| S32 / API pipeline | Migrated SQLite → import, snapshot, extract, match → exact source trace and two match states | integration/test_api.py |
| S33 / API errors | Missing job/prerequisite/malformed payload → call → 404/409/422 | integration/test_api.py |
| S34 / fetch recovery | Official URL denies access → bounded fetch → typed 403, saved attempt, manual fallback, prior source preserved | integration/test_api.py; integration/test_acquisition_boundary.py |
| S35 / PostgreSQL | Disposable DB → Alembic upgrade + full source/extraction path → tables and API work | integration/test_postgres.py (opt-in locally; required in CI) |
| S36 / health | Database connected but unmigrated → health → 503 | integration/test_boundaries.py |
| S37 / persistence boundary | Replaceable provider returns invalid quote → service extract → no new rows; prior run preserved | integration/test_boundaries.py |

V12–V19 provider regressions are in `unit/test_openai_provider.py`,
`unit/test_openai_semantics.py`, and `integration/test_openai_boundary.py`.
They use fake Responses transports for strict schema/refusal/retry/Unicode/errors,
independent authored semantic cases, concurrent request provenance, explicit
configuration, API/CLI parity, migrated SQLite/PostgreSQL persistence and atomic
failure. UI03 exports identity and UI07 verifies typed errors and preserved runs.
Paid execution and measured live semantic quality belong to issue #9.

V24–V26 regressions are in `unit/test_candidate_predicates.py` and
`integration/test_candidate_revisions.py`: inclusive years/ranges, merged overlapping
periods, missing dates, source contradictions, production/current capability separation,
exact-scope eligibility and dated validity, immutable revision reuse, stale extraction
selection, migration preservation and atomic rollback on SQLite/PostgreSQL. UI04 saves,
reloads, selects and re-matches synthetic revisions with match-run provenance.

## Implementation acceptance in GitHub issues

V31–V32 regressions in `integration/test_exports.py` and `unit/test_export_csv.py`
cover current/explicit historical selection, saved candidate revisions, repeated and
stale runs, successful empty extractions, applied denominators, ANY/ALL and version/
obligation preservation, API/CLI equality, CSV provenance resolution, exact JSON,
Unicode/CSV boundaries and formula prefixes after whitespace/control characters.
Export query counts are bounded across corpus sizes; private generated paths must
be ignored. UI03/UI04/UI05 verify backend download parity, refresh persistence,
source-change exclusion and explicit historical recovery.

| Issue | Acceptance area | Original scenario IDs |
| --- | --- | --- |
| [#2](https://github.com/newdarwindev/JobIntelAI/issues/2) | Ground extraction metadata, experience obligation, and version predicates in source evidence | V19, V21–V23 |
| [#3](https://github.com/newdarwindev/JobIntelAI/issues/3) | Implement bounded HTTP acquisition with auditable outcomes and manual fallback | V02–V11; optional V08 excluded |
| [#4](https://github.com/newdarwindev/JobIntelAI/issues/4) | Implement a structured OpenAI adapter and versioned provider configuration | V12–V19 |
| [#5](https://github.com/newdarwindev/JobIntelAI/issues/5) | Persist reusable candidate revisions and match sourced tenure and eligibility predicates | V24–V26 |
| [#6](https://github.com/newdarwindev/JobIntelAI/issues/6) | Implement persisted corpus gap analytics, coverage accounting, and explicit slices | V27–V30 |
| [#7](https://github.com/newdarwindev/JobIntelAI/issues/7) | Expose provenance-preserving backend requirement and match exports with spreadsheet safety | V31–V32 |
| [#8](https://github.com/newdarwindev/JobIntelAI/issues/8) | Build an independent golden evaluation with semantic, abstention, matching, and operations metrics | V20, V33–V37 |
| [#9](https://github.com/newdarwindev/JobIntelAI/issues/9) | Run and publish at least two authorized live extraction experiments on a frozen corpus | V38 |
| [#10](https://github.com/newdarwindev/JobIntelAI/issues/10) | Complete persistence and privacy regressions and publish backend CI test evidence | V01, V39–V44 |

The linked issues retain the required behaviors, boundary cases, test requirements
and evidence needed for closure. Use their V IDs in new test docstrings. Optional
browser rendering V08 and optional provider V45 are outside the required issue set.

## Manual release review

Verify README architecture, example trace, data model, schema, real experiment table,
counts with n/N, trade-offs, privacy and next steps. Do not add the suggested résumé
claim until this behavior exists and the repository is published. An uploaded brief
or planned scenario is not evidence of implementation.

Add meaningful executable regressions that fail on incorrect behavior, retain their
stable IDs, and attach actual results to the implementing issue/PR. Do not use empty,
permanently skipped or xfail tests as implementation evidence.

## Mock web UI workflows

The authorized UI extension has a separate acceptance contract in
[web_ui_spec.md](web_ui_spec.md) and ID map in `web_ui_workflows.json`. UI01–UI08
exercise full registry, capture/history, evidence, matching, analytics/export,
evaluation, failure recovery and accessible navigation journeys on desktop/mobile
Chromium. The tests use the actual migrated API with the fixture provider. The
README video manifest records executed successful attempts and their source hash.
Implementation acceptance for persisted/live behavior is tracked in the linked issues.
