"""Portfolio sync orchestration.

`sync_futu` fetches the user's Futu positions, refreshes FX rates, then
upserts each position into the local SQLite store. Existing rows for matched
securities have prices/qty/PnL refreshed but their user-curated tags
(tag_l1, tag_l2, asset_class) are preserved so manual classification doesn't
get clobbered on every sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.portfolio import db, fx
from backend.portfolio.sources import futu as futu_src
from backend.portfolio.sources import quotes as quotes_src
from backend.portfolio.sources.futu import FutuPosition, codes_match


_BROKER = "富途证券"


def is_hk_connect(broker: str | None, market: str | None) -> bool:
    """True for 港股通 holdings — bought from 东方财富 (mainland broker)
    on the HK Connect channel. These are settled in CNY, so cost basis
    and price display stay in CNY rather than HKD even though the
    underlying trades on HKEx."""
    return broker == "东方财富" and market == "香港"


# ---- code normalization shared with screenshot import -----------------

def _normalize_code(code: str | None) -> str | None:
    """Lowercase, strip leading zeros — used for fuzzy matching against
    existing rows so that '003448' and '3448' both find the same fund."""
    if not code:
        return None
    return code.lstrip("0").upper() or code.upper()


def sync_futu() -> dict:
    """Run a Futu sync. Returns the SyncRun record."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs(source, started_at, status) VALUES (?,?,?)",
            ("futu", started, "running"),
        )
        run_id = cur.lastrowid

    try:
        rates, _ = fx.refresh_and_persist()
        positions = futu_src.fetch()
        n_inserted, n_updated = _upsert_positions(positions, rates, run_id)

        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, n_rows=? WHERE id=?",
                (finished, "ok", n_inserted + n_updated, run_id),
            )
        return {
            "id": run_id,
            "status": "ok",
            "n_inserted": n_inserted,
            "n_updated": n_updated,
            "fx_rates": rates,
        }
    except Exception as e:
        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, error_msg=? WHERE id=?",
                (finished, "error", str(e), run_id),
            )
        raise


def _to_cny(value: float | None, currency: str, rates: dict[str, float]) -> float | None:
    if value is None:
        return None
    if currency == "CNY":
        return round(value, 2)
    rate = rates.get(currency + "CNY")
    if not rate:
        return None
    return round(value * rate, 2)


def _find_existing(conn, p: FutuPosition) -> dict | None:
    """Look up an existing 富途证券 row that matches this position.

    Tickers match loosely (leading zeros stripped). Synthetic rows (code=None)
    match by exact name within the same broker."""
    if p.code:
        rows = conn.execute(
            "SELECT * FROM holdings WHERE broker=? AND market=? AND code IS NOT NULL",
            (_BROKER, p.market),
        ).fetchall()
        for r in rows:
            if codes_match(r["code"], p.code):
                return dict(r)
        return None

    row = conn.execute(
        "SELECT * FROM holdings WHERE broker=? AND market=? AND code IS NULL AND name=?",
        (_BROKER, p.market, p.name),
    ).fetchone()
    return dict(row) if row else None


