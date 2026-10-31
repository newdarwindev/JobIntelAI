"""Read-only copy of legacy SQLite snapshots and candidate revisions into the new store.

This archives source records as imported comparisons with no inferred match claims.
Never opens the original database for writing.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from .store import Store, digest


def import_database(source: str, destination: str) -> int:
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError("Source and destination must differ")
    old = sqlite3.connect(f"file:{Path(source).resolve()}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    store = Store(destination)
    count = 0
    with Path(source).open("rb") as source_file:
        source_hash = hashlib.file_digest(source_file, "sha256").hexdigest()
    try:
        with store.connect() as db:
            for table in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                name = table["name"]
                if name.startswith("sqlite_"):
                    continue
                quoted = name.replace('"', '""')
                for index, row in enumerate(old.execute(f'SELECT * FROM "{quoted}"')):
                    db.execute(
                        "INSERT OR IGNORE INTO legacy_archive VALUES (?,?,?,?)",
                        (source_hash, name, str(index), json.dumps(dict(row), ensure_ascii=False)),
                    )
        tables = {
            row["name"] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "match_runs" in tables:
            pairs = old.execute(
                "SELECT DISTINCT s.id AS snapshot_id, s.clean_text, s.source_url, "
                "c.id AS candidate_id, c.payload "
                "FROM match_runs m "
                "JOIN posting_snapshots s ON s.id=m.snapshot_id "
                "JOIN candidate_evidence c ON c.id=m.profile_revision_id"
            )
            for pair in pairs:
                candidate_text = json.dumps(json.loads(pair["payload"]), ensure_ascii=False)
                key = f"legacy:{pair['snapshot_id']}:{pair['candidate_id']}"
                body_hash = digest(pair["clean_text"] + candidate_text)
                existing = store.reserve(key, body_hash)
                if existing:
                    continue
                store.save(
                    key,
                    body_hash,
                    pair["clean_text"],
                    candidate_text,
                    pair["source_url"],
                    "legacy-import/no-inference",
                    [],
                )
                count += 1
    finally:
        old.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="Copy legacy SQLite source pairs, no inference")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    print(f"Imported {import_database(args.source, args.destination)} source pairs")


if __name__ == "__main__":
    main()
