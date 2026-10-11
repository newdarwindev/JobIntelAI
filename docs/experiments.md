# Frozen-corpus experiment protocol

`jobintel experiment` is a database-independent CLI with an explicitly fake default.
It supports one opt-in OpenAI Responses transport using secure runtime
`OPENAI_API_KEY`, supplied model/pricing configuration and a separate paid-call
authorization reference. Configuration is not user authorization. Never run paid
calls in CI, automatically from the browser, or before explicit operator approval.
[Issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9) defines the actual
live-run/reviewer release gate; offline results cannot close that gate.

## Reproduce a reviewed dry run

Run from the repository root, using new output paths:

```bash
jobintel experiment freeze --dataset reviewed --output local_data/experiments/reviewed.json
jobintel experiment plan --corpus local_data/experiments/reviewed.json \
  --output local_data/experiments/fake-plan.json
jobintel experiment run --provider fake --corpus local_data/experiments/reviewed.json \
  --output local_data/experiments/reviewed-fake
# This exits 1: five inputs have no fixture response in each configuration.
jobintel experiment rescore --report local_data/experiments/reviewed-fake/report.json \
  --output local_data/experiments/reproduced.json
jobintel experiment publish --report local_data/experiments/reviewed-fake/report.json \
  --output results/experiments/reviewed-fake
```

The frozen file embeds all 25 pinned source-reviewed snapshots, labels, rationales,
taxonomy, sourced candidate, assessment date and expected matches. Copies are
cross-validated against reviewed annotations. Public publication compares the entire
corpus to the repository's authored MIT-licensed source pin. A `public` flag or
copied filename cannot authorize private inputs; private outputs stay under ignored
`local_data/`.

The default reviewed fake run reserves 75 attempts (25 cases × A/B/C). Twenty
snapshots have actual fixture responses; five remain `provider_unavailable` failures
in each configuration. Never manufacture predictions from reviewed labels.
Ordinary `freeze` preserves the original 20-case/60-attempt regression. Legacy
format-v1 reports still rescore exactly with their original configuration/metrics.

## Opt-in live configuration

Supply JSON through `--config path.json`:

| Field | Contract |
| --- | --- |
| configurations | At least two distinct choices from A, B, C; all three preferred |
| model | Explicit OpenAI model; fake-fixture is rejected for live execution |
| max_calls | At least cases × configs; no hidden retries |
| max_input_tokens | Conservative UTF-8 reservation for the complete request plus envelope overhead |
| max_output_tokens | Enforced in the actual Responses request |
| budget_usd | Must cover all reserved attempts at supplied pricing |
| pricing | Model, source, valid calendar date, input/output USD-per-million rates |
| authorization_reference | Separate explicit operator approval reference, never a key |

Verify current pricing before proposing a paid run; supplied estimates are not
billing reconciliation. The planner rejects call/input/priced reservations before
constructing a transport or making requests. Usage exceeding token limits stops
later paid attempts. A model alias may return its dated snapshot; different or
missing response models stop execution.

Prepare a concrete plan without credentials or paid requests:

```bash
jobintel experiment plan --provider openai --corpus local_data/experiments/reviewed.json \
  --config local_data/experiments/authorized-config.json \
  --output local_data/experiments/live-plan.json
```

Only after separate authorization, secure credentials, current pricing and permitted
`api.openai.com` network access:

```bash
jobintel experiment run --provider openai --corpus local_data/experiments/reviewed.json \
  --config local_data/experiments/authorized-config.json \
  --output local_data/experiments/authorized-run
```

No API-key argument/config field exists. HTTP uses the supported proxy and verified
TLS, requesting `store: false`, the supplied model and output token limit. There is
no fixture substitution or hidden retry. Repeating a run requires approval covering
its additional spend; an authorization reference alone grants nothing.

## A/B/C and failures

