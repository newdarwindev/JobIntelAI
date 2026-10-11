# Reviewed network experiments

These are actual local development measurements on authored MIT-licensed frozen
sources, with automated Codex output/privacy audits separate from source-label
review. No hosted paid call occurred. [Protocol and reproduction](../../docs/experiments.md).

| Execution | Frozen selection | Actual HTTP attempts | Valid / attempted, B and C | Evidence |
| --- | --- | ---: | --- | --- |
| pinned Qwen2.5-1.5B F16 / llama.cpp CPU | REV-01, REV-23, REV-25 | 6 | each 2/3; REV-23 invalid evidence | [comparison](local/comparison.md), [report](local/report.json), [scores](local/scores.json), [audit](local/audit.json), [service evidence](local/service-evidence.json) |
| separate Responses emulator | REV-01 | 2 | each 1/1 authored response | [comparison](emulator/comparison.md), [report](emulator/report.json), [scores](emulator/scores.json), [audit](emulator/audit.json) |

Local B/C use identical source-bound requests and produced identical raw outputs.
REV-01 correctly marks Python MUST but misses preferred PostgreSQL: successful-case
recall is 1/2, precision/type/evidence each 1/1. REV-25 correctly abstains. REV-23's
invalid exact evidence remains a failure with available output and usage, excluded
from successful-case quality metrics. No observed normalization benefit or causal
prompt improvement is established by three cases. Each configuration reports actual
1753 input / 478 output tokens, including the failed request. CPU/power cost is
unmeasured and stays null. The separate normal-API reviewed evaluation is also retained
in service evidence; it uses the production prompt, not the shorter experiment prompt.

Emulator B's raw Postgres alias gives alignment precision/recall 1/2; C's deterministic
normalization gives 2/2. This demonstrates plumbing, never model quality. Usage, cost
and LLM time remain unavailable. Both modes reproduce saved scores with no requests.

Development provenance is retained exactly: the local image source hash is
`1a3224e15a028e18f56d32dad6407826e3e1d296bc749ee2066cfebc3f7e894d` and
contains no Git metadata. Host source hash is
`66a08807c36e149d6f932464061430ca006f89a9cb45dc39af7ba3080415bde2`, captured
at `335c5b9` with dirty=true while adding these artifacts. The emulator measured that
host source hash at the earlier development commit with dirty=true. These are
honest development runs; final-commit Actions evidence is linked in issue #28.
Hosted experiment authorization and publication requirements remain in issue #9.
