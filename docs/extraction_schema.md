# Extraction schema v2

New provider responses, fixture replay, golden labels, persistence writes, and API
extractions use `schema_version: 2`. API reads also report
`stored_schema_version` so clients can distinguish a compatibility projection
from a newly validated run. The released initial Alembic migration is unchanged.
The following migration adds a run version column with default 1 for old rows;
new service writes explicitly use 2. Historical JSON and snapshot text stay intact.

Geography and work mode are null when absent, ambiguous, or unsupported. A populated
value is `{value, evidence: {quote, start, end}}`. Filters are null when absent;
each populated item has a strict kind (work_authorization, travel, residency, or
attendance), a literal value and evidence. Offsets count Unicode code points,
including non-BMP characters, in the immutable clean source. Every populated span
is revalidated at the service boundary before any extraction row is written.

Metadata also receives conservative relevance checks. Geography must quote an
explicit job/role/position location or "remote work within"/"onsite in" statement.
Company addresses, headquarters and offices cannot supply job geography or mode.
Negated, conditional and conflicting modes remain unknown. Filter kinds need their
corresponding source cue and literal value. These checks admit a narrow English
grammar; unsupported wording must abstain. They do not replace independent semantic
annotation or establish general language understanding.

Requirement type, years, experience obligation and production obligation are
separate fields. Obligations are MUST/PREFERRED/UNKNOWN. Production preference
uses PREFERRED and `explicit_production_required: false`; absent production is
UNKNOWN with null. The evidence must explicitly support populated years and
obligations. English number words zero through ten and numeric ranges such as
"three or more years of Python experience" and "two to four years of Java
experience" are supported. Unsupported tenure wording stays null. EXPERIENCE
remains a separate analytics type and is never automatically counted as MUST.

Version constraints bind to individual skill branches. Each retains a product,
source product, comparator (EQ/GTE/GT/LTE/LT), numeric version, exact raw wording,
and its own evidence nested within the requirement span. Accepted forms include
"Python 3.11+", "Python >=3.11", "Python 3.11 or later" and analogous comparison
operators. Dotted versions cannot be dropped into unversioned skills. Canonical
aliases change product/display labels while preserving source wording and spans.
Incompatible versions and distinct products retain separate branch labels.
Alias deduplication retains the original ANY/ALL operator and source skill terms,
including groups with only one distinct canonical branch. Candidate version
matching abstains until sourced candidate predicates are implemented.

Unversioned/v1 stored extraction JSON is read through a compatibility projection:
ungrounded scalar geography/mode become null; ambiguous historical production
flags become null/UNKNOWN; experience obligation stays UNKNOWN and version strings
remain verbatim. The original JSON is never rewritten or retroactively certified.
v1 frozen experiment reports can still be checked against their original hashes
and rescored through this projection; their original provenance stays intact.
Unknown schema versions fail explicitly. v1 fixture responses and golden labels
must be reannotated with source evidence and regenerated as v2; they are not silently
upgraded into provider claims. The generator and source pin make the authored v2
corpus reproducible. Existing published v1 experiment reports remain historical.