A provides the extraction schema in the prompt without server-side enforcement.
Parseable extraction output is audited even when source quotes are invalid. B uses
strict Responses output and local production grounding checks. C uses B's identical
request, then applies deterministic taxonomy normalization. Each configuration
receives identical frozen source bytes. B/C are separate model calls; response
variation can confound attribution to normalization. No result assumes C wins.

Free-form predictions remain experimental files, never production persistence.
Reports retain parsed raw/scored predictions, bounded raw model text, actual model
and request/response IDs, usage, request/source/prompt/schema/config/corpus/code hashes,
UTC run timestamps and measured posting/provider/end-to-end duration. Provider-only
LLM latency stays null. Invalid output retains available usage and raw text. Error
bodies and credentials never enter reports. Text is capped at 128,000 characters;
invalid schema/truncated Responses output remains a failure.

An atomic incomplete checkpoint names each active case before its request.
Interruptions preserve it. Quota/rate-limit, network/provider, model identity and
usage-limit failures stop later attempts across configurations; remaining slots
are `not_attempted`, with unavailable usage/duration. Case-local schema/evidence/
refusal failures remain diagnostics. No error becomes an empty successful result.
Failures exit 1 after saving; invalid preflight/inputs exit 2. Existing output
directories cannot be overwritten.

## Scores and publication

Format-v2 reports use counted one-to-one alignment, confusion matrices and the
reviewed semantic, abstention, filter/responsibility and gold-requirement matching
protocol in [evaluation.md](evaluation.md). Per-case diagnostics and successful/
failed/not-attempted counts accompany quality rates. All-failed or zero-denominator
quality remains null. Missing usage makes complete tokens/cost unavailable; known
priced usage remains separate. Rescoring uses saved predictions without a provider,
credentials or another paid call.

`comparison.md` includes rates, posting duration, usage, cost and failures.
Automatic fake publication admits only default non-secret settings and reproducible
known fixture responses or known unavailable inputs. Arbitrary predictions/provider
metadata are rejected.

Live publication requires a separate output/privacy/per-case audit tied to the exact
complete report hash:

```bash
jobintel experiment audit --report local_data/experiments/authorized-run/report.json \
  --output local_data/experiments/output-audit.json
```

This creates an **unapproved** draft. Review every raw output, prediction, failure,
metric denominator and source license. Record the actual reviewer (including an
automated reviewer honestly), method, revision and timezone-aware timestamp after
the run. Resolve findings and approve only that reviewed report. Source-label review
is a separate record. Recognizable credentials and non-pinned/private inputs are
rejected; pattern checks cannot replace scrutiny of all content.

```bash
jobintel experiment publish --report local_data/experiments/authorized-run/report.json \
  --audit local_data/experiments/output-audit.json \
  --output results/experiments/authorized-run --readme README.md
```

Publication writes complete report/scores/audit, shared frozen corpus and a linked
machine-readable report per configuration. `--readme` adds/replaces only the marked
live-results section with measured values and relative artifact links, preserving
other content. Stale/unapproved audits and incomplete runs cannot publish. Failures
stay visible. Add observed per-case trade-offs and benchmark limitations to the
review method rather than assuming a normalization winner.

V38 tests use fake Responses transports and authored inputs: full CLI execution,
identical snapshots/config separation, pre-request budget rejection, fatal stops,
raw-output failures, interruption checkpoints, saved rescoring, source pins, audit
freshness and README publication. Simulated transport/model/usage records are test
evidence only; at least two actual authorized live configuration reports and reviewer
audit remain the release gate.

## Local CPU and network contract experiments

Credential-free `local` and `emulator` modes use separately running scoped services;
they never load hosted credentials or substitute fixture output. Freeze a bounded
selection in benchmark order, retaining original source pins, rationales, candidate
and independent review:

```bash
jobintel experiment freeze --dataset reviewed --cases REV-01 REV-23 REV-25 \
  --output local_data/experiments/cpu-corpus.json
```

