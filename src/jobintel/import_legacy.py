"""Read-only copy of legacy SQLite snapshots and candidate revisions into the new store.

This archives source records as imported comparisons with no inferred match claims.
Never opens the original database for writing.
"""

import argparse
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
    source_hash = digest(Path(source).read_bytes().hex())
    try:
        with store.connect() as db:
            for table in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                name = table["name"]
                if name.startswith("sqlite_"):
                    continue
                for index, row in enumerate(old.execute(f'SELECT * FROM "{name}"')):
                    db.execute(
                        "INSERT OR IGNORE INTO legacy_archive VALUES (?,?,?,?)",
                        (source_hash, name, str(index), json.dumps(dict(row), ensure_ascii=False)),
                    )
        snapshots = old.execute(
            "SELECT id, clean_text, source_url FROM posting_snapshots"
        ).fetchall()
        candidates = old.execute("SELECT id, payload FROM candidate_evidence").fetchall()
        for snap in snapshots:
            for candidate in candidates:
                text = json.dumps(json.loads(candidate["payload"]), ensure_ascii=False)
                key = f"legacy:{snap['id']}:{candidate['id']}"
                body_hash = digest(snap["clean_text"] + text)
                try:
                    existing = store.reserve(key, body_hash)
                except ValueError:
                    continue
                if existing:
                    continue
                store.save(
                    key,
                    body_hash,
                    snap["clean_text"],
                    text,
                    snap["source_url"],
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
