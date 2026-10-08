"""Private local candidate import, explicit revision selection and match reads."""

import argparse
import json
from datetime import date
from pathlib import Path

from jobintel.config import database_url, fixture_root
from jobintel.db import session_factory
from jobintel.providers import FixtureProvider
from jobintel.schemas import CandidateProfile, MatchSelection
from jobintel.service import Service


def execute(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["candidate-import", "candidate-revisions", "match", "match-run"]
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--profile-id")
    parser.add_argument("--revision-id")
    parser.add_argument("--job-id")
    parser.add_argument("--run-id")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    factory = session_factory(database_url())
    try:
        with factory.begin() as session:
            svc = Service(session, FixtureProvider(fixture_root()))
            output = dispatch(svc, args)
        print(json.dumps(output, indent=2))
    finally:
        factory.kw["bind"].dispose()


def required(args, name):
    value = getattr(args, name)
    if not value:
        raise ValueError(f"{args.command} requires --{name.replace('_', '-')}")
    return value


def dispatch(svc, args):
    if args.command == "candidate-import":
        return svc.import_candidate(
            CandidateProfile.model_validate_json(required(args, "input").read_text())
        )
    if args.command == "candidate-revisions":
        return svc.candidate_revisions(required(args, "profile_id"))
    if args.command == "match-run":
        return svc.match_run(required(args, "run_id"))
    return svc.match(
        required(args, "job_id"),
        MatchSelection(
            profile_id=required(args, "profile_id"),
            profile_revision_id=required(args, "revision_id"),
            expected_run_id=required(args, "run_id"),
            as_of=args.as_of,
        ),
    )
