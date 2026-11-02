# storage.py
# ------------------------------------------------------------
# Power-loss safe buffer for readings that are not uploaded yet.
#
# Backed by SQLite in WAL mode with synchronous=FULL: every append is one
# committed transaction that is on the card before append() returns. A power
# cut can lose at most the entry being written, never earlier entries, and
# the file can never end up half-written.
#
# Rows are deleted only after the API has confirmed the upload. Each row has
# a monotonically increasing seq (AUTOINCREMENT never reuses numbers), which
# the power-cut test uses to prove that no committed entry was lost.
# ------------------------------------------------------------

import glob
import json
import os
import sqlite3
import threading
from typing import Dict, List, Tuple

from module.utils.logger import setup_custom_logger

log = setup_custom_logger("module.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL
)
"""


class ReadingBuffer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # One shared connection guarded by a lock; the app is low-volume.
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(SCHEMA)
        self._conn.commit()
        self._check_integrity()

    def _check_integrity(self) -> None:
        result = self._conn.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            log.error(f"Buffer integrity check failed: {result}")

    def append(self, entry: Dict) -> int:
        """Store one entry durably. Returns its seq."""
        payload = json.dumps(entry, separators=(",", ":"))
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO readings (payload) VALUES (?)", (payload,)
            )
            return cur.lastrowid

    def oldest(self, limit: int) -> List[Tuple[int, Dict]]:
        """Return up to `limit` of the oldest pending entries as (seq, entry)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, payload FROM readings ORDER BY seq LIMIT ?", (limit,)
            ).fetchall()
        return [(seq, json.loads(payload)) for seq, payload in rows]

    def delete_through(self, max_seq: int) -> None:
        """Delete all entries with seq <= max_seq (after a confirmed upload)."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM readings WHERE seq <= ?", (max_seq,))

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def checkpoint(self) -> None:
        """Fold the WAL back into the main file (call before shutdown)."""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def import_legacy_json(self, directory: str) -> None:
        """Import buffers left by the old JSON-file implementation.

        The old buffer was a JSON list rewritten in place. Any *.json file in
        `directory` is imported in one transaction and then renamed to
        *.imported, so it is never imported twice. Unreadable files are
        renamed to *.corrupt and kept for manual inspection.
        """
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw) if raw.strip() else []
                if not isinstance(data, list):
                    raise ValueError("not a JSON list")
            except (OSError, ValueError) as e:
                log.error(f"Could not read legacy buffer {path}: {e}")
                os.replace(path, path + ".corrupt")
                continue

            with self._lock, self._conn:
                self._conn.executemany(
                    "INSERT INTO readings (payload) VALUES (?)",
                    [(json.dumps(e, separators=(",", ":")),) for e in data],
                )
            os.replace(path, path + ".imported")
            log.info(f"Imported {len(data)} entries from legacy buffer {path}")
