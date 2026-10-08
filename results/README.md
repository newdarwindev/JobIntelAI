# Result artifacts

`fixture_evaluation.json` and `example_skill_counts.csv` are generated from the
bundled authored corpus with the documented CLI. They are fixture regressions,
not a live LLM benchmark or job-market sample. Local elapsed time is not LLM latency.

Runtime commands write to ignored `results/generated/`. Do not commit private
corpus exports. The portfolio release still needs actual independently reviewed
A/B/C (at least two configurations) results with provider/prompt/dataset provenance.
