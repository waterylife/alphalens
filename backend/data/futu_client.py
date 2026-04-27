"""Futu OpenD data client — snapshot, capital flow, kline.

Connects to OpenD running on 127.0.0.1:11111. Requires user to be logged in
via the Futu OpenD GUI (no SDK unlock needed for read-only market data).

All functions are best-effort: return empty dict/None on any error so the
surrounding pipeline keeps working.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

import pandas as pd

try:
    from futu import OpenQuoteContext, PeriodType, KLType
    _FUTU_OK = True
except ImportError:
    _FUTU_OK = False

from backend.data.cache import cache

_HOST = "127.0.0.1"
_PORT = 11111

TTL_INTRADAY = 60 * 5
TTL_DAILY = 60 * 60 * 4

_ctx_lock = threading.Lock()
_ctx: Any = None


def _get_ctx() -> Any:
    """Lazily create a single shared OpenQuoteContext."""
    global _ctx
    if not _FUTU_OK:
        return None
    with _ctx_lock:
        if _ctx is None:
            try:
                _ctx = OpenQuoteContext(host=_HOST, port=_PORT)
            except Exception:
                _ctx = None
        return _ctx


def _fcode(ticker: str) -> str:
    """Convert 5-digit HK code to Futu format 'HK.00700'."""
    return f"HK.{ticker.strip().lstrip('0').zfill(5)}"


def available() -> bool:
    """Check if Futu OpenD is reachable and logged-in."""
    ctx = _get_ctx()
    if ctx is None:
        return False
    try:
        ret, _ = ctx.get_global_state()
        return ret == 0
    except Exception:
        return False


# ─────────────────────────── Snapshot ───────────────────────────


def fetch_snapshot(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Bulk snapshot for a list of 5-digit HK tickers.

    Returns: {ticker: {name, pe_ttm, pb, turnover_rate, volume_ratio, turnover_hkd_mn}}
    pe_ttm/pb are nulled if negative (unprofitable — not meaningful).
    """
    if not tickers:
        return {}
    key = ",".join(sorted(tickers))

    def _fetch() -> dict[str, dict[str, Any]]:
        ctx = _get_ctx()
        if ctx is None:
            return {}
        codes = [_fcode(t) for t in tickers]
        try:
            ret, df = ctx.get_market_snapshot(codes)
        except Exception:
            return {}
        if ret != 0 or df is None or df.empty:
            return {}

        out: dict[str, dict[str, Any]] = {}
        for _, row in df.iterrows():
            fcode = str(row.get("code", ""))
            ticker = fcode.replace("HK.", "").zfill(5)

            def _num(k: str) -> float | None:
                v = row.get(k)
                try:
                    f = float(v)
                    return f if f == f else None
                except (TypeError, ValueError):
                    return None

            pe_ttm = _num("pe_ttm_ratio")
            pb = _num("pb_ratio")
            if pe_ttm is not None and pe_ttm <= 0:
                pe_ttm = None
            if pb is not None and pb <= 0:
                pb = None

            turnover = _num("turnover")
            last = _num("last_price")
            prev = _num("prev_close_price")
            chg_pct = round((last / prev - 1) * 100, 2) if (last and prev) else None

            out[ticker] = {
                "name": str(row.get("name", "")) or None,
                "last_price": last,
                "change_pct": chg_pct,
                "pe_ttm": round(pe_ttm, 2) if pe_ttm is not None else None,
                "pb": round(pb, 2) if pb is not None else None,
                "turnover_rate": _num("turnover_rate"),
                "volume_ratio": _num("volume_ratio"),
                "turnover_hkd_mn": round(turnover / 1_000_000, 2) if turnover else None,
            }
        return out

    try:
        return cache.fetch("futu_snapshot", key, TTL_INTRADAY, _fetch)
    except Exception:
        return {}


# ─────────────────────────── Capital flow ───────────────────────────


