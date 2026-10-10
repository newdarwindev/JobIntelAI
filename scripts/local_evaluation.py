"""Run a fixed, source-reviewed three-case CPU evaluation and persist every outcome."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from jobintel.db import session_factory
from jobintel.evaluation_corpus import REVIEWED_CORPUS_SHA256, load_reviewed
from jobintel.evaluation_runs import case_record, result_summary
from jobintel.evaluation_store import save_report
from jobintel.local_model import MODEL, MODEL_SHA256, model_identity
from jobintel.normalization import Taxonomy
from jobintel.provider_config import digest, identity
from jobintel.providers import selected_provider

# Selected before model execution: ordinary requirements, alternatives/versions and abstention.
CASE_IDS = ["REV-01", "REV-23", "REV-25"]


def evaluate(root):
    corpus = load_reviewed(root)
    cases = [next(case for case in corpus.cases if case.case_id == key) for key in CASE_IDS]
    taxonomy = Taxonomy(root / "taxonomy.json")
    provider = selected_provider(root, "local")
    configuration = "local_normalized_v1"
    started = perf_counter()
    records = [case_record(provider, case, configuration, corpus, taxonomy) for case in cases]
    return {
        "format_version": 2,
        "dataset": "reviewed",
        "dataset_revision": "source-reviewed-v1/local-three-case-v1",
        "dataset_size": len(cases),
        "case_ids": CASE_IDS,
        "parent_dataset_sha256": REVIEWED_CORPUS_SHA256,
        "dataset_sha256": digest([case.model_dump(mode="json") for case in cases]),
        "review": corpus.review.model_dump(),
        "mode": "local CPU inference — fixed source-reviewed subset; one automated reviewer",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "partial" if any(record["error"] for record in records) else "completed",
        "results": [
            {
                "configuration": configuration,
                "identity": {
                    **identity("local", configuration, MODEL, taxonomy),
                    **model_identity(),
                    "execution_mode": "local-inference",
                },
                "model_sha256": MODEL_SHA256,
                "configuration_sha256": digest(
                    {"configuration": configuration, "identity": model_identity()}
                ),
                "per_case": records,
                "provenance": [record["provenance"] for record in records],
                "elapsed_seconds": perf_counter() - started,
                **result_summary(records, cases, None),
            }
        ],
    }


def main():
    report = evaluate(Path("data"))
    factory = session_factory(os.environ["JOBINTEL_DATABASE_URL"])
    with factory.begin() as session:
        saved = save_report(session, report)
    print(json.dumps(saved, ensure_ascii=False))


if __name__ == "__main__":
    main()