`--cases` is valid only during reviewed freezing. Generator labels retain
`independent=false` and cannot become local/network reviewed input. Both
configurations receive identical frozen snapshots. Public selections are checked
against the repository source pin before execution or publication.

| Provider | Model/protocol | Configurations | Bounds |
| --- | --- | --- | --- |
| local | pinned `jobintel-qwen2.5-1.5b-f16`, llama.cpp Chat Completions | B source-line grammar; C identical request then taxonomy normalization | 8192 context, output <=2048, input+output reservations <=8192 |
| emulator | `contract-schema-v2`, Responses | B strict schema; C identical request then normalization | output <=8192; only authored source hashes |
| openai | explicitly selected hosted Responses model | A prompt-only schema, B strict schema, C normalized B | separately authorized priced plan |

A is explicitly unsupported in local/emulator modes. Local experiments use
`local-experiment-v1`: the production local policy and example, omitting the
duplicate schema from the prompt because the source-bound schema already constrains
generation. Request/source/prompt/generation-schema hashes identify this protocol.
Grammar constrains spans; semantic entailment remains measured, never repaired.
B/C separate calls can produce different output despite identical requests, so
comparisons cannot isolate normalization causally.

Use a config with B/C, the pinned model, max_calls=6, max_input_tokens=6144,
max_output_tokens=2048, budget_usd=0 and no pricing/hosted authorization. Local
planning reserves UTF-8 message bytes plus 1024 template/envelope tokens; grammar
compilation does not consume prompt context. Responses reserves the full request.
Reservations are conservative bounds, never measured usage. Calls, input/context/
output bounds and mismatched model/cost settings reject before requests. Actual
`max_tokens`/`max_output_tokens` equals the plan, with no hidden retries. Reported
usage beyond bounds stops later calls. Local CPU/power cost stays null because it
is unmeasured; emulator usage and inference time stay null.

Inside the normal local-inference Compose API, on its internal engine network:

```bash
jobintel experiment plan --provider local --corpus local_data/experiments/cpu-corpus.json \
  --config local_data/experiments/cpu-config.json --output local_data/experiments/cpu-plan.json
jobintel experiment run --provider local --corpus local_data/experiments/cpu-corpus.json \
  --config local_data/experiments/cpu-config.json --output local_data/experiments/cpu-run
```

The runtime supplies `JOBINTEL_LOCAL_ENDPOINT`; emulator uses
`JOBINTEL_RESPONSES_ENDPOINT`. `--endpoint` accepts only the corresponding scoped
HTTP service/protocol, never a hosted override. No engine port is published. For
emulator plumbing, freeze REV-01 only and set its model/max_calls=2; unknown authored
hashes fail. `python -m scripts.network_experiments --provider local` measures the
three-case CPU subset; `--provider emulator` measures the one-case contract subset.
Service smoke workflows retain full reports, actual HTTP attempts, matching B/C
request hashes and exact saved rescoring. Model errors remain separate from service
checks, with successful-case metric denominators and failures visible.

Atomic, fsynced checkpoints contain a content hash and name the active case. Resume
only an interrupted zero-cost run using the same corpus/config/code:

```bash
jobintel experiment resume --provider local --corpus local_data/experiments/cpu-corpus.json \
  --config local_data/experiments/cpu-config.json --report local_data/experiments/cpu-run/report.json \
  --output local_data/experiments/cpu-run
```

Saved predictions and failures remain intact. An active request has uncertain
outcome after process loss: its reserved slot becomes `failed/interrupted`, with no
prediction, usage or duration. Resume never repeats that slot; remaining slots stay
within the original call bound. Fatal saved errors keep later slots not attempted.
Unfinished checkpoints cannot rescore or publish. Completed failures exit 1. Resumed
end-to-end timing stays null; last-session timing is measured. Hosted resume is
unsupported because uncertain paid attempts require a separate authorization decision.
Local/emulator publication requires the same exact-report, privacy and per-case
reviewer audit as hosted output. These reports cannot replace the hosted README
section or close issue #9.
