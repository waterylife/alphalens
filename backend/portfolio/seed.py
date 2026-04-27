"""One-shot importer that seeds the local SQLite portfolio store from the CSV
exported from the user's Google Sheet.

CSV layout (1-indexed):
    Row 1: HKDCNY rate in column 6 (e.g. 0.872489)
    Row 2: USDCNY rate in column 6
    Row 3: blank
    Row 4: header (col 1 empty, then 市场, 资产类型, ..., 交易平台)
    Row 5..N: positions
    Last row: 全市场 totals row — skipped

Usage:
    python -m backend.portfolio.seed /path/to/portfolio_seed.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.portfolio import db


# Anything that isn't a digit, dot, or minus sign — covers ￥, ¥, %, commas
_NON_NUMERIC = re.compile(r"[^0-9.\-]")


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    cleaned = _NON_NUMERIC.sub("", s)
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


_CODE_LIKE = re.compile(r"^[A-Za-z0-9]+$")
_TICKER_LIKE = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")


def _split_name_code(raw: str) -> tuple[str, str | None]:
    """Extract (name, code) from the user's '名称/代码' convention.

    Cases:
      '腾讯控股/00700'    → ('腾讯控股', '00700')   slash + code-like tail
      '港元/美元货币基金'  → ('港元/美元货币基金', None)  slash but tail isn't a code
      'QQQ' / 'NVDA'      → ('QQQ', 'QQQ')         bare US ticker — name == code
      '上海金'            → ('上海金', None)         no slash, not a ticker
    """
    raw = raw.strip()
    if "/" in raw:
        name, tail = raw.rsplit("/", 1)
        if _CODE_LIKE.match(tail.strip()):
            return name.strip(), tail.strip()
        return raw, None
    if _TICKER_LIKE.match(raw):
        return raw, raw
    return raw, None


_MARKET_TO_CCY = {"中国": "CNY", "香港": "HKD", "美国": "USD"}


def _original_price(cny_price: float | None, currency: str, fx: dict[str, float]) -> float | None:
    if cny_price is None:
        return None
    if currency == "CNY":
        return round(cny_price, 4)
    rate = fx.get(currency + "CNY")
    if not rate:
        return None
    return round(cny_price / rate, 4)


def parse_csv(csv_path: Path) -> tuple[dict[str, float], list[dict]]:
    with csv_path.open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))

    if len(rows) < 5:
        raise ValueError(f"CSV too short: {len(rows)} rows")

    # Rows 0-1: FX rates in column index 5
    hkd_cny = float(rows[0][5])
    usd_cny = float(rows[1][5])
    fx = {"HKDCNY": hkd_cny, "USDCNY": usd_cny}

    # Row 3 is the header — find it just to be safe
    header = rows[3]
    expected_first_cols = ["", "市场", "资产类型", "一级资产标签", "二级资产标签"]
    if header[: len(expected_first_cols)] != expected_first_cols:
        raise ValueError(f"Unexpected header: {header}")

    holdings: list[dict] = []
    for raw in rows[4:]:
        if not any(c.strip() for c in raw):
            continue
        market = raw[1].strip()
        if market in ("", "全市场"):
            continue
        asset_class = raw[2].strip()
        tag_l1 = raw[3].strip() or None
        tag_l2 = raw[4].strip() or None
        name, code = _split_name_code(raw[5])
        currency = _MARKET_TO_CCY.get(market, "CNY")
        cny_current = _to_float(raw[6])
        cny_cost = _to_float(raw[7])
        quantity = _to_float(raw[8])
        cost_value_cny = _to_float(raw[10])
        market_value_cny = _to_float(raw[11])
        unrealized_pnl_cny = _to_float(raw[12])
        return_pct = _to_float(raw[13])
        broker = raw[14].strip()

        if cost_value_cny is None or market_value_cny is None:
            # nothing to aggregate — skip rather than poison sums
            continue

        holdings.append({
            "market": market,
            "asset_class": asset_class,
            "tag_l1": tag_l1,
            "tag_l2": tag_l2,
            "name": name,
            "code": code,
            "currency": currency,
            "current_price": _original_price(cny_current, currency, fx),
            "cost_price": _original_price(cny_cost, currency, fx),
            "quantity": quantity,
            "cost_value_cny": cost_value_cny,
            "market_value_cny": market_value_cny,
            "unrealized_pnl_cny": unrealized_pnl_cny,
            "return_pct": return_pct,
            "broker": broker,
        })

    return fx, holdings


def seed(csv_path: Path) -> None:
    fx, holdings = parse_csv(csv_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    db.reset()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs(source, started_at, status, n_rows) "
            "VALUES (?, ?, 'ok', ?)",
            ("seed", now, len(holdings)),
        )
        run_id = cur.lastrowid

        for h in holdings:
            conn.execute(
                """
                INSERT INTO holdings(
                    market, asset_class, tag_l1, tag_l2, name, code, currency,
                    current_price, cost_price, quantity,
                    cost_value_cny, market_value_cny, unrealized_pnl_cny, return_pct,
                    broker, as_of, source_run_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    h["market"], h["asset_class"], h["tag_l1"], h["tag_l2"],
                    h["name"], h["code"], h["currency"],
                    h["current_price"], h["cost_price"], h["quantity"],
                    h["cost_value_cny"], h["market_value_cny"],
                    h["unrealized_pnl_cny"], h["return_pct"],
                    h["broker"], now, run_id,
                ),
            )

        for pair, rate in fx.items():
            conn.execute(
                "INSERT OR REPLACE INTO fx_rates(pair, rate, as_of) VALUES (?,?,?)",
                (pair, rate, now),
            )

        conn.execute(
            "UPDATE sync_runs SET finished_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), run_id),
        )

    print(f"seeded {len(holdings)} holdings; FX={fx}; db={db.db_path()}")


def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("csv", type=Path)
    args = p.parse_args()
    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1
    seed(args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
