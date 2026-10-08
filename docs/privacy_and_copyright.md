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

Corpus conclusions describe only the selected input corpus. Counts and skill gaps
are evidence-linked frequencies, not statements about the general labor market or
claims of professional competence based on employer reputation.
