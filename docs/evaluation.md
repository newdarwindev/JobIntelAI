# Evaluation protocol

Run `jobintel evaluate` from the checkout root. It reads 20 fixed authored golden
examples and replay responses keyed by clean text SHA-256. It writes ignored
`results/generated/evaluation.json`. `results/fixture_evaluation.json` records a
verified example run; it is not a benchmark of an LLM.

`fixture_raw` preserves replay alias strings. `fixture_normalized` applies the
taxonomy. The comparison demonstrates the normalization/metric pipeline. Gold and
responses come from the same authored examples; matching gold perfectly does not
demonstrate generalization. The provider does not read the gold file at runtime.

The exact-key multiset scorer counts duplicates as extra predictions, keeps ANY/ALL
groups distinct, and includes production/years predicates in the matching key.
Type/evidence accuracy use aligned-pair denominators. Unsupported spans are measured
independently. Undefined metrics are null. Tests deliberately corrupt classification,
evidence and duplication to show that the evaluator can detect failures.

Independent labels, additional metrics and evaluation provenance are specified in
[issue #8](https://github.com/newdarwindev/JobIntelAI/issues/8). Actual authorized live
comparisons and publication requirements are in [issue #9](https://github.com/newdarwindev/JobIntelAI/issues/9).

The [frozen experiment command](experiments.md) checkpoints fake A/B/C runs,
checks budgets and rescores saved predictions without provider calls. Its fake
reports cannot substitute for independently reviewed live measurements.
