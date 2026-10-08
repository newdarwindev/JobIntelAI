# JobIntel AI — full v1 specification

Source: [original brief](source_brief.txt), “GitHub Portfolio Project 02 — JobIntel
AI — Evidence-Grounded Job Requirements & Skill Gap Analysis”, Stefan Novak.
This document translates that brief into implementable contracts. The repository
name remains `JobIntelAI`; package/CLI names are `jobintel-ai` / `jobintel`.

**2026-10-08 scope extension:** the user subsequently requested spec-driven mock web
UIs, complete Actions browser workflows, successful videos in README, and mandatory
agent recording updates. [Web UI specification](web_ui_spec.md) defines this
authorized extension and its executable acceptance map. Original backend-only
exclusions below describe the initial v1 brief, not a prohibition on this requested
mock UI. Implementation acceptance and dependencies are tracked in
[GitHub issues](implementation_plan.md).

## 1. Purpose and audience

Build a reproducible Python backend that converts heterogeneous job postings into
requirements backed by source evidence, then measures extraction quality and
candidate gaps. A hiring manager should understand the evidence trace, architecture
and measured trade-offs in 5–10 minutes. The engineering evidence is Python/backend,
structured AI, evaluation, data modeling, APIs, testing and debugging, rather than
scraping volume. Personal job search is a second, private use case.

Invariant: **No evidence — no claim.** Evidence is necessary for requirements,
filters, classifications and candidate coverage. Evidence existence alone is not
sufficient: annotations/evaluation must also check whether a quote supports the
claim. Employer reputation is never candidate or job evidence.

## 2. Scope and implementation defaults

| Component | v1 contract |
| --- | --- |
| API / CLI | FastAPI sync endpoints; argparse CLI; no frontend |
| Schemas | Pydantic v2, reject extra fields |
| Storage | SQLAlchemy, Alembic, PostgreSQL 16 |
| Import | JSON or pasted CSV export; no Google OAuth integration |
| Manual acquisition | Text/HTML payload, local authored fixtures |
| URL acquisition | Bounded HTTP GET through httpx |
| Browser | Optional fallback only after HTTP/manual modes |
| Snapshots | Append-only raw/clean text, SHA-256, UTC timestamp |
| Extraction | Strict provider interface; fixture replay by hash |
| OpenAI | One adapter with schema-constrained output |
| Anthropic | Optional comparison adapter |
| Skills | Exact case-insensitive alias map in versioned JSON |
| Candidate | Explicit capability + production axes, no embeddings |
| Analytics | Distinct-job SQL/service aggregation, JSON/CSV |
| Evaluation | Fixed labels, exact multiset alignment |
| CI | pytest + PostgreSQL service; zero external AI calls |

No LangChain/LangGraph, multi-agent architecture, vector database, embeddings or
rapidfuzz until measured errors justify them. Use synchronous SQLAlchemy and a
simple request pipeline first; an async httpx adapter can be added without replacing
the domain services. No queues or distributed workers in v1.

These contracts define the requested portfolio product. Issue acceptance and test
evidence determine completion; this specification does not maintain feature status.

## 3. End-to-end use cases

Public demonstration: migrate → import synthetic registry → create local snapshots
→ replay structured responses → validate → normalize → match synthetic profile →
export n/N counts → compare fixture configurations. Everything works without keys.

Private workflow contract: import CSV → fetch official URLs → clean and
snapshot → extract with OpenAI → validate and persist → normalize → candidate
matching → filtered corpus analytics → JSON/CSV export → golden evaluation.

When HTTP fails (timeout, denied, unsupported JS), preserve an acquisition outcome
and offer manual text entry. Browser fallback must be explicit, optional and never
an anti-bot bypass. One job may have many source snapshots and extraction runs.

## 4. Data ownership and privacy

