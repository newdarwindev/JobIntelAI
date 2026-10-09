# Evaluation protocol

`jobintel evaluate` retains the original 20-case fixture regression. Gold and replay
responses share synthetic definitions, so this mode measures pipeline behavior and
leaves semantic/abstention measurements null. Exact one-to-one multiset alignment
penalizes duplicates, preserves ANY/ALL and version/obligation predicates, and
scores classification/evidence separately. Alias alignment is deliberately strict.

## Source-reviewed benchmark

`jobintel evaluate --dataset reviewed` selects the frozen
`data/evaluation/reviewed-v1.json`: 25 MIT-licensed repository-authored cases, source
hashes, full extraction annotations, per-case rationales, a sourced synthetic
candidate, fixed assessment date, and manually assigned four-state matches.
Twenty sources overlap the original regression; five add responsibilities,
ambiguity, negation and version alternatives. It is a small engineering benchmark,
not a representative labor-market sample.

Annotations were written directly from source clauses and reviewed against the
specification, separately from generator labels, replay responses and model
predictions. Metadata records Codex as one automated source reviewer, the method,
and revision. It does not claim a human panel or independent-model review. The
fixture generator cannot rewrite these labels. A source-content pin and taxonomy
hash reject accidental edits; deliberate revisions require a fresh review and pin.
A future external review should retain its identity and method honestly.

The existing bounded fixture provider recognizes 20 of these snapshots. Five cases
have no replay response and remain `provider_unavailable` failures. Do not fill
these failures with gold labels or invent predictions. Tests returning annotations
through fake transports validate scoring/persistence only. Real measured quality
requires the separately authorized comparisons in issue #9.

## Metrics and denominators

Every rate has explicit numerator/denominator fields; zero denominators yield null.
The original exact-key metrics also expose counts, a type confusion matrix and
MUST/PREFERRED accuracy among aligned pairs.

Reviewed semantic unsupported-claim rate covers requirements, job metadata/filters
and responsibilities against exhaustive source annotations for that frozen case.
Taxonomy aliases are canonicalized for semantic review, while distinct products,
operators, types and positive year/production/version/obligation claims remain
separate. Omitted predicates are abstentions, not unsupported positive claims.
Evidence must use the annotated supporting span. A valid but irrelevant quote is
unsupported; an invalid source span is unreviewable and gets a separate rate.
This finite annotated catalog is conservative about alternative supporting spans
and is not an automatic general-purpose entailment judge.

Filter metrics include geography, work mode and typed filters. Responsibility and
filter precision/recall use independent one-to-one multisets. Abstention slots are
geography, work mode, filters, and each reviewed requirement's years, production
predicate, experience obligation and production obligation. Null/UNKNOWN is an
abstention; an omitted requirement abstains on those slots and is also penalized
by requirement recall. Precision measures correct abstentions/all abstentions;
recall and correct-unknown rate measure correct abstentions/expected unknown slots.

Matching agreement compares the deterministic matcher on **gold requirements and
sourced candidate evidence** with reviewed states. It isolates matching from
extraction; it is not end-to-end candidate agreement on generated requirements.
False-COVERED rate is incorrect COVERED decisions/all COVERED decisions. Filters
and geography join requirement matches; assessment time is frozen. The cases cover
strong capability with insufficient production and historical production with weak
current capability.

## Reports, operations and failures

Migrate first. Evaluation appends an `evaluation_runs` record; API and CLI can
reload the exact historical JSON without another provider call:

```bash
jobintel evaluate --output results/generated
jobintel evaluate --dataset reviewed --output results/generated/reviewed
# The reviewed fixture command saves diagnostics and exits 1 for its five failures.
jobintel evaluate --run-id RUN_ID --output results/generated/reloaded
```

`POST /evaluate` accepts `dataset`, distinct `configurations`, and optional pricing.
`GET /evaluation-runs` lists runs; `GET /evaluation-runs/{id}` retrieves one. Browser
UI06 selects either dataset, shows rates/failures and reloads the selected run after
refresh, storing only its ID. JSON and a concise `evaluation.txt` summary are
exported by the CLI. Unknown IDs return 404; all report reads use `no-store`.

Reports freeze dataset/candidate/configuration/model/prompt/schema/taxonomy hashes,
source hashes, code provenance, timestamps, predictions, per-case metrics and error
codes. Provider errors never become successful empty predictions. Live evaluation
stops a configuration after its first failure and marks the remaining cases
`not_attempted`; another explicitly selected configuration has its own diagnostics.
The API returns the provider error status with a saved report ID. CLI exports the
report before exiting 1. Prior reports and production extraction rows remain intact.
Aggregate quality metrics cover successful cases only, with failed/not-attempted
counts beside them; all-failed quality metrics remain null.

Measured posting, provider-adapter and evaluation elapsed times remain distinct
from unavailable provider-only LLM latency. Fixture tokens/cost are null. Actual
supplied usage, including bounded retry attempts, is retained. Optional pricing
requires the selected model, source, date and input/output USD-per-million rates;
missing usage makes complete usage/cost null while known priced usage is reported
separately. Pricing is a supplied dated estimate, not a billing reconciliation.
No paid readiness or evaluation requests run in ordinary CI.

Boundary regressions map to V20/V33-V37 in `tests/unit/test_reviewed_evaluation.py`
and `tests/integration/test_evaluation_reports.py`. They check hand-calculated
counts, aliases, groups, misleading/invalid quotes, duplicates, empty sets,
abstentions, false coverage, missing usage, pricing, frozen inputs and saved
failure reporting on migrated SQLite/PostgreSQL. UI06 and every desktop/mobile
journey must be recorded after relevant edits under AGENTS.md.
