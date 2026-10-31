"""SQLite persistence, immutable input records, and atomic idempotent saves."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, job TEXT NOT NULL,
                    candidate TEXT NOT NULL, reference_url TEXT, job_sha256 TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, model TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    key TEXT PRIMARY KEY, body_sha256 TEXT NOT NULL,
                    record_id TEXT REFERENCES records(id), state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS legacy_archive (
                    source_sha256 TEXT NOT NULL, table_name TEXT NOT NULL, row_key TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(source_sha256, table_name, row_key));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def get(self, record_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        return self._view(row) if row else None

    def recent(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM records ORDER BY created_at DESC LIMIT 30").fetchall()
        return [self._view(row) for row in rows]

    def reserve(self, key: str, body_hash: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operations WHERE key=?", (key,)).fetchone()
            if row:
                if row["body_sha256"] != body_hash:
                    raise ValueError("Idempotency key belongs to another request")
                if row["state"] != "committed":
                    raise ValueError("Submission outcome uncertain or rejected; use a new key")
                record_id = row["record_id"]
            else:
                db.execute(
                    "INSERT INTO operations VALUES (?,?,?,?)", (key, body_hash, None, "pending")
                )
                record_id = None
        return self.get(record_id) if record_id else None

    def reject(self, key: str):
        with self.connect() as db:
            db.execute(
                "UPDATE operations SET state='rejected' WHERE key=? AND state='pending'", (key,)
            )

    def save(
        self,
        key: str,
        body_hash: str,
        job: str,
        candidate: str,
        reference_url: str | None,
        model: str,
        result: list[dict],
    ):
        record_id = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    datetime.now(UTC).isoformat(),
                    job,
                    candidate,
                    reference_url,
                    digest(job),
                    digest(candidate),
                    model,
                    json.dumps(result, ensure_ascii=False),
                ),
            )
            updated = db.execute(
                "UPDATE operations SET record_id=?, state='committed' "
                "WHERE key=? AND body_sha256=? AND state='pending'",
                (record_id, key, body_hash),
            )
            if updated.rowcount != 1:
                raise ValueError("Submission reservation missing")
        return self.get(record_id)

    @staticmethod
    def _view(row):
        value = dict(row)
        value["result"] = json.loads(value["result"])
        return value
