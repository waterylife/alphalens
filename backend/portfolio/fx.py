"""FX rate refresh — sources daily HKDCNY/USDCNY from SAFE via akshare.

`currency_boc_safe` returns one row per business day with foreign-currency
quotes per 100 units (e.g. 美元=686.74 means 100 USD = 686.74 CNY).
"""

from __future__ import annotations

from datetime import datetime, timezone

import akshare as ak

from backend.portfolio import db


_PAIR_TO_COL = {
    "USDCNY": "美元",
    "HKDCNY": "港元",
}


def fetch_latest_rates() -> dict[str, float]:
    """Returns {'HKDCNY': 0.876, 'USDCNY': 6.867}. Raises on network error."""
    df = ak.currency_boc_safe()
    last = df.iloc[-1]
    return {pair: float(last[col]) / 100 for pair, col in _PAIR_TO_COL.items()}


def refresh_and_persist() -> tuple[dict[str, float], str]:
    """Fetch latest rates and upsert them into fx_rates. Returns (rates, as_of)."""
    rates = fetch_latest_rates()
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        for pair, rate in rates.items():
            conn.execute(
                "INSERT OR REPLACE INTO fx_rates(pair, rate, as_of) VALUES (?,?,?)",
                (pair, rate, as_of),
            )
    return rates, as_of


def get_latest_rates() -> dict[str, float]:
    """Most-recent persisted rates (no network)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT pair, rate FROM fx_rates "
            "WHERE (pair, as_of) IN ("
            "  SELECT pair, MAX(as_of) FROM fx_rates GROUP BY pair"
            ")"
        ).fetchall()
    return {r["pair"]: r["rate"] for r in rows}
