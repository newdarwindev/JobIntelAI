"""Normal browser services use the shared owned environment lifecycle."""

import json
from contextlib import contextmanager
from uuid import uuid4

from jobintel.experiments import code_provenance
from scripts.environment import Environment
from scripts.responses_environment import write_evidence


@contextmanager
def normal_api(mode, fixtures):
    project = "jobintel-browser-" + mode + "-" + uuid4().hex[:12]
    with Environment(mode, project=project, fixtures=fixtures) as session:
        info = session.info
        if mode == "local":
            evaluated = session.command(
                "exec", "-T", "api", "python", "-m", "scripts.local_evaluation", capture=True
            )
            report = json.loads(evaluated.stdout)
            report["code_provenance"] = code_provenance()
            write_evidence(session.lease.path.parent / "local-evaluation.json", report)
            write_evidence("work/persistent-browser-local-evaluation.json", report)
            info["evaluation_run_id"] = report["evaluation_run_id"]
            session.lease.ready(info)
        yield info
