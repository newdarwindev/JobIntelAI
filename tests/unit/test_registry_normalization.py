import pytest

from jobintel.registry import normalize_url, parse_csv


def test_url_canonicalization_does_not_destroy_semantics():
    assert (
        normalize_url(" HTTPS://EXAMPLE.COM:443/Jobs/?id=2#apply ")
        == "https://example.com/Jobs/?id=2"
    )
    assert normalize_url("https://example.com/jobs") != normalize_url("https://example.com/jobs/")
    assert normalize_url(None) is None


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@example.com",
        "https://example.com:8080/jobs",
        "not-a-url",
    ],
)
def test_unsupported_urls(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_csv_requires_fields_and_typed_metadata():
    jobs = parse_csv("job_id,company,role,applied\n1,Demo,Engineer,false\n")
    assert jobs[0].applied is False
    with pytest.raises(ValueError):
        parse_csv("job_id,company,role,applied\n1,Demo,Engineer,maybe\n")
    with pytest.raises(ValueError):
        parse_csv("company,role\nDemo,Engineer\n")


def test_aliases_preserve_distinct_concepts_and_unknowns(taxonomy, requirement):
    assert taxonomy.canonical(" POSTGRES ") == "PostgreSQL"
    assert taxonomy.canonical("K8s") == "Kubernetes"
    assert taxonomy.canonical("GenAI") == "Generative AI"
    assert taxonomy.canonical("AWS") != taxonomy.canonical("AWS Bedrock")
    assert taxonomy.canonical("Python 3.12") == "Python 3.12"
    result = taxonomy.normalize(requirement)
    assert result.raw_text == requirement.raw_text
    assert result.evidence == requirement.evidence
