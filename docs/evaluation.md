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

Live release experiments need independently reviewed labels, dataset hashes, prompt
and schema versions, provider/model, taxonomy revision, run timestamps and failures.
Use the same frozen 20–30 cases for A free-form, B evidence-structured and C normalized
structured configurations; compare at least two. Experimental unsupported A claims
remain in evaluation outputs and must not enter production requirement storage.

Score semantic hallucination via reviewed entailment; quote integrity is only one
signal. Add type confusion matrix, unknown/abstention metrics, explicit OTHER filters,
matching agreement and false COVERED rate. Record actual provider usage and pricing
source/date for cost, not guessed zeros. Keep local replay time separate from LLM
and end-to-end latency. Explain errors and cost/quality trade-offs without a preferred
winner. A live run requires explicit paid-call authorization and secure configuration.
