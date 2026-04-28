"""SQLite store for portfolio holdings.

Schema is intentionally close to the user's Google Sheet columns to keep the
seed import dumb. All monetary fields are persisted both in the original
currency (when known) and pre-converted to CNY so the API can serve fast
aggregations without re-running FX math.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


_CANONICAL_DB_PATH = Path.home() / "Code" / "alphalens" / ".cache" / "portfolio.sqlite"

_DEFAULT_DB_PATH = Path(os.environ.get("ALPHALENS_PORTFOLIO_DB", _CANONICAL_DB_PATH))


SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market          TEXT NOT NULL,             -- 中国 / 香港 / 美国
    asset_class     TEXT NOT NULL,             -- 股票 / 债券 / 黄金 / 现金 ...
    tag_l1          TEXT,
    tag_l2          TEXT,
    name            TEXT NOT NULL,
    code            TEXT,                      -- nullable: cash entries have no code
    currency        TEXT NOT NULL,             -- CNY / HKD / USD
    current_price   REAL,                      -- in original currency
    cost_price      REAL,                      -- in original currency
    quantity        REAL,
    cost_value_cny    REAL NOT NULL,
    market_value_cny  REAL NOT NULL,
    unrealized_pnl_cny REAL,
    return_pct      REAL,
    broker          TEXT NOT NULL,             -- 富途证券 / 东方财富 / 天天基金 / 蚂蚁财富 ...
    as_of           TEXT NOT NULL,             -- ISO timestamp
    source_run_id   INTEGER,
    UNIQUE(broker, market, name, code)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,                 -- seed / futu / screenshot:tiantian / ...
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,                 -- ok / error
    n_rows      INTEGER,
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS fx_rates (
    pair       TEXT NOT NULL,                  -- HKDCNY / USDCNY
    rate       REAL NOT NULL,
    as_of      TEXT NOT NULL,
    PRIMARY KEY (pair, as_of)
);
"""


def db_path() -> Path:
    return _DEFAULT_DB_PATH


@contextmanager
def connect():
    path = _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def reset() -> None:
    """Drop and recreate all portfolio tables. Used by the seed script."""
    with connect() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS holdings;"
            "DROP TABLE IF EXISTS sync_runs;"
            "DROP TABLE IF EXISTS fx_rates;"
        )
        conn.executescript(SCHEMA)
