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


def import_tiantian_browser_rows(rows: list[dict]) -> dict:
    """Upsert minimal read-only rows collected from Tiantian fund pages.

    The browser collector is intentionally limited to code/name/quantity/cost
    price. Current NAV is fetched locally via the quote layer, then all derived
    CNY fields are computed here. Existing user-curated market/tags are
    preserved when a matching 天天基金 code already exists.
    """
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs(source, started_at, status) VALUES (?,?,?)",
            ("browser:tiantian", started, "running"),
        )
        run_id = cur.lastrowid

    n_inserted = n_updated = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with db.connect() as conn:
            for r in rows:
                code = str(r["code"]).strip().zfill(6)
                name = str(r["name"]).strip()
                quantity = float(r["quantity"])
                cost_price = float(r["cost_price"])
                if quantity <= 0 or cost_price <= 0:
                    continue

                profile = classify_fund_holding(name, code)
                name = profile["name"] or name
                existing = _find_existing_by_broker_code(conn, "天天基金", code)
                current_price = quotes_src.fetch_quote(
                    profile["market"], code, asset_class=profile["asset_class"]
                )
                if current_price is None:
                    current_price = cost_price

                cost_value = round(quantity * cost_price, 2)
                market_value = round(quantity * current_price, 2)
                pnl = round(market_value - cost_value, 2)
                ret_pct = round((current_price / cost_price - 1) * 100, 2)

                if existing:
                    conn.execute(
                        """
                        UPDATE holdings SET
                            market=?, asset_class=?, tag_l1=?, tag_l2=?,
                            name=?, current_price=?, cost_price=?, quantity=?,
                            cost_value_cny=?, market_value_cny=?,
                            unrealized_pnl_cny=?, return_pct=?,
                            as_of=?, source_run_id=?
                        WHERE id=?
                        """,
                        (
                            profile["market"], profile["asset_class"],
                            profile["tag_l1"], profile["tag_l2"],
                            name, current_price, cost_price, quantity,
                            cost_value, market_value, pnl, ret_pct,
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
                            profile["market"], profile["asset_class"],
                            profile["tag_l1"], profile["tag_l2"],
                            name, code, "CNY",
                            current_price, cost_price, quantity,
                            cost_value, market_value, pnl, ret_pct,
                            "天天基金", now, run_id,
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


def classify_fund_holding(name: str, code: str | None = None) -> dict[str, str | None]:
    """Classify a fund into the UI's top-level portfolio buckets.

    The holdings UI only has first-class sections for 股票 / 债券 / 现金.
    Fund imports therefore need to be mapped by fund metadata rather than
    stored as a separate generic "基金" asset class.
    """
    code = (code or "").strip().zfill(6) if code else ""
    meta = quotes_src.fetch_fund_profile(code) if code else None
    fund_name = (meta or {}).get("name") or name.strip()
    fund_type = (meta or {}).get("type") or ""
    text = f"{fund_name} {fund_type}"

    asset_class = "股票"
    tag_l1: str | None = "价值成长"
    tag_l2: str | None = None
    market = "中国"

    if any(k in text for k in ("货币", "现金", "同业存单")):
        asset_class, tag_l1, tag_l2 = "现金", "现金", "现金"
    elif any(k in text for k in ("债", "短债", "中短债", "纯债", "可转债")):
        asset_class = "债券"
        is_mixed = any(k in text for k in ("混合债", "混合一级", "混合二级", "可转债", "增强债"))
        tag_l1 = "混合债券" if is_mixed else "纯债"
        tag_l2 = "混合债券" if is_mixed else "纯债-中国"
        if "QDII" in text.upper() and any(k in text for k in ("美元", "美国", "全球", "亚洲")):
            tag_l2 = "混合债券" if is_mixed else "纯债-美国"
    elif any(k in text for k in ("黄金", "贵金属")):
        asset_class, tag_l1, tag_l2 = "黄金", "黄金/虚拟币", "黄金/虚拟币"
    elif any(k in text for k in ("红利", "低波")):
        asset_class, tag_l1 = "股票", "红利低波"
        if any(k in text for k in ("港", "恒生", "香港")):
            tag_l2 = "港股红利"
        elif any(k in text for k in ("美", "标普", "纳斯达克")):
            tag_l2 = "美股红利"
        else:
            tag_l2 = "沪深红利"
    elif any(k in text for k in ("科技", "互联网", "纳斯达克", "恒生科技")):
        asset_class, tag_l1 = "股票", "价值成长"
        if any(k in text for k in ("港", "恒生")):
            tag_l2 = "港股科技"
        elif any(k in text for k in ("美", "纳斯达克", "标普", "全球")):
            tag_l2 = "美股科技"

    return {
        "name": fund_name,
        "market": market,
        "asset_class": asset_class,
        "tag_l1": tag_l1,
        "tag_l2": tag_l2,
    }


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


def _find_existing_by_broker_code(conn, broker: str, code: str) -> dict | None:
    norm = _normalize_code(code)
    rows = conn.execute(
        "SELECT * FROM holdings WHERE broker=? AND code IS NOT NULL",
        (broker,),
    ).fetchall()
    for row in rows:
        if _normalize_code(row["code"]) == norm:
            return dict(row)
    return None
