"""Read saved corpus aggregates without invoking extraction or live providers."""

import argparse
import json

from jobintel.config import database_url
from jobintel.corpus_analytics import AnalyticsInput, AnalyticsService
from jobintel.db import session_factory


def execute(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["analytics"])
    parser.add_argument("--applied", choices=["true", "false"])
    parser.add_argument("--remote", choices=["true", "false"])
    parser.add_argument("--profile-id")
    parser.add_argument("--revision-id")
    args = parser.parse_args(argv)
    request = AnalyticsInput(
        applied=None if args.applied is None else args.applied == "true",
        remote=None if args.remote is None else args.remote == "true",
        profile_id=args.profile_id,
        profile_revision_id=args.revision_id,
    )
    factory = session_factory(database_url())
    try:
        with factory() as session:
            report = AnalyticsService(session).report(request)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        factory.kw["bind"].dispose()
