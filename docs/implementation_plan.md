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

The approved runtime extension has its own dependency map:

| Issue | Runtime acceptance |
| --- | --- |
| [#22](https://github.com/newdarwindev/JobIntelAI/issues/22) | Persistent dev/demo/provider profiles, mounted secrets, readiness and verified trust |
| [#23](https://github.com/newdarwindev/JobIntelAI/issues/23) | Responses contract emulator over real HTTP |
| [#24](https://github.com/newdarwindev/JobIntelAI/issues/24) | Actual local inference for unseen postings |
| [#25](https://github.com/newdarwindev/JobIntelAI/issues/25) | Acquisition origins, TLS and controlled proxy fixtures |
| [#26](https://github.com/newdarwindev/JobIntelAI/issues/26) | Verified acquisition in proxy-only environments |
| [#27](https://github.com/newdarwindev/JobIntelAI/issues/27) | Provider-aware UI and persistent real-service browser journeys |
| [#28](https://github.com/newdarwindev/JobIntelAI/issues/28) | Connect implemented experiment runners to local/network environments |
| [#29](https://github.com/newdarwindev/JobIntelAI/issues/29) | Complete disposable environment lifecycle and CI integration |

#22 provides the runtime foundation; #23/#24/#25 materialize its external services.
#25 precedes proxy validation (#26). Provider-aware journeys (#27) use #23/#24/#25;
experiment integration (#28) extends #9. #29 composes those environments on demand.
Optional browser rendering (V08) remains separate from HTTP origin fixtures. The
original brief and scope decisions are retained in [the specification](specification.md).

Each implementing PR must satisfy the tests and evidence requirements in its issue.
Keep the offline demo usable, preserve immutable source/run history, and link actual
final-commit CI results. API/provider/browser changes also require the complete
mapped desktop/mobile journeys and successful-attempt recording provenance under
[AGENTS.md](../AGENTS.md). Paid live experiments require separate explicit authorization.
