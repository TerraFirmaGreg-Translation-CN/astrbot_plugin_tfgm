"""Small local SQLite outbox. Cursor and enqueued events commit together."""

import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cursors (
                server TEXT PRIMARY KEY, endpoint TEXT, instance TEXT, seq INTEGER);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, target TEXT, kind TEXT, payload TEXT,
                created REAL, expires REAL, status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, error TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS job_target ON jobs(target,status,next_at);
            CREATE TABLE IF NOT EXISTS history (
                session TEXT PRIMARY KEY, messages TEXT, updated REAL);
            CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER);
        """)
        # A crash during QQ/AI execution is ambiguous. Never replay these automatically.
        self.db.execute(
            "UPDATE jobs SET status='failed',error='interrupted_ambiguous' WHERE status='working' AND kind IN ('qq','ai')"
        )
        self.db.execute("UPDATE jobs SET status='pending' WHERE status='working' AND kind='mc'")
        self.db.commit()

    def count(self, name, amount=1):
        self.db.execute(
            "INSERT INTO counters VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value",
            (name, amount),
        )

    def cursor(self, server, endpoint):
        row = self.db.execute(
            "SELECT * FROM cursors WHERE server=? AND endpoint=?", (server, endpoint)
        ).fetchone()
        return dict(row) if row else None

    def set_cursor(self, server, endpoint, instance, seq):
        self.db.execute(
            "INSERT OR REPLACE INTO cursors VALUES (?,?,?,?)", (server, endpoint, instance, seq)
        )

    def enqueue(self, job_id, target, kind, payload, ttl, capacity, created=None):
        now = time.time()
        created = now if created is None else created
        if created + ttl <= now:
            self.count("expired")
            return False
        if self.db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            return False
        pending = self.db.execute(
            "SELECT COUNT(*) FROM jobs WHERE target=? AND status IN ('pending','working')",
            (target,),
        ).fetchone()[0]
        if pending >= capacity:
            self.count("queue_full")
            return False
        self.db.execute(
            "INSERT INTO jobs(id,target,kind,payload,created,expires) VALUES (?,?,?,?,?,?)",
            (job_id, target, kind, json.dumps(payload, ensure_ascii=False), created, created + ttl),
        )
        return True

    def claim(self, target):
        now = time.time()
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status='failed',error='expired' WHERE target=? AND status='pending' AND expires<=?",
                (target, now),
            )
            # Head-of-line ordering: a delayed retry must not be overtaken.
            row = self.db.execute(
                "SELECT * FROM jobs WHERE target=? AND status='pending' ORDER BY rowid LIMIT 1",
                (target,),
            ).fetchone()
            if not row or row["next_at"] > now:
                return None
            self.db.execute(
                "UPDATE jobs SET status='working',attempts=attempts+1 WHERE id=?", (row["id"],)
            )
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        job["attempts"] += 1
        return job

    def finish(self, job, status="done", error=""):
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status=?,error=? WHERE id=?", (status, error, job["id"])
            )
            self.count(status)

    def retry(self, job, payload, delay):
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status='pending',payload=?,next_at=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), time.time() + delay, job["id"]),
            )

    def save_payload(self, job, payload):
        with self.db:
            self.db.execute(
                "UPDATE jobs SET payload=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), job["id"]),
            )

    def history(self, session, hours):
        row = self.db.execute(
            "SELECT messages,updated FROM history WHERE session=?", (session,)
        ).fetchone()
        return json.loads(row[0]) if row and row[1] > time.time() - hours * 3600 else []

    def save_history(self, session, messages):
        self.db.execute(
            "INSERT OR REPLACE INTO history VALUES (?,?,?)",
            (session, json.dumps(messages, ensure_ascii=False), time.time()),
        )

    def prune(self, retention_hours, history_hours):
        with self.db:
            self.db.execute(
                "UPDATE jobs SET status='failed',error='expired' WHERE status='pending' AND expires<=?",
                (time.time(),),
            )
            self.db.execute(
                "DELETE FROM jobs WHERE status IN ('done','failed') AND created<?",
                (time.time() - retention_hours * 3600,),
            )
            self.db.execute(
                "DELETE FROM history WHERE updated<?", (time.time() - history_hours * 3600,)
            )

    def summary(self):
        return {
            "queues": [
                dict(r)
                for r in self.db.execute(
                    "SELECT target,status,COUNT(*) AS count FROM jobs GROUP BY target,status"
                )
            ],
            "counters": dict(self.db.execute("SELECT name,value FROM counters")),
        }

    def close(self):
        self.db.close()
