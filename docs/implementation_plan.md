# Implementation plan and completion gates

The scaffold implements an offline vertical slice. The source brief's overall
portfolio target is 26–36 hours; estimates below are planning bounds, not logged
work. If total effort approaches 40 hours, reduce optional scope first.

| Stage | Original estimate | Already scaffolded | Remaining exit condition |
| --- | --- | --- | --- |
| 1. Skeleton/DB/schemas | 3–4h | FastAPI, Pydantic, SQLAlchemy, migration, Compose | Expand grounded metadata/experience obligation; tested model↔migration compatibility |
| 2. Registry/acquisition/snapshots | 4–6h | JSON/CSV, manual HTML/text, immutable service snapshots | HTTP fake transport + safety/retry/errors, real authorized fetch; two ingestion modes |
| 3. Extraction/normalization | 5–7h | Protocol, replay provider, span guard, aliases | OpenAI schema adapter, failure contracts, versioned prompts, golden semantic regressions |
| 4. Matching/analytics | 4–5h | Four states, two axes, alternatives, core counts/export | Candidate predicate schema, evidence explanations, gaps and clusters |
| 5. Evaluation | 5–7h | 20 authored cases, exact-key scorer, replay comparison | Independent label review, full metrics/provenance and ≥2 measured live configs |
| 6. Tests/CI | 2–3h | Unit/migrated API/PostgreSQL suite, Actions workflow | Add tests as target features land; inspect actual remote CI result |
| 7. README/cleanup | 3–4h | Docs, trace/example, quick starts, synthetic report | Actual LLM results table, error analysis, release/privacy audit |

Implement in this order: V21 (metadata grounding) + experience obligation → V02–V07
(HTTP with transport injection) → V12–V20 (one live provider with mock tests) →
V25–V31 (predicates/gaps) → V33–V38 (real experiment) → release gates. No optional
browser/second provider until the required trace and evaluation work.

Each slice should leave the offline demo usable. Keep a fake transport/provider in
tests; do not substitute fixtures silently for a selected live provider. A working
stub returns a clear unsupported operation, not a success-looking empty result.

Scaffold complete: editable install, Alembic, replay demo, nontrivial tests, API
functional request, PostgreSQL check, authored public dataset and honest docs.
Portfolio complete: every required release gate in `specification.md` §14 plus
measured live results. Frontend, auth, browser, deployment and additional providers
remain optional. The follow-on project in the brief is out of scope.

Current validation: 34 tests passed including PostgreSQL; offline Docker and a
functional API trace passed. [Validation details](validation.md) record limitations.
