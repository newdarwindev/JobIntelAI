"""Measure B/C on frozen reviewed inputs using an already-running scoped local service."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from jobintel.experiment_cli import save_checkpoint, selected_experiment_provider
from jobintel.experiment_reviewed import freeze_reviewed
from jobintel.experiments import ExperimentSpec, rescore, run_experiment
from jobintel.local_model import MODEL
from jobintel.openai_transport import EMULATOR_MODEL


class CountedTransport:
    def __init__(self, transport):
        self.transport = transport
        self.requests = []

    def complete(self, payload):
        from jobintel.experiment_corpus import digest

        self.requests.append(digest(payload))
        return self.transport.complete(payload)


def measure(name, endpoint=None):
    cases = ["REV-01", "REV-23", "REV-25"] if name == "local" else ["REV-01"]
    corpus = freeze_reviewed(Path("data"), cases)
    spec = ExperimentSpec(
        configurations=["B", "C"],
        model=MODEL if name == "local" else EMULATOR_MODEL,
        max_calls=len(cases) * 2,
        max_input_tokens=6144 if name == "local" else 32000,
        max_output_tokens=2048,
    )
    provider = selected_experiment_provider(name, None, endpoint)
    transport = CountedTransport(provider.transport)
    provider.transport = transport
    with TemporaryDirectory(prefix="jobintel-experiment-") as directory:
        path = Path(directory) / "report.json"
        report = run_experiment(
            provider, corpus, spec, checkpoint=lambda current: save_checkpoint(path, current)
        )
        save_checkpoint(path, report)
        saved = json.loads(path.read_text())
    count = len(transport.requests)
    scores = rescore(saved)
    assert [r["summary"] for r in scores["results"]] == [r["summary"] for r in saved["results"]]
    assert len(transport.requests) == count == spec.max_calls
    assert transport.requests[: len(cases)] == transport.requests[len(cases) :]
    assert all(
        r["status"] != "not_attempted" for result in saved["results"] for r in result["records"]
    )
    return {
        "status": "passed",
        "execution_mode": provider.mode,
        "observed_http_attempts": count,
        "request_sha256": transport.requests,
        "identical_B_C_requests": True,
        "rescore_without_requests": True,
        "report": saved,
        "scores": scores,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["local", "emulator"], required=True)
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    print(json.dumps(measure(args.provider, args.endpoint), ensure_ascii=False))


if __name__ == "__main__":
    main()
