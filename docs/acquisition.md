# Bounded URL acquisition

`POST /jobs/{id}/fetch` acquires the registered official URL through `HttpAcquirer`.
The transport, resolver, policy, clock and waits are injectable; CI supplies only
authored offline responses. The normal API uses `HttpTransport`/`DNSResolver`.
No fetching occurs during import, snapshot submission, extraction or API startup.

## Limits and destination safety

| Bound | Default | Supported maximum |
| --- | --- | --- |
| Connect / DNS timeout | 3 seconds | 10 seconds |
| Read inactivity timeout | 5 seconds | 10 seconds |
| Total acquisition deadline, including DNS, redirects and waits | 20 seconds | 60 seconds |
| Attempts per URL/hop | 3 | 3 |
| Redirects | 3 | 3 |
| Wire bytes and decompressed bytes | 200,000 each | 200,000 each |
| Exponential backoff base | 0.5 seconds | 10 seconds |
| Retry-After / backoff wait cap | 2 seconds | 10 seconds |

Construct `FetchPolicy` in application setup to lower/change these limits; the
public route cannot disable them. The default backoff is 0.5 then 1 second. Numeric
and HTTP-date Retry-After values are capped; a wait that would exhaust the deadline
stops acquisition. Connect/read/network/DNS failures, 429 and 5xx retry within the
shared budget. TLS, proxy/access refusal, invalid redirects and content failures do
not retry. Three retries at every permitted hop allow at most 12 requests, still
bounded by the shared deadline. DNS waiting and socket I/O have deadline guards;
a stalled system resolver thread is daemonized and cannot extend the caller's wait.

URLs are credential-free HTTP(S) on standard ports 80 or 443, with bounded
length, no control/whitespace characters and valid IDNA hostnames. HTTPS redirects
cannot downgrade to HTTP. Each hop and retry resolves anew, rejects the entire
answer set if any address is private, loopback, link-local, metadata, multicast,
reserved, scoped IPv6 or an IPv4-mapped/transition address, and selects a numeric
public IP. The transport connects to that IP and verifies the direct peer before
sending HTTP. Host and TLS SNI/certificate identity use the original hostname.
Redirect loops and a fourth redirect fail before any request to that extra hop.

Environment HTTP/HTTPS proxy settings and `NO_PROXY` are honored. Supported proxies
are credential-free **HTTP** gateways: HTTP uses the pinned IP in the absolute
request target; HTTPS sends CONNECT to the pinned IP (bracketed for IPv6), then
verifies TLS against the original hostname. The administrator's gateway may be
private, but the job destination must pass the same public-IP checks. Proxy refusal
never causes a direct retry; authenticated, HTTPS and SOCKS proxies fail explicitly.
A hostname-only gateway policy may refuse numeric CONNECT: use manual entry or
administrator-approved proxy configuration. Fixed request headers carry no cookies,
authorization or referrers. Certificates and configured CA trust remain verified.

## Content and immutable provenance

Only `text/plain`, `text/html` and `application/xhtml+xml` are accepted. Supported
declared charsets are UTF-8, UTF-8-SIG, ASCII, Latin-1 and Windows-1252; absent charset
means strict UTF-8. Invalid text/NUL, empty content, PDF/binary types, oversized or
truncated bodies and unsupported compression require manual entry. Identity, gzip
and zlib-wrapped deflate are supported with bounded streaming decompression; malformed,
truncated or concatenated compressed streams are rejected. No content sniffing or
browser execution occurs. Recognized CAPTCHA/access-check and JavaScript-only
empty/loading/noscript shells also require manual entry. Unrecognized site layouts
can still need manual review; this is a conservative cleaner, not a universal ATS parser.

Usable decoded raw text/HTML is retained exactly, including a UTF-8 BOM. Successful
attempt metadata records the SHA-256 and length of the decompressed bytes, MIME and
charset, so different wire encodings retain distinct attempt provenance. Clean
snapshots remove scripts/styles/title/navigation/forms/cookies, prefer main/article
before authored ATS selectors, and preserve inline wording, list/table clauses and
Unicode line breaks. The clean-text SHA-256 uses UTF-8; quote offsets count Unicode
code points. Authored ATS/malformed fixtures verify retained required clauses.

Latest identical raw + clean + URL reuses the existing snapshot without changing
its timestamp/status. Changed raw with the same clean hash appends a new source;
current extraction becomes stale while historical runs remain readable. HTTP reuse
of a manual source keeps the manual snapshot's provenance and records the new HTTP
attempt separately. This immutability is enforced by supported services/routes,
not by a database restriction against direct SQL modification.

## Outcomes, API and manual recovery

Each fetch has a generated `fetch_id`; immutable `acquisition_attempts` records
retain ordered attempts, UTC timestamps, original/requested/final URLs, redirect and
retry indexes, wait duration, HTTP status, error code and retryability. Refusals
before HTTP are recorded with a null HTTP status. Only success links a snapshot.
Failed response bodies, arbitrary upstream headers and exception text are neither
stored in attempts nor logged. URLs and successful snapshots remain private local
database content; history should not be published as a real-job report.

Success returns **201** with `fetch_id`, `status=success`, `snapshot_id`,
`content_hash` and `attempts`. Expected failures return the same envelope with
`status=failed`, null source fields and
`detail={code,message,retryable,manual_fallback:true}`:

| HTTP status | Failure |
| --- | --- |
| 403 | Access denial / recognized CAPTCHA |
| 413 | Wire/decompressed size limit |
| 415 | Unsupported MIME / invalid compression |
| 422 | Invalid/blocked destination, redirect, text, empty/JS-only source |
| 502 | TLS/proxy/network/DNS failure, exhausted 5xx or other unusable HTTP status |
| 503 | Exhausted upstream 429 |
| 504 | Connect/read/DNS timeout or exhausted deadline |

Expected failures commit their attempts and leave the previous source/extraction
current. Database failures return the application's sanitized **503** and roll back
all snapshot/attempt writes together; no success is published before commit.
Missing jobs return 404 and jobs without a URL return 422 without HTTP attempts.
`GET /jobs/{id}/history` includes read-only `acquisition_attempts` alongside immutable
snapshots and extraction runs. Supported update/delete requests are rejected.

The source workbench shows the acquisition mode and saved attempt history. Failure
refreshes history while preserving unsaved manual editor fields and prior usable
results. Manual save/extract is the recovery path; no bypass or rendering is attempted.
Fixture extraction still accepts only known authored clean hashes; arbitrary fetched
sources require explicitly configured provider setup.

The demo's `synthetic` mode recognizes authored `https://example.com/authored-job`
(redirect to `authored-final`) and `authored-js`; other demo destinations return an
authored access denial. It runs the same bounded acquirer/service with fake DNS and
HTTP, never a real-network fallback. UI02 covers success and 403/JS manual recovery
on desktop/mobile. Backend V02–V07/V09–V11 cover adversarial transport/persistence
boundaries. Authorized real URL smoke and optional browser rendering V08 are separate
from this offline CI evidence; no paid provider calls or real postings are recorded.
