"""Планирование, запуск notebook execution и проверка artifacts без hosted credentials."""

import argparse
import json
from pathlib import Path

from jobintel.experiment_corpus import read_json
from jobintel.notebook_artifacts import verify_manifest
from jobintel.notebook_contracts import NotebookRejected, NotebookRequest
from jobintel.notebook_runs import plan_notebook, run_notebook


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "run", "verify"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args(arguments)
    try:
        manifest = execute(args)
    except (ValueError, OSError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, NotebookRejected) else "invalid_input"
        parser.exit(2, f"Запуск notebook отклонён ({code}).\n")
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0 if manifest.status in {"planned", "succeeded"} else 1


def execute(args):
    if args.action == "verify":
        if not args.manifest or args.config or args.output:
            raise NotebookRejected("verify_arguments")
        return verify_manifest(args.manifest)
    if not args.config or args.manifest:
        raise NotebookRejected("config_required")
    value = read_json(args.config)
    if args.output is not None:
        value["output"] = str(args.output)
    request = NotebookRequest.model_validate(value)
    runner = plan_notebook if args.action == "plan" else run_notebook
    return runner(request, data_root=args.data_root)
