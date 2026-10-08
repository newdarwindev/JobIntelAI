# Architecture

```mermaid
flowchart LR
    Registry[CSV / JSON registry] --> Jobs[(Jobs)]
    Manual[Manual text / authored HTML] --> Clean[Deterministic cleaning]
    HTTP[HTTP adapter] --> Clean
    Clean --> Snapshots[(Immutable source snapshots)]
    Snapshots --> Provider[Extraction provider]
    Provider --> Guard[Pydantic + exact evidence guard]
    Guard --> Aliases[Deterministic taxonomy]
    Aliases --> Runs[(Extraction runs + requirements)]
    Candidate[Candidate profile + sources] --> Match[Capability / production rules]
    Runs --> Match
    Match --> Matches[(Auditable matches)]
    Runs --> Counts[Distinct-job n/N counts]
    Runs --> Eval[Golden evaluator]
    Counts --> API[API / CLI / JSON / CSV]
    Eval --> API
```

Files live under one `src/jobintel` package. Single-purpose modules provide registry,
acquisition, snapshots, providers, normalization, matching, analytics and evaluation.
`Service` coordinates transactions; API/CLI call the same services. Tests inject
provider data and disposable databases. No framework orchestration is needed.

Source snapshots are separated from extraction runs so a changed prompt or provider
does not overwrite the source. Matching references a concrete requirement row and
profile snapshot. The current job view only exposes results for its latest source.
Historical runs remain in the database but are not aggregated twice.

SQLite is a low-friction offline development mode. PostgreSQL and Alembic are the
target persistence path; PostgreSQL integration is required in CI. JSON payloads
keep the initial schema compact while foreign keys preserve provenance.

Quote integrity and semantic entailment are separate boundaries. See specification
sections 6–11 for their contracts and [the issue map](implementation_plan.md) for
implementation acceptance and dependencies.
