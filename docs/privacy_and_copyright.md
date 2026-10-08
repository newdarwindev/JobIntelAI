# Privacy and copyright

All `data/sample_jobs` postings, registry companies and candidate facts are fictional
and authored for this repository. No real application history or recruiter details
are included. The original project brief is preserved separately as user-supplied
requirements, not as candidate evidence or a third-party job corpus.

Store real job-search logs, candidate records, snapshots and private experiment
outputs in ignored `local_data/` or outside the checkout. `.env`, databases and
generated results are ignored. Ignore rules do not remove previously tracked files;
check the actual staged diff before committing. Never publish employer code/data,
correspondence, addresses, credentials or full third-party postings without rights.

Public access to a job URL permits neither unrestricted crawling nor republication.
Respect access restrictions; use manual text rather than bypassing anti-bot systems.
No automatic applications or messages. Do not log full private source/provider
payloads. Avoid including private URLs or source quotes in public evaluation output.

The API is unauthenticated local single-user tooling. Bind it to loopback, not a
public endpoint. Demo database passwords in Compose/CI are local placeholders only.
Live API credentials belong in secure runtime settings; do not put them in Git.

The `jobintel.outcomes` logger emits JSON at INFO for imports, snapshots, fetching, extraction,
candidate revisions and matching. Enable this named logger through your application's
logging configuration. Outcomes are emitted after transaction commit or rollback,
including savepoint handling; successful work is not reported before commit. Fields
are operation/outcome, generated storage IDs, a hash of the subject, elapsed milliseconds
and allowlisted error codes. Job/profile names, URLs, source/candidate bodies,
provider responses and exception text are excluded. SQLAlchemy hides bound parameters
in exception rendering. These guarantees do not cover custom SQL logging configured
outside this application, or logging request/response bodies in external middleware.
Acquisition URLs and successful source bodies remain in the local database; attempt
history is not a public report. Failed HTTP bodies and raw response headers are not
stored or logged. The transport sends fixed headers without cookies, authorization,
referrers or browser execution, validates every destination and refuses access gates.
CI and videos use authored responses only; no real job URL smoke is implied.

Backend Actions artifacts contain synthetic test JUnit, sanitized command diagnostics,
counts/provenance and release audit hashes, retained for 30 days. Private runtime files
are excluded from wheel/source releases; the source release carries the authored BSD
licensed fixtures needed to reproduce the offline README workflow.

Corpus conclusions describe only the selected input corpus. Counts and skill gaps
are evidence-linked frequencies, not statements about the general labor market or
claims of professional competence based on employer reputation.
