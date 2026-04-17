"""SQLite-backed cache for akshare responses.

Strategy:
- Each cache entry is keyed by (namespace, key) and stores pickled bytes + timestamp.
- Callers specify a TTL; expired entries are transparently refetched.
- Data-source responses for historical series are cached with long TTL (hours),
  intraday snapshots with short TTL (minutes).
"""

from __future__ import annotations

import os
import pickle
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable


_DEFAULT_DB_PATH = Path(os.environ.get(
    "ALPHALENS_CACHE_DB",
    Path(__file__).resolve().parents[2] / ".cache" / "akshare.sqlite",
))


class Cache:
    def __init__(self, db_path: Path = _DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    stored_at REAL NOT NULL,
                    PRIMARY KEY (namespace, key)
                )
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, namespace: str, key: str, ttl_seconds: float) -> Any | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, stored_at FROM cache WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
        if row is None:
            return None
        payload, stored_at = row
        if time.time() - stored_at > ttl_seconds:
            return None
        return pickle.loads(payload)

    def set(self, namespace: str, key: str, value: Any) -> None:
        payload = pickle.dumps(value)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache(namespace, key, payload, stored_at) VALUES (?,?,?,?)",
                (namespace, key, payload, time.time()),
            )

    def fetch(
        self,
        namespace: str,
        key: str,
        ttl_seconds: float,
        producer: Callable[[], Any],
    ) -> Any:
        cached = self.get(namespace, key, ttl_seconds)
        if cached is not None:
            return cached
        value = producer()
        self.set(namespace, key, value)
        return value


# Module-level singleton — cheap, avoids passing around explicitly.
cache = Cache()
