# Acceptance scenarios and traceability

Stable S/V IDs provide regression traceability. Implementation acceptance and
remaining work are maintained in [GitHub issues](implementation_plan.md), rather
than executable/planned status tables. Live model experiments require explicit
paid-call authorization; fast CI uses fake transports/providers.

## Regression references

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
| S34 / fetch stub | Registry has official URL → fetch → explicit 501, no network call | integration/test_api.py |
| S35 / PostgreSQL | Disposable DB → Alembic upgrade + full source/extraction path → tables and API work | integration/test_postgres.py (opt-in locally; required in CI) |
| S36 / health | Database connected but unmigrated → health → 503 | integration/test_boundaries.py |
| S37 / persistence boundary | Replaceable provider returns invalid quote → service extract → no new rows; prior run preserved | integration/test_boundaries.py |

## Implementation acceptance in GitHub issues

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