def _upsert_positions(
    positions: list[FutuPosition],
    rates: dict[str, float],
    run_id: int,
) -> tuple[int, int]:
    n_inserted = n_updated = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with db.connect() as conn:
        for p in positions:
            mv_cny = _to_cny(p.market_value_native, p.currency, rates) or 0.0
            cv_cny = _to_cny(p.cost_value_native, p.currency, rates) or mv_cny
            pnl_cny = _to_cny(p.unrealized_pnl_native, p.currency, rates)

            existing = _find_existing(conn, p)
            if existing:
                # Preserve user-curated fields: tag_l1, tag_l2, asset_class, currency.
                # (Currency is preserved because for synthetic rows like 美国中长期国债,
                # Futu reports value in account base currency rather than the asset's
                # native currency — overwriting would silently flip the display ccy.)
                conn.execute(
                    """
                    UPDATE holdings SET
                        current_price=?, cost_price=?, quantity=?,
                        cost_value_cny=?, market_value_cny=?, unrealized_pnl_cny=?,
                        return_pct=?, as_of=?, source_run_id=?
                    WHERE id=?
                    """,
                    (
                        p.current_price, p.cost_price, p.quantity,
                        cv_cny, mv_cny, pnl_cny, p.return_pct, now, run_id,
                        existing["id"],
                    ),
                )
                n_updated += 1
            else:
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
                        p.market, p.asset_class_hint, None, None,
                        p.name, p.code, p.currency,
                        p.current_price, p.cost_price, p.quantity,
                        cv_cny, mv_cny, pnl_cny, p.return_pct,
                        _BROKER, now, run_id,
                    ),
                )
                n_inserted += 1

    return n_inserted, n_updated


# ---- screenshot import ------------------------------------------------

