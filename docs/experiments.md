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
