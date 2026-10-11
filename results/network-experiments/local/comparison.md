Experiment mode: local-inference; requested model: jobintel-qwen2.5-1.5b-f16.
Created: 2026-10-11T06:06:49.916949+00:00; corpus SHA-256: `dea25cda21d05f80d9e991eddb78f02cd26a76d17bddafb5a1f7a706a8493f7b`.
Configuration SHA-256: `c0f45ecddd97e2f10896552ce4762873f93953c6f21800c9bfa930b5e03e1e02`. [Complete report](report.json); [reproduced scores](scores.json).

| Config | Success / cases | Failures | Precision | Recall | Type | Evidence | Semantic unsupported | Correct unknown | Posting seconds | Tokens in/out | Cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| [B](configuration-B.json) | 2/3 | 1 | 1.0000 | 0.5000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 102.2850 | 1753/478 | unavailable |
| [C](configuration-C.json) | 2/3 | 1 | 1.0000 | 0.5000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 96.0009 | 1753/478 | unavailable |

Metrics cover successful cases; failures and raw outputs remain in the complete report. Matching isolates gold requirements and the sourced candidate. Zero denominators and unmeasured usage/cost/provider-only LLM latency remain unavailable.
Measured pinned local CPU model on the selected reviewed snapshots. B/C use the same source-bound Chat grammar and separate calls; only C normalizes. No hosted benchmark or purchased-cost claim. [Output audit](audit.json).
- B / REV-23: invalid_evidence
- C / REV-23: invalid_evidence
