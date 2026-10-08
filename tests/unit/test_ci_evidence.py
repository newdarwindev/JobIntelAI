"""V43-V44: truthful leaf counts and audited reproducible source/wheel releases."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.audit_release import audit
from scripts.summarize_tests import test_counts as junit_counts

ROOT = Path(__file__).resolve().parents[2]


def test_v43_nested_junit_counts_do_not_double_count_totals(tmp_path):
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite tests="4" failures="1" errors="1" skipped="1">'
        '<testsuite tests="4" failures="1" errors="1" skipped="1">'
        '<testcase name="pass"/><testcase name="fail"><failure/></testcase>'
        '<testcase name="error"><error/></testcase><testcase name="skip"><skipped/></testcase>'
        "</testsuite></testsuite></testsuites>"
    )
    assert junit_counts(report) == {"tests": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1}
    assert all(value is None for value in junit_counts(tmp_path / "absent.xml").values())


@pytest.mark.parametrize(
    "name,contents",
    [
        ("local_data/profile.json", b"private"),
        ("jobintel/private.key", b"private"),
        (".env", b"private"),
        ("data/unlicensed.txt", b"unreviewed posting"),
        ("jobintel/unexpected.txt", b"-----BEGIN " + b"PRIVATE KEY-----"),
        ("jobintel/unexpected.json", b"JOBINTEL_PRIVATE_" + b"RELEASE_SENTINEL"),
    ],
    ids=[
        "private-directory",
        "key-file",
        "environment-file",
        "unlicensed-fixture",
        "key-content",
        "sentinel-content",
    ],
)
def test_v44_release_audit_rejects_private_paths_keys_and_unlicensed_content(
    tmp_path, name, contents
):
    wheel = tmp_path / "bad.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("package.dist-info/licenses/LICENSE", b"Authored license")
        archive.writestr(name, contents)
    with pytest.raises(ValueError):
        audit(wheel, {})


def test_v44_build_excludes_ignored_private_outputs_and_bundles_licensed_fixtures(tmp_path):
    source = tmp_path / "fresh-source"
    source.mkdir()
    for name in [
        "pyproject.toml",
        "MANIFEST.in",
        "README.md",
        "LICENSE",
        "alembic.ini",
        "requirements.lock.txt",
    ]:
        shutil.copy(ROOT / name, source / name)
    for name in ["src", "data", "alembic"]:
        shutil.copytree(
            ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info")
        )
    marker = b"JOBINTEL_PRIVATE_" + b"RELEASE_SENTINEL"
    for name in [
        "local_data/profile.json",
        "work/posting.txt",
        "results/generated/private.csv",
        ".env",
        "src/jobintel/private.key",
    ]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(marker)
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    public_data = {
        str(path.relative_to(ROOT)): path.read_bytes()
        for path in (ROOT / "data").rglob("*")
        if path.is_file()
    }
    artifacts = list((source / "dist").iterdir())
    assert len(artifacts) == 2
    reports = [audit(path, public_data) for path in artifacts]
    assert all(report["audit"] == "passed" for report in reports)
    assert sorted(report["fixture_files"] for report in reports) == [0, len(public_data)]