Public mode: 20 authored synthetic postings are included; v1 accepts 20–30 labelled
examples (satisfies the brief's 15–30 public samples and 20–30 golden samples).
Examples cover alternatives, conjunctions, preference, years, production, aliases,
geography, travel, negation, Unicode and technology mentions that are not demands.
Golden labels and provider responses are distinct runtime inputs, but are authored
from the same synthetic definitions. Their agreement measures pipeline plumbing.

Private mode: real Job Search Log, status/applied history, original descriptions,
candidate evidence and notes remain under ignored `local_data/` or outside Git.
Do not copy full third-party postings into public fixtures without permission.
Private notes/recruiter details are not part of public API examples. No secrets in
logs or results. The API is local single-user tooling, unauthenticated; bind to
loopback and do not expose publicly.

Analytics claims apply only to the loaded, self-selected corpus. Public URL access
does not imply redistribution rights. See [privacy](privacy_and_copyright.md).

## 5. Registry contract

Required: `job_id` (1–64 ASCII letters/digits/underscore/hyphen, starts alphanumeric),
`company`, `role`. Optional: `official_url`, `status`, `applied` (bool or unknown).
CSV headers use these exact snake_case names; Sheets exports require header mapping
outside v1. `applied` accepts `true`, `false`, empty; no inferred application state.
CSV may omit optional columns. JSON/CSV batches are atomic.

Canonical URL: HTTP(S), no credentials, host/scheme lowercase, default port removed,
fragment removed, meaningful path case/trailing slash/query retained. This is an
identity function, not permission to fetch. Acquisition adds network safety checks.

Same ID + identical metadata is idempotent. Same ID + changed metadata is 409.
Different ID + same canonical URL or casefolded company+role is 409, requiring
explicit resolution; do not silently drop distinct postings. Null URLs may repeat.
The conservative company+role rule may flag separate openings; explicit duplicate
resolution/update workflows require a separate scope decision. Reject malformed rows with 422.

## 6. Acquisition and snapshot contract

Manual endpoint accepts `text`, optional `source_url`, `format=text|html`, at most
200,000 characters. HTML stripping removes scripts/styles/nav/header/footer/forms
and explicit cookie banners, prefers main/article, and normalizes line breaks.
Retain raw HTML/text and clean text; simple cleaning can still lose information on
unusual sites. Fixture tests precede expanding selectors.

Snapshots include ID, job FK, URL, UTC `fetched_at`, raw content, clean content,
SHA-256 of UTF-8 clean text, acquisition status and outcome metadata.
Offsets refer to clean Unicode text. Exact latest raw+clean+URL resubmission reuses
the existing snapshot. Changed raw text with identical clean content can create a
new provenance snapshot with the same hash. The service never edits a snapshot;
the service contract does not protect against direct database mutation.

HTTP adapter acceptance requirements: configurable connect/read timeouts; bounded
retry on transient errors/429 with capped Retry-After; at most three redirects;
HTTP(S) only; no credentials; validate every redirect and resolved IP, reject
loopback/private/link-local/metadata/multicast/reserved addresses including IPv6;
protect against DNS rebinding via a transport with verified destination selection;
allow HTML/plain text only; bounded decompressed body; retain final URL and fetch
status; no unlimited redirects, credential forwarding or HTML execution. Access
denial and CAPTCHA prompt manual entry, never bypass. Inject a fake transport for
tests. Respect the environment's supported egress proxy rather than bypassing it.

## 7. Structured extraction contract

The executable field and compatibility contract is [extraction schema v2](extraction_schema.md).

Provider input is the exact immutable clean snapshot + versioned configuration.
It returns `Extraction`: requirements, responsibilities with evidence, geography
and work_mode (unknown if absent). A requirement contains:

| Field | Meaning |
| --- | --- |
| raw_text | Exact original quoted wording; never a rewritten summary |
| normalized_skill_or_requirement | Canonical readable requirement/group |
| skills | One or more canonical terms after normalization |
| operator | SINGLE / ANY / ALL; alternatives remain one requirement |
| requirement_type | MUST / PREFERRED / EXPERIENCE / OTHER |
| category | AI/LLM, backend, cloud, infrastructure, data, domain, geography, etc. |
| evidence | quote, start >= 0, end > start; end exclusive |
| explicit_production_required | true / false / null (unknown); absence is null |
| years_required | minimum, optional maximum, or null; never guessed |
| confidence | [0,1], informational; never overrides missing evidence |
| notes | Optional ambiguity explanation only |

EXPERIENCE marks tenure/experience predicates and is reported separately from MUST.
Experience uses a separate obligation field (MUST/PREFERRED/UNKNOWN), rather than
being counted automatically as mandatory. Production preference is not a
mandatory production filter. Responsibilities are not requirements. Top-level
geography/work-mode metadata requires explicit source evidence. Validate populated
metadata as well as requirements/responsibilities before persistence.

Validate schema and every evidence slice before persistence. Fail the entire run
on missing/invalid evidence with 422; retain the prior run. Exact source text can
still be misleading evidence: semantic hallucination is assessed against labels,
not just substrings. A quote saying “nice to have” cannot substantiate MUST. Company
location cannot imply geography. “AWS or Azure” cannot become AWS AND Azure.
Production/years/filter predicate entailment requires review/regression cases.

Live provider must treat document instructions as untrusted data. Version prompts,
schema, model, provider and normalization config; capture timing and usage metadata.
One bounded schema retry is acceptable, never an endless repair loop. Timeouts,
malformed JSON, refusals, quota failures and invalid grounding are distinguishable
outcomes, never empty successful extraction. No paid calls in CI. API keys come
from secure runtime configuration, never test data.

## 8. Skill normalization

Versioned `data/taxonomy.json`: canonical name, aliases, category. Exact whitespace
trim + casefold first. Examples: Postgres→PostgreSQL, K8s→Kubernetes,
GenAI→Generative AI. AWS remains distinct from AWS Bedrock. Preserve raw evidence.
Unknown terms remain literal; no automatic semantic merging. Version requirements
retain their explicit predicates and raw wording. Reject ambiguous
aliases. Normalization may deduplicate alias equivalents but must preserve ANY/ALL
semantics. Embeddings/fuzzy matching are optional experiments, not v1 prerequisites.

## 9. Candidate matching

Profile has ID, completeness flag (default false) and explicit records: skill,
current_capability (`strong|basic|none|unknown`), production_evidence
(`confirmed|limited|none|unknown`), source reference and quote. A source reference
is supplied evidence, not proof that a third-party credential has been verified.
No employer-name inference. Candidate import and revision selection use explicit sourced profile payloads.
`POST /candidates/import` appends an immutable revision, reusing an identical validated
payload for the same profile ID. Reads list revisions or retrieve one exact revision;
there is no update/delete endpoint. Legacy snapshot IDs remain valid revisions.
Completeness is a user assertion about supplied records, not independent verification.

`tenure` records carry skill, kind (`experience|production`), status
(`confirmed|none|unknown`), start/end dates, source and quote. End is exclusive;
missing dates and periods beyond the match assessment date abstain. Overlapping
and adjacent intervals are merged per canonical skill/kind before computing calendar
anniversary years plus a fractional remainder. Requirements use inclusive minimum
and maximum bounds. A known lower bound can satisfy a minimum; a maximum requires
`tenure_complete=true`. Short positive complete tenure is PARTIAL; zero/absent complete
tenure or exceeding a maximum is MISSING. Incomplete deficits stay UNKNOWN.
Generic capability and employer names never supply tenure. Production years use
production periods and still require the separate current capability/production axes.

`eligibility` records carry kind (`location|work_authorization|travel|residency|attendance`),
exact scoped value, status (`confirmed|denied|unknown`), observation date, optional
inclusive expiry, source and quote. Only whitespace/case normalization is applied;
no country hierarchy, citizenship, authorization, or travel inference is performed.
Records outside their validity period or contradictory records abstain. Each kind's
absence remains UNKNOWN unless declared in `eligibility_complete`. Explicit denial
is MISSING. Sourced job geography and filter metadata are evaluated directly. An OTHER
requirement using the same grounded evidence span shares those predicate results;
OTHER claims without such a supported fact and version requirements abstain.

Matching a saved revision sends `profile_id`, `profile_revision_id`, `expected_run_id`
and optional `as_of` (default local assessment date). A wrong profile/revision pair
returns 404; a stale extraction returns 409. Older candidate revisions remain valid
when explicitly selected. A coherent persisted match run identifies source snapshot,
source hash, extraction, candidate revision/hash and assessment date, with per-predicate
job evidence and candidate sources. `GET /match-runs/{id}` preserves historical reads.
The original full-profile match body remains compatible and imports/reuses its revision.
Private payloads stay in the user's local database; only synthetic records enter tests.
The browser retains revision IDs, not profile bodies, in local storage.

| Condition | State |
| --- | --- |
| Strong capability, production not required | COVERED |
| Strong capability, confirmed production when required | COVERED |
| Basic capability, or strong capability but limited/no required production | PARTIAL |
| Explicit no capability, or absent record in explicitly complete profile | MISSING |
| Missing incomplete record, conflicting evidence, unknown required axis | UNKNOWN |

ANY chooses a sufficient branch; ALL requires every branch. Every match references
the extraction requirement and stored profile snapshot, with explicit sources and
explanation. Tenure/geography/authorization/travel predicates require sourced candidate records
and predicate-specific matching. Unsupported or absent predicates return UNKNOWN;
generic skill capability cannot establish eligibility or years of experience.

## 10. Analytics and exports

Default N = distinct jobs with a successful extraction on their latest snapshot,
not total registry rows or number of requirements. Successfully extracted empty
postings count in N. Report total registered, failed, pending and excluded counts. Each skill counts once per job and once per job/type. Must/Preferred
may overlap in one posting; their sum need not equal overall mentions.

ANY groups are reported separately; no branch is counted as an independent MUST.
ALL branches count as individual required mentions. EXPERIENCE and OTHER have
separate breakdowns. Results are n/N integers, not unsupported market estimates.

Analytics includes taxonomy cluster coverage, requirement-group gaps from the latest matching
run for a selected profile, unknown counts separate from missing, and slices by
applied state, remote and explicitly imported positive-response status. Do not
infer “positive response” from generic notes. Recompute N after each slice. Counts
are frequencies, not job suitability scores; no ranking without an explicit model.

JSON export preserves provenance/alternatives. CSV includes core counts and flattened requirement/match rows with run and snapshot identifiers.
For spreadsheet-facing exports neutralize formula prefixes in user-controlled
strings; test both authored terms and private user-controlled values.

## 11. Evaluation contract

Fixed authored golden records include requirement types, canonical skills, spans,
years, production and OTHER filters. Live experiment labels must be reviewed
independently from model output, not auto-generated from predictions. Record dataset
hash, revision, prompt/schema/taxonomy versions, provider/model/config and run time.

The exact-key scorer uses an exact multiset key: operator, sorted skill group,
production predicate, years range. It consumes each gold item at most once. Type
and span are scored separately after alignment. This makes errors visible but is
strict about aliases and groups; no fuzzy metric claims. Filters and responsibilities use their own metrics.

- Precision = aligned predictions / all predicted requirements.
- Recall = aligned predictions / all gold requirements.
- F1 = harmonic mean when both denominators are defined, else null.
- Type accuracy = correct types / aligned pairs; include a MUST/PREFERRED-only
  denominator and confusion matrix.
- Evidence accuracy = exact gold evidence matches / aligned pairs.
- Unsupported-span rate = invalid source slices / predicted items. This is **not**
  semantic hallucination rate; a valid irrelevant quote may still hallucinate.
- Semantic hallucination rate = unsupported claims after annotated entailment
  review / all predictions; never rename unmatched aliases as hallucinations.
- Abstention quality: precision/recall of abstentions on annotated ambiguous
  predicates; correct-unknown rates for missing geography/production.
- Matching: agreement across four states and false COVERED rate, including
  historical evidence with weak current capability and the reverse.
- Operations: posting and provider latency, token usage, estimated cost with
  explicit price/model/date, fetch success/failure and manual fallback share.

Zero-denominator metrics are null, not 100%; runner errors fail the run and are
reported separately. Fixture elapsed time is local replay time; tokens/cost/LLM
latency are null. Unmeasured semantic hallucination and abstention metrics are null.

Controlled experiments on identical frozen inputs:
A = free-form prompt (parse output and audit ungrounded claims in evaluator);
B = structured Pydantic/schema output + mandatory evidence;
C = B + deterministic normalization. A output never enters production persistence
without grounding. Compare at least two live configurations; all three preferred.
Publish actual measured table (precision, recall, type/evidence accuracy,
hallucination, latency, cost), failures and trade-offs without assuming C wins.
`fixture_raw` vs `fixture_normalized` is a plumbing demonstration, not A/B/C evidence.

## 12. API contracts

All endpoints use JSON except embedded CSV text in import. No frontend or auth.
422 = invalid input/schema/evidence; 404 = unknown job; 409 = conflict/prerequisite;
501 = explicit unimplemented integration; 503 = DB not ready. Live adapters use 502 for provider failure, 504 for timeout, structured retryable error codes.

| Endpoint | Contract |
| --- | --- |
| GET /health | Check DB connection and migrated jobs table; report fixture/live status |
| POST /jobs/import | Exactly one of `{jobs:[...]}` / `{csv_text:"..."}`; counts, atomic |
| GET /jobs | Ordered registry with latest-source snapshots/extractions for the UI |
| GET /jobs/{id}/history | Append-only snapshot and extraction-run history |
| POST /candidate/validate | Strict profile validation without persistence |
| POST /candidates/import | Explicit local candidate import; immutable/reused revision |
| GET /candidates/{profile_id}/revisions | List saved revisions |
| GET /candidates/{profile_id}/revisions/{revision_id} | Read/select an exact saved revision |
| GET /match-runs/{match_run_id} | Read a historical match run and its provenance |
| POST /jobs/{id}/snapshots | Manual text/HTML, source URL; return snapshot ID/hash |
| POST /jobs/{id}/fetch | Bounded HTTP fetch with auditable outcomes; unsupported integration returns 501 |
| POST /jobs/{id}/extract | Configuration, latest snapshot; return run, requirements, evidence |
| GET /jobs/{id} | Metadata, latest snapshot and its latest extraction; no stale results |
| POST /jobs/{id}/match | Candidate profile payload; requirement-linked states/sources |
| GET /analytics/skills | n/N, type counts, alternatives, selected-profile gaps and explicit slices |
| POST /evaluate | Explicit config list and persisted evaluation provenance; fixture and authorized live runs |

CLI: `jobintel demo` imports/processes authored examples; `jobintel evaluate`
compares fixture configurations; `jobintel export` writes current counts as JSON/CSV.
Run from checkout root, migrate first. Repeated demo doesn't duplicate jobs or the
latest identical snapshot; it deliberately appends extraction/match history.

## 13. Persistence and operations

Logical entities: jobs, posting_snapshots, extraction_runs, requirements, skills,
candidate_evidence (immutable profile revisions), match_runs, matches, evaluation_runs.
FKs establish source/run/candidate trace. SQLAlchemy JSON holds validated payloads
to keep initial migrations small; promote frequently queried fields to columns
when gap/slice queries justify it. PostgreSQL is authoritative; SQLite is not
a substitute for PostgreSQL migration checks. See [data model](data_model.md).

No automatic DDL on API startup. Apply Alembic before readiness. Service transactions
keep imports/extractions atomic. Raw/clean source text and profile evidence are
private data in private mode. Structured logs contain IDs, hashes, outcomes
and timings, no full bodies/secrets. Limits/backoff precede public URL operations.

## 14. Required checks and portfolio completion

Fast CI: unit/schema/grounding/normalization/count/matching tests, fake-provider
tests, HTML fixtures, migrated API integration and PostgreSQL migrations. No keys.
Live golden experiments are separate explicit manual runs; browser/Anthropic are
optional. Do not hide missing target features as skipped green tests.

Portfolio release gate (all required): reproducible README; registry import; both
HTTP and manual ingestion; immutable metadata/hash snapshots; valid live structured
extraction; source evidence on every requirement; canonical aliases/raw wording;
four evidence-based match states; n/N corpus analytics and gaps; frozen reviewed
golden set; at least two live config experiments; measured results committed; README
quality table; unit/integration tests and passing CI; no private/secrets/unauthorized
content; author can explain architecture and limitations. Test references and issue traceability are in [testing scenarios](testing_scenarios.md).

## 15. Trade-offs and explicit exclusions

Snapshots separate from runs because URLs change/disappear and models evolve.
HTTP first because browser dependencies are costly and manual entry is predictable.
Counts expose denominator selection; MUST/PREFERRED must remain distinct. Exact
aliases are auditable, unlike an unmeasured semantic merger. Candidate axes avoid
equating a lab skill with historical production evidence. Confidence helps triage
but cannot invent a source. Golden regressions detect prompt/provider drift.

No React/dashboard, authentication, SaaS, broad crawling, protected-site bypass,
automatic applications, resume generation, general browser framework, Kubernetes,
Terraform, cloud deployment, LangGraph/MCP/multi-agent runtime, unnecessary vector
database, many providers or heavyweight observability. Do not start the brief's
next Agentic Repository Task Runner project as part of this task.

## 16. Delivery and positioning

Follow the original 26–36 hour staged budget; cut optional features if approaching
40 hours. See [the issue map](implementation_plan.md) for dependencies and acceptance evidence. Evidence-grounded API/evaluation is the priority, not feature volume.

Only after actual completion/publication describe the project in a résumé as a
Python/FastAPI/PostgreSQL system with structured LLM extraction and measured
evaluation. It is a portfolio demonstration, not proof of production SaaS scale or
a substitute for professional experience. Interviews should show evidence traces,
metrics, candidate axis rules, actual error cases and cost/latency trade-offs.
