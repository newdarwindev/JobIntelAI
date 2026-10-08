# Frozen-corpus experiment protocol

`jobintel experiment` runs independently of the database with an explicitly fake
default provider. Requested `openai` execution rejects the request pending the
adapter/evaluator contracts in [#4](https://github.com/newdarwindev/JobIntelAI/issues/4)
and [#8](https://github.com/newdarwindev/JobIntelAI/issues/8), without fixture fallback.
Actual paid runs and reviewer audit belong to [#9](https://github.com/newdarwindev/JobIntelAI/issues/9).

Run from the repository root with the package installed, using new output paths:

```bash
jobintel experiment freeze --output local_data/experiments/corpus.json
jobintel experiment plan --corpus local_data/experiments/corpus.json \
  --output local_data/experiments/plan.json
jobintel experiment run --provider fake --corpus local_data/experiments/corpus.json \
  --output local_data/experiments/fake-run
jobintel experiment rescore --report local_data/experiments/fake-run/report.json \
  --output local_data/experiments/reproduced-scores.json
jobintel experiment publish --report local_data/experiments/fake-run/report.json \
  --output results/experiments/fake
```

Freeze bundles exact Unicode snapshots, SHA-256, labels, taxonomy and review
metadata. It checks the complete authored synthetic content against a source pin;
an environment-selected private root cannot gain public status through filenames.
Bundled labels have no independent review. Loading rechecks hashes/evidence/unique
IDs. Every configuration receives the same snapshots without URL/database reads.

A audits free-form JSON, B rejects invalid evidence, C applies deterministic
normalization to B. The fake provider replays identical raw responses for A/B/C;
it cannot measure prompt/schema effects. Raw predictions remain in reports.
Experimental A predictions never enter production storage.

Use `--config path.json` with at least two distinct configurations:

```json
{
  "configurations": ["B", "C"],
  "model": "fake-fixture",
  "max_calls": 40,
  "max_input_tokens": 32000,
  "max_output_tokens": 4096,
  "budget_usd": 0,
  "pricing": null,
  "authorization_reference": null
}
```

Plans reserve one attempt per case/configuration with no retries. Call limits,
conservative UTF-8 input reservations and worst-case priced reservations are
checked before requests. Optional pricing has `model`, `source`, `date`,
`input_usd_per_million`, `output_usd_per_million`; model must match configuration.
Reservations are bounds, never usage. A future live transport must enforce model
and token limits on requests; over-limit responses are rejected. Simulated test
pricing/usage is never described as purchased service usage.

Live preflight requires independent reviewer/method/revision, a separate paid-call
authorization reference, and dated model-specific pricing. Configuration is not
user authorization. The eventual adapter must use secure runtime credentials;
this command accepts no API-key argument and reads no key. Keep secrets out of
review/configuration fields.

Reports retain successes/failures, predictions, measured local durations, available
usage, corpus/config/prompt/schema/source hashes, commit and dirty status. Errors
use codes without exception bodies. Atomic checkpoints retain interruptions as
incomplete. The command writes diagnostics then exits 1 on case failures; invalid
files/preflight errors exit 2. Existing run directories cannot be overwritten.

Rescore verifies complete aligned corpus/config/prediction hashes without a
provider. The existing multiset scorer reports aggregate/per-case alignment,
type/evidence and invalid spans. Metrics cover successful cases only; failure
counts remain alongside. All-failed metrics are null. Semantic/abstention metrics
stay null pending independent evaluation; alias mismatch is not hallucination.
Missing usage makes complete usage/cost null; `known_cost_usd` reports available
priced usage separately.

Private outputs must stay under ignored `local_data/`. Public fake publication
accepts only pinned authored inputs, default non-secret configuration and verified
fixture predictions. It rebuilds summaries and filters arbitrary fields. Live
publication requires reviewer/privacy audit. Reports contain text/quotes: never
commit private reports or upload them to CI. CI artifacts contain synthetic tests.

The README fake table demonstrates plumbing. Live evidence requires at least two
authorized reports with model/config/date/pricing, measured failures/trade-offs and
reviewer audit. Fake reports and green offline tests do not close V38.
