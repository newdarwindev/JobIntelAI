"""EXEC-01/04/05: execute real fresh-kernel boundaries with no provider or database."""

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from jobintel.experiment_corpus import write_json
from jobintel.experiments import code_provenance

ROOT = Path(__file__).resolve().parents[1]


def notebook_source(directory):
    return f"""
import json
import sys
from pathlib import Path
import httpx
from jobintel import db
from jobintel.notebook_contracts import NotebookRequest, NotebookRejected
from jobintel.notebook_runs import run_notebook
from jobintel.experiment_corpus import read_json

def forbidden(*args, **kwargs):
    raise AssertionError('database or HTTP access in offline kernel')

httpx.Client.request = forbidden
db.session_factory = forbidden
assert sys.prefix == {sys.prefix!r}
root = Path({str(ROOT / "data")!r})
directory = Path({str(directory)!r})
fixture = run_notebook(NotebookRequest(output=directory / 'fixture'), data_root=root)
assert fixture.status == 'succeeded' and fixture.evidence_mode == 'fake'
saved = run_notebook(NotebookRequest(mode='saved-report',
    report=directory / 'fixture' / 'report.json', output=directory / 'saved'), data_root=root)
assert saved.mode == 'saved-report' and saved.evidence_mode == 'fake'
assert read_json(directory / 'fixture' / 'scores.json') == read_json(directory / 'saved' / 'scores.json')
try:
    run_notebook(NotebookRequest(output=directory / 'refused', corpus_sha256='0' * 64), data_root=root)
except NotebookRejected as error:
    assert error.code == 'corpus_checksum'
else:
    raise AssertionError('bad input was accepted')
assert not (directory / 'refused').exists()
print(json.dumps({{'fresh_kernel': True, 'same_environment': True,
    'fixture_status': fixture.status, 'saved_rescore_equal': True,
    'preflight_refused': True, 'database_and_http_forbidden': True,
    'corpus_sha256': fixture.parameters['corpus_sha256']}}))
"""


def execute_kernel(directory):
    import nbformat
    from nbclient import NotebookClient

    notebook = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell(notebook_source(directory))]
    )
    environment = {
        **os.environ,
        "JOBINTEL_PROVIDER": "openai",
        "JOBINTEL_DATABASE_URL": "postgresql://must-not-connect/private",
        "OPENAI_API_KEY": "offline-kernel-sentinel",
        "JOBINTEL_FIXTURE_ROOT": str(directory / "private-inputs"),
    }
    executed = NotebookClient(notebook, timeout=120, kernel_name="python3").execute(
        cwd=str(ROOT), env=environment
    )
    output = "".join(o.get("text", "") for o in executed.cells[0].outputs)
    return json.loads(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work/ci/notebook-kernel.json"))
    args = parser.parse_args()
    with TemporaryDirectory(prefix="jobintel-notebook-") as directory:
        result = execute_kernel(Path(directory))
    report = {"python": sys.version.split()[0], "code": code_provenance(), "checks": result}
    write_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
