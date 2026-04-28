"""Spot price lookup by (market, code) across A-share / HK / US / open-end funds.

We deliberately use the Sina-backed akshare endpoints over the EastMoney
(_em) ones — the EM endpoints proxy through ``*.push2.eastmoney.com``
which is regularly blocked by Clash / Surge style proxies. Sina works
direct.

All HTTP calls run inside ``_no_proxy()`` because akshare routes through
the system proxy, which the user is running and which blocks several
upstream finance hosts.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable

import akshare as ak


_PROXY_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


# Default cache window: 30 minutes. Tuned so a user mashing the refresh
# button a few times in a row hits cache, but a daytime trader who
# refreshes once an hour still sees fresh quotes. Override via env.
_TTL_SECONDS = int(os.environ.get("PORTFOLIO_QUOTES_TTL", "1800"))


@contextmanager
def _no_proxy():
    """Temporarily strip proxy env vars so akshare hits upstream directly."""
    saved = {k: os.environ.pop(k, None) for k in _PROXY_VARS}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ---- TTL cache --------------------------------------------------------

_caches: list[dict] = []   # registry so reset_cache() clears them all


def _ttl_cache(ttl: int = _TTL_SECONDS, maxsize: int = 256) -> Callable:
    """Per-args cache with a wall-clock TTL.

    Unlike functools.lru_cache, entries are considered fresh only within
    ``ttl`` seconds — so a stale value (e.g. a price from yesterday) won't
    silently linger across the 30-minute window. The cache can also be
    bypassed by passing ``_force=True`` to the wrapped call (see below)."""

    def deco(fn: Callable) -> Callable:
        cache: dict = {}
        _caches.append(cache)

        @wraps(fn)
        def wrapper(*args, _force: bool = False):
            now = time.time()
            if not _force and args in cache:
                value, stored_at = cache[args]
                if now - stored_at < ttl:
                    return value
            value = fn(*args)
            cache[args] = (value, now)
            if len(cache) > maxsize:
                # FIFO eviction — fine for this scale (≤a few hundred symbols)
                cache.pop(next(iter(cache)))
            return value

        return wrapper

    return deco


def reset_cache() -> None:
    """Drop all in-memory quote caches. Used when the API caller passes
    `?force=true` to bypass the TTL window."""
    for c in _caches:
        c.clear()


# ---- batch fetchers (TTL-cached) -------------------------------------

@_ttl_cache()
def _a_stock_spot() -> dict[str, float]:
    """A-share stocks (no ETFs). Codes prefixed with sh/sz, e.g. 'sh600519'."""
    with _no_proxy():
        df = ak.stock_zh_a_spot()
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        code = str(r["代码"]).strip()
        try:
            out[code] = float(r["最新价"])
        except (TypeError, ValueError):
            pass
    return out


@_ttl_cache()
def _a_etf_spot() -> dict[str, float]:
    """A-share ETFs + LOFs (513***, 515***, 159***, 161***). Sina lumps both
    under category=ETF基金. Codes are also sh/sz-prefixed in this dataset."""
    with _no_proxy():
        df = ak.fund_etf_category_sina(symbol="ETF基金")
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        code = str(r["代码"]).strip()
        try:
            out[code] = float(r["最新价"])
        except (TypeError, ValueError):
            pass
    return out


@_ttl_cache()
def _hk_spot() -> dict[str, float]:
    """HK stocks. Codes are 5-digit zero-padded strings ('00700')."""
    with _no_proxy():
        df = ak.stock_hk_spot()
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        code = str(r["代码"]).strip().zfill(5)
        try:
            out[code] = float(r["最新价"])
        except (TypeError, ValueError):
            pass
    return out


@_ttl_cache()
def _open_fund_spot() -> dict[str, float]:
    """Open-end funds keyed by 6-digit code (110018, 270002, ...).

    Prefer the most recent published unit NAV; fall back to the est. value
    if NAV column is empty (e.g. fund hasn't published yet today).
    """
    with _no_proxy():
        df = ak.fund_value_estimation_em()

    nav_col = next((c for c in df.columns if c.endswith("公布数据-单位净值")), None)
    est_col = next((c for c in df.columns if c.endswith("估算数据-估算值")), None)

    out: dict[str, float] = {}
    for _, r in df.iterrows():
        code = str(r["基金代码"]).strip().zfill(6)
        for col in (nav_col, est_col):
            if not col:
                continue
            try:
                v = float(r[col])
                if v > 0:
                    out[code] = v
                    break
            except (TypeError, ValueError):
                continue
    return out


@_ttl_cache(ttl=24 * 60 * 60)
def _open_fund_profiles() -> dict[str, dict[str, str]]:
    """Open-end fund metadata keyed by 6-digit code.

    Used to classify imported fund holdings into the portfolio UI's broader
    buckets (股票 / 债券 / 现金). Cached for a day because fund names/types are
    slow-moving reference data, unlike NAVs.
    """
    with _no_proxy():
        df = ak.fund_name_em()

    out: dict[str, dict[str, str]] = {}
    for _, r in df.iterrows():
        code = str(r["基金代码"]).strip().zfill(6)
        out[code] = {
            "name": str(r.get("基金简称") or "").strip(),
            "type": str(r.get("基金类型") or "").strip(),
        }
    return out


@_ttl_cache()
def _us_one(symbol: str) -> float | None:
    """US tickers — akshare doesn't have a reliable spot endpoint that works
    behind the user's proxy, so we pull the single-symbol daily series and
    return the most recent close. Slow per call but US holdings are usually
    a handful of tickers."""
    try:
        with _no_proxy():
            df = ak.stock_us_daily(symbol=symbol.upper(), adjust="")
        if df is None or df.empty:
            return None
        return float(df.iloc[-1]["close"])
    except Exception:
        return None


@_ttl_cache()
def _hk_one_via_hist(symbol: str) -> float | None:
    """Per-symbol fallback for HK tickers not in stock_hk_spot — covers HK
    ETFs like 03032 which the spot endpoint omits. Uses the Sina daily
    endpoint because the EastMoney equivalent (``stock_hk_hist``) routes
    through ``*.push2.eastmoney.com`` which is blocked by Clash."""
    try:
        with _no_proxy():
            df = ak.stock_hk_daily(symbol=symbol, adjust="")
        if df is None or df.empty:
            return None
        return float(df.iloc[-1]["close"])
    except Exception:
        return None


@_ttl_cache()
def _open_fund_one(symbol: str) -> float | None:
    """Per-symbol fallback for open-end funds not in fund_value_estimation_em
    — covers QDII funds like 002400, 100050. Returns latest 单位净值."""
    try:
        with _no_proxy():
            df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
        if df is None or df.empty:
            return None
        return float(df.iloc[-1]["单位净值"])
    except Exception:
        return None


# ---- public lookup ----------------------------------------------------



def fetch_quote(market: str, code: str, asset_class: str | None = None) -> float | None:
    """Return the latest native-currency price for (market, code), or None.

    ``asset_class`` (e.g. '股票', '债券', '现金') disambiguates 6-digit codes
    that exist in BOTH the A-share stock universe and the open-end fund
    universe (e.g. 002400 = sz股票红宝丽 ≠ QDII 南方亚洲美元收益债券). When
    asset_class is '债券' / '基金' we look up funds first, otherwise we
    look up ETFs/stocks first.

    Loose matching: leading zeros and sh/sz prefixes are tried so '9988',
    '09988', '600519' and '513010' all resolve."""
    if not code:
        return None
    code = code.strip().upper()

    # Disambiguate by code shape first — market labels are user-supplied
    # and frequently reflect the *underlying* exposure rather than the
    # listing venue. E.g. user labels QDII fund 002400 as 美国 because it
    # holds US bonds, but the actual price source is a Chinese fund NAV.

    # Pure-letter ticker → US (NVDA, QQQ, MSFT)
    if code.isalpha():
        return _us_one(code)

    # 4–5-digit numeric → HK ticker
    if code.isdigit() and len(code) <= 5:
        padded = code.zfill(5)
        d = _hk_spot()
        v = d.get(padded) or d.get(code)
        if v is not None:
            return v
        # HK ETFs (e.g. 03032) aren't in stock_hk_spot — fall back to
        # per-symbol historical close.
        return _hk_one_via_hist(padded)

    # 6-digit: A-share ETF/stock or open-end fund. Prefer fund-first lookup
    # when the holding is classified as bond/fund to avoid colliding with
    # SZ stock codes like 002400.
    if code.isdigit() and len(code) == 6:
        fund_first = asset_class in ("债券", "基金")

        def _try_a_tables() -> float | None:
            for table in (_a_etf_spot, _a_stock_spot):
                d = table()
                for pfx in ("sh", "sz"):
                    v = d.get(pfx + code)
                    if v is not None:
                        return v
            return None

        def _try_funds() -> float | None:
            v = _open_fund_spot().get(code)
            if v is not None:
                return v
            # Per-symbol fallback for QDII / niche funds
            return _open_fund_one(code)

        if fund_first:
            v = _try_funds()
            if v is not None:
                return v
            return _try_a_tables()
        else:
            v = _try_a_tables()
            if v is not None:
                return v
            return _try_funds()

    return None


def fetch_fund_profile(code: str) -> dict[str, str] | None:
    """Return basic open-end fund metadata, or None if the code is unknown."""
    if not code:
        return None
    code = code.strip().zfill(6)
    try:
        return _open_fund_profiles().get(code)
    except Exception:
        return None
