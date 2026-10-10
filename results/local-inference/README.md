# Measured local CPU results

These are actual Qwen2.5-1.5B-F16 predictions through pinned llama.cpp, the normal
PostgreSQL API and a frozen three-case source-reviewed subset. They are authored
public inputs, not fixture/emulator predictions or a private job-market sample.

[Initial generation](initial.json) preserves 0/3 valid reviewed outcomes: two
`invalid_evidence` failures and one timeout. [Source-bound generation](source-bound.json)
uses local prompt v2 and exact whole-line choices in the sampling schema. It
preserves 1/3 valid reviewed outcomes and two `invalid_evidence` failures. REV-01's
accepted prediction omits preferred Postgres and misclassifies required Python as
PREFERRED. Requirement-key recall is 1/2 and type accuracy is 0/1 on that sole
successful case; failed cases are excluded from those metric denominators. The
unseen posting extracts Python as MUST with exact offsets, but assigns frontend.
These results demonstrate a functioning provider and poor measured model quality.

Both runs pass 4 service/persistence checks with 0 failures and 0 skips. Model
failures are reported separately and are never converted to empty successes. Token
usage and engine timing are actual returned measurements; missing aggregate
measurements in the initial run remain null. Compute cost is unmeasured.

The reports retain their original development provenance (`git_dirty: true`),
including the base commit and actual Python source hash. The source-bound report's
Python source SHA-256 `f43e02fe9193d63009febd3b85e00e813844ae9afbe50e742b6372b2ec009db8`
was verified unchanged against clean implementation commit
`568a1914132a06d389ff0afb1c202e380d17cfde`. No provenance is rewritten to pretend
these development measurements ran after that commit. Actions independently runs
the same service checks against each checked-out commit and uploads its artifact.

Measurements share host/filesystem caches; this is not a controlled model/prompt
comparison. The initial run also competed with the full Python suite. Cgroup peak
memory measures that container's accounting and can exclude shared host page cache.
See [runtime, license and measurement boundaries](../../docs/local_inference.md).