def fetch_capital_flow(ticker: str) -> dict[str, Any]:
    """Daily capital flow: today's net inflow + 5d sum (HKD mn).

    `in_flow` = 主力净流入（大单 + 超大单净额 - 中小单净额 approx）. Futu
    ships daily aggregates via period_type=DAY.
    """
    empty = {
        "ticker": ticker,
        "net_inflow_today_hkd_mn": None,
        "net_inflow_5d_hkd_mn": None,
    }

    def _fetch() -> dict[str, Any]:
        ctx = _get_ctx()
        if ctx is None:
            return empty
        try:
            ret, df = ctx.get_capital_flow(_fcode(ticker), period_type=PeriodType.DAY)
        except Exception:
            return empty
        if ret != 0 or df is None or df.empty:
            return empty

        df = df.copy()
        df["in_flow"] = pd.to_numeric(df["in_flow"], errors="coerce")
        today_row = df.iloc[-1]
        today_flow = float(today_row["in_flow"]) if pd.notna(today_row["in_flow"]) else None
        last5 = df.tail(5)["in_flow"].dropna()
        sum5 = float(last5.sum()) if not last5.empty else None
        return {
            "ticker": ticker,
            "net_inflow_today_hkd_mn": round(today_flow / 1_000_000, 1) if today_flow is not None else None,
            "net_inflow_5d_hkd_mn": round(sum5 / 1_000_000, 1) if sum5 is not None else None,
        }

    try:
        return cache.fetch("futu_capflow", ticker, TTL_INTRADAY, _fetch)
    except Exception:
        return empty


# ─────────────────────────── K-line (for ADTV) ───────────────────────────


def fetch_order_book_metrics(ticker: str) -> dict[str, float | None]:
    """Bid-ask spread % and 5-level depth ratio. Needs ORDER_BOOK subscription.

    Returns {bid_ask_spread_bps, depth_ratio_5}.
    - bid_ask_spread_bps: (ask1-bid1)/mid * 10000
    - depth_ratio_5: sum(bid vol top 5) / sum(ask vol top 5). >1 = more buy pressure.
    Null during market close or on any error.
    """
    empty = {"bid_ask_spread_bps": None, "depth_ratio_5": None}
    ctx = _get_ctx()
    if ctx is None:
        return empty
    try:
        from futu import SubType
        code = _fcode(ticker)
        ctx.subscribe([code], [SubType.ORDER_BOOK])
        ret, d = ctx.get_order_book(code, num=5)
    except Exception:
        return empty
    if ret != 0 or not isinstance(d, dict):
        return empty

    bids = d.get("Bid") or []
    asks = d.get("Ask") or []
    if not bids or not asks:
        return empty
    try:
        bid1 = float(bids[0][0])
        ask1 = float(asks[0][0])
        if bid1 <= 0 or ask1 <= 0:
            return empty
        mid = (bid1 + ask1) / 2
        spread_bps = round((ask1 - bid1) / mid * 10000, 1)
        bid_vol = sum(float(b[1]) for b in bids[:5])
        ask_vol = sum(float(a[1]) for a in asks[:5])
        if ask_vol <= 0:
            return {"bid_ask_spread_bps": spread_bps, "depth_ratio_5": None}
        depth_ratio = round(bid_vol / ask_vol, 2)
        return {"bid_ask_spread_bps": spread_bps, "depth_ratio_5": depth_ratio}
    except Exception:
        return empty


def fetch_adtv_20d(ticker: str) -> float | None:
    """20-day average daily turnover in HKD millions, via Futu kline turnover field."""
    def _fetch() -> float | None:
        ctx = _get_ctx()
        if ctx is None:
            return None
        try:
            end = dt.date.today().strftime("%Y-%m-%d")
            start = (dt.date.today() - dt.timedelta(days=50)).strftime("%Y-%m-%d")
            ret, df, _ = ctx.request_history_kline(
                _fcode(ticker), start=start, end=end, ktype=KLType.K_DAY,
                fields=["turnover", "time_key"], max_count=50,
            )
        except Exception:
            return None
        if ret != 0 or df is None or df.empty:
            return None
        df = df.copy()
        df["turnover"] = pd.to_numeric(df["turnover"], errors="coerce")
        tail = df.tail(20)["turnover"].dropna()
        if tail.empty:
            return None
        return round(float(tail.mean()) / 1_000_000, 2)

    try:
        return cache.fetch("futu_adtv20", ticker, TTL_DAILY, _fetch)
    except Exception:
        return None
