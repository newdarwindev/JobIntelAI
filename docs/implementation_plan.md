# Implementation issue map

GitHub issues are the source of truth for implementation status, remaining work,
acceptance criteria and closure evidence. Keep this file as a navigation map;
do not duplicate issue status or completion claims in source comments or documents.

| Issue | Implementation acceptance | Original scenario IDs |
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

Dependency order: grounded schema (#2) precedes the structured provider (#4) and
candidate predicates (#5). Acquisition (#3) can proceed independently with fake
transports. Profile/match revisions (#5) feed persisted analytics (#6) and exports
(#7). Independent evaluation (#8) and provider provenance (#4) precede authorized
live experiments (#9). Reliability and result publication (#10) support every slice.

Optional browser rendering (V08) and a second provider (V45) remain outside these
required implementation issues. The original brief and scope exclusions are retained
in [the specification](specification.md).

Each implementing PR must satisfy the tests and evidence requirements in its issue.
Keep the offline demo usable, preserve immutable source/run history, and link actual
final-commit CI results. API/provider/browser changes also require the complete
mapped desktop/mobile journeys and successful-attempt recording provenance under
[AGENTS.md](../AGENTS.md). Paid live experiments require separate explicit authorization.
