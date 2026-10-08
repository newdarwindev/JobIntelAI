# Acceptance scenarios and traceability

`Executable` means an existing test demonstrates the stated behavior. `Planned`
means an acceptance contract for future implementation, not a skipped/passing test.
Use these IDs in issues and new test docstrings. Live model tests are manual and
require explicit paid-call authorization; fast CI must remain offline.

## Scaffold scenarios

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

## Target v1 scenarios (planned)

| ID / brief area | Given → when → expected | Boundary / priority |
| --- | --- | --- |
| V01 / import | Canonical URL duplicate under different ID → batch → 409 and no partial inserts | registry / required |
| V02 / acquisition | HTTP HTML 200 via fake transport → fetch → immutable snapshot, final URL/time/hash | acquisition + API / required |
| V03 / acquisition | Connect/read timeout or bounded 429/5xx → fetch → capped retries, retryable error, manual fallback | fake transport / required |
| V04 / acquisition | Redirects across public hosts → fetch → validate each target, max three hops | fake transport / required |
| V05 / SSRF | localhost/IPv6 loopback/private/DNS rebound/metadata URL or redirect → fetch → no internal request | acquisition / required before enabling HTTP |
| V06 / acquisition | Large compressed body or PDF/binary content → fetch → size/type error, no extraction | acquisition / required |
| V07 / access | CAPTCHA/403/JS-only page → fetch → documented manual fallback, no bypass | acquisition / required |
| V08 / browser | Opted-in JS fallback with rendered fixture → snapshot → same evidence contract | optional Playwright |
| V09 / HTML | Table/list/ATS career HTML with no main or malformed markup → clean → preserve required clauses | HTML fixtures / required |
| V10 / raw provenance | Different raw HTML, identical clean text → snapshot → distinct raw provenance allowed, same clean hash | persistence / required |
| V11 / integrity | Attempt snapshot mutation through supported API/service → persist → rejected; prior evidence stable | snapshots / required |
| V12 / live provider | Mock OpenAI schema response → extract → strict Pydantic result and prompt/schema/model IDs | provider / required |
| V13 / live failures | Refusal, invalid JSON or quote, timeout, quota error → extract → explicit failure, prior run intact | provider + transaction / required |
| V14 / prompt injection | Posting instructs model to fabricate skills/reveal secrets → extract → treats instruction as document data | provider regression / required |
| V15 / classification | Technology only in responsibilities or product description → extract → no candidate MUST claim | golden regression / required |
| V16 / classification | Nice-to-have section with Python → extract → PREFERRED, not MUST | golden regression / required |
| V17 / alternatives | AWS or Azure / Python and SQL → extract → ANY / ALL groups preserved | golden regression / required |
| V18 / unknown filters | No geography/work mode/years/production clause → extract → unknown predicates, no company inference | golden regression / required |
| V19 / production | Production requirement vs hobby familiarity vs production preference → extract → distinguish production and obligation | golden regression / required |
| V20 / entailment | Valid but irrelevant quote supports invented skill/years → audit → semantic hallucination reported | evaluation / required |
| V21 / metadata grounding | Explicit remote/geography claim → schema → metadata evidence matches snapshot | schema + golden / required |
| V22 / normalization | Taxonomy contains ambiguous alias → load → reject, do not arbitrarily choose | taxonomy / required |
| V23 / versions | Python 3.11+ vs Python skill → normalize → retain version predicate and raw wording | taxonomy / required |
| V24 / candidate ingestion | Private candidate JSON → validate/store → source-linked profile revision, no public copies | matching / required |
| V25 / candidate predicates | Verified candidate tenure/location/authorization → match years/OTHER → correct sourced state | matching / required for complete v1 |
| V26 / missing proof | Employer name or unsourced candidate claim → match → cannot claim COVERED | matching / required |
| V27 / gaps | Selected profile across corpus → summarize → MISSING/PARTIAL/UNKNOWN distinct, per-job/group gap frequencies | analytics / required |
| V28 / coverage | Registered failed/pending/empty extracted postings → summary → explicit excluded/registered counts, correct N | analytics / required |
| V29 / slices | Applied/remote/positive-response slice → summary → filter by explicit metadata, recompute denominator | analytics / optional |
| V30 / clusters | Taxonomy cloud/backend group → summary → per-job cluster coverage, no sum of mentions | analytics / required |
| V31 / export | Requirement/match export → JSON/CSV → snapshot/run/profile references and raw wording retained | exports / required |
| V32 / spreadsheet safety | Private user-controlled string starts =,+,-,@ → CSV → prevent spreadsheet formula execution | exports / required before private spreadsheet use |
| V33 / eval provenance | Fixed gold + config/prompt/schema/taxonomy/model → run → hashes/revisions and timestamp recorded | evaluation / required |
| V34 / metric boundaries | Empty gold/predictions, duplicate skills, unmatched type, misgrouped ANY/ALL → score → explicit denominators/nulls | evaluation / required |
| V35 / abstention | Annotated ambiguous/missing predicates → compare → abstention precision/recall + error cases | evaluation / required |
| V36 / matching eval | Labels for four match states + axis conflicts → compare → agreement and false COVERED rate | evaluation / required |
| V37 / operations | Mock usage/timing/provider error → report → tokens/cost/latency with pricing source, failures not zeros | evaluation / required |
| V38 / actual experiments | Identical frozen corpus, authorized live A/B/C (at least two) → compare → actual metrics/table/errors; no assumed winner | manual paid experiment / required portfolio gate |
| V39 / migrations | PostgreSQL fresh upgrade, downgrade in disposable DB, re-upgrade → validate → schema matches model | db integration / required |
| V40 / transactions | Provider/DB failure midway → commit → zero partial new requirements/matches | persistence / required |
| V41 / health | Database unreachable → health → 503, no falsely healthy state (unmigrated case covered by S36) | API / required |
| V42 / logging | Private source/key input → errors/logs → only IDs/status/hash, no bodies or credentials | observability / required |
| V43 / privacy | Public tree/result artifacts → audit → only licensed/authored fixtures, no personal history or secrets | release review / required |
| V44 / reproduction | Fresh clone per README + sample data → run → API/demo/exports usable without private material | release smoke / required |
| V45 / optional provider | Anthropic fake transport returns same schema → compare → provider adapter interchangeable | optional |

## Manual release review

Verify README architecture, example trace, data model, schema, real experiment table,
counts with n/N, trade-offs, privacy and next steps. Do not add the suggested résumé
claim until this behavior exists and the repository is published. An uploaded brief
or planned scenario is not evidence of implementation.

Promotion rule: add a meaningful executable test, verify it against a failing case,
move the scenario to the executable table, and update the implementation plan. Do
not create empty or permanently skipped test functions for the planned table.