def import_rows(broker: str, rows: list[dict]) -> dict:
    """Upsert reviewed rows from screenshot/manual import into holdings.

    Match key: (broker, market, normalized_code) when code is non-null;
    otherwise (broker, market, name). User-curated fields (tag_l1, tag_l2,
    asset_class, currency) are taken from the incoming rows since the user
    just edited them in the confirm modal — full overwrite is fine here."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs(source, started_at, status) VALUES (?,?,?)",
            (f"screenshot:{broker}", started, "running"),
        )
        run_id = cur.lastrowid

    n_inserted = n_updated = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with db.connect() as conn:
            for r in rows:
                existing = _find_existing_for_import(conn, broker, r)
                if existing:
                    conn.execute(
                        """
                        UPDATE holdings SET
                            market=?, asset_class=?, tag_l1=?, tag_l2=?,
                            name=?, code=?, currency=?,
                            current_price=?, cost_price=?, quantity=?,
                            cost_value_cny=?, market_value_cny=?,
                            unrealized_pnl_cny=?, return_pct=?,
                            as_of=?, source_run_id=?
                        WHERE id=?
                        """,
                        (
                            r["market"], r["asset_class"], r.get("tag_l1"), r.get("tag_l2"),
                            r["name"], r.get("code"), r.get("currency", "CNY"),
                            r.get("current_price"), r.get("cost_price"), r.get("quantity"),
                            r.get("cost_value_cny") or r["market_value_cny"],
                            r["market_value_cny"],
                            r.get("unrealized_pnl_cny"), r.get("return_pct"),
                            now, run_id, existing["id"],
                        ),
                    )
                    n_updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO holdings(
                            market, asset_class, tag_l1, tag_l2,
                            name, code, currency,
                            current_price, cost_price, quantity,
                            cost_value_cny, market_value_cny,
                            unrealized_pnl_cny, return_pct,
                            broker, as_of, source_run_id
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            r["market"], r["asset_class"], r.get("tag_l1"), r.get("tag_l2"),
                            r["name"], r.get("code"), r.get("currency", "CNY"),
                            r.get("current_price"), r.get("cost_price"), r.get("quantity"),
                            r.get("cost_value_cny") or r["market_value_cny"],
                            r["market_value_cny"],
                            r.get("unrealized_pnl_cny"), r.get("return_pct"),
                            broker, now, run_id,
                        ),
                    )
                    n_inserted += 1

        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, n_rows=? WHERE id=?",
                (finished, "ok", n_inserted + n_updated, run_id),
            )
        return {"id": run_id, "status": "ok", "n_inserted": n_inserted, "n_updated": n_updated}
    except Exception as e:
        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, error_msg=? WHERE id=?",
                (finished, "error", str(e), run_id),
            )
        raise


# ---- price refresh ----------------------------------------------------

def refresh_prices(force: bool = False) -> dict:
    """Refresh `current_price` for every holding with a code, then recompute
    market_value_cny / unrealized_pnl_cny / return_pct using the latest FX.

    Quote responses are cached in-process (TTL controlled by
    PORTFOLIO_QUOTES_TTL, default 30 min) so mashing the refresh button
    won't re-hit upstream APIs. Pass ``force=True`` to bypass that window.

    Skips rows where:
      * code is NULL (cash, broker-side aggregates like 港元/美元货币基金)
      * the quote source returns no match (e.g. delisted, unknown market)
    """
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs(source, started_at, status) VALUES (?,?,?)",
            ("refresh_prices", started, "running"),
        )
        run_id = cur.lastrowid

    try:
        rates, _ = fx.refresh_and_persist()
        if force:
            quotes_src.reset_cache()

        n_updated = n_skipped = n_no_quote = 0
        skipped_examples: list[str] = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with db.connect() as conn:
            rows = conn.execute(
                "SELECT id, market, name, code, broker, currency, quantity, "
                "       cost_price, asset_class "
                "FROM holdings WHERE code IS NOT NULL"
            ).fetchall()

            for r in rows:
                # 港股通 (东方财富 + 香港): the holding's authoritative
                # cost & price are the CNY values the user imported from
                # the eastmoney screenshot. Don't fetch HKD live and
                # back-convert — the FX drift between purchase and now
                # silently distorts return_pct. Skip; user re-uploads a
                # screenshot when they want fresh values.
                if is_hk_connect(r["broker"], r["market"]):
                    n_skipped += 1
                    continue

                price = quotes_src.fetch_quote(
                    r["market"], r["code"], asset_class=r["asset_class"]
                )
                if price is None:
                    n_no_quote += 1
                    if len(skipped_examples) < 5:
                        skipped_examples.append(f"{r['name']}({r['code']})")
                    continue
                if r["quantity"] is None:
                    n_skipped += 1
                    continue

                qty = float(r["quantity"])
                cost = r["cost_price"]

                rate = 1.0 if r["currency"] == "CNY" else (
                    rates.get(r["currency"] + "CNY") or 0.0
                )
                if rate == 0.0:
                    n_skipped += 1
                    continue
                new_currency = r["currency"]

                mv_cny = round(price * qty * rate, 2)
                pnl_cny = (
                    round((price - cost) * qty * rate, 2)
                    if cost is not None else None
                )
                ret_pct = (
                    round((price / cost - 1) * 100, 2)
                    if cost else None
                )

                conn.execute(
                    "UPDATE holdings SET current_price=?, currency=?, market_value_cny=?, "
                    "unrealized_pnl_cny=?, return_pct=?, as_of=?, source_run_id=? "
                    "WHERE id=?",
                    (price, new_currency, mv_cny, pnl_cny, ret_pct, now, run_id, r["id"]),
                )
                n_updated += 1

        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, n_rows=? WHERE id=?",
                (finished, "ok", n_updated, run_id),
            )
        return {
            "id": run_id,
            "status": "ok",
            "n_updated": n_updated,
            "n_no_quote": n_no_quote,
            "n_skipped": n_skipped,
            "skipped_examples": skipped_examples,
            "fx_rates": rates,
        }
    except Exception as e:
        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, error_msg=? WHERE id=?",
                (finished, "error", str(e), run_id),
            )
        raise


def _find_existing_for_import(conn, broker: str, r: dict) -> dict | None:
    code = r.get("code")
    market = r["market"]
    if code:
        norm = _normalize_code(code)
        rows = conn.execute(
            "SELECT * FROM holdings WHERE broker=? AND market=? AND code IS NOT NULL",
            (broker, market),
        ).fetchall()
        for row in rows:
            if _normalize_code(row["code"]) == norm:
                return dict(row)
        return None

    row = conn.execute(
        "SELECT * FROM holdings WHERE broker=? AND market=? AND code IS NULL AND name=?",
        (broker, market, r["name"]),
    ).fetchone()
    return dict(row) if row else None
