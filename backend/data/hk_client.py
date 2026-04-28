"""HK stock data access layer using akshare (Sina sources).

Sina is preferred over Eastmoney because the Eastmoney HK endpoints go
through push2.eastmoney.com which is often blocked by local proxies. Sina
endpoints are slower but reach reliably.

Trade-off: Sina's HK snapshot does not include PE/PB — those remain null.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
import akshare as ak

try:
    import yfinance as yf
except ImportError:
    yf = None

from backend.data.cache import cache
from backend.data import futu_client

TTL_INTRADAY = 60 * 10
TTL_DAILY = 60 * 60 * 4
TTL_STATIC = 60 * 60 * 24


def normalize_ticker(ticker: str) -> str:
    """Normalize HK ticker to 5-digit zero-padded string."""
    return ticker.strip().lstrip("0").zfill(5)


# ─────────────────────────── Spot / snapshot ───────────────────────────


def hk_stocks_all_snapshot() -> pd.DataFrame:
    """All HK stocks real-time snapshot from Sina (cached 10 min).

    Columns: 日期时间, 代码, 中文名称, 英文名称, 交易类型, 最新价, 涨跌额, 涨跌幅,
             昨收, 今开, 最高, 最低, 成交量, 成交额, 买一, 卖一.
    Note: no PE/PB columns from Sina.
    """
    def _fetch() -> pd.DataFrame:
        df = ak.stock_hk_spot()
        df = df.copy()
        if "代码" in df.columns:
            df["代码"] = df["代码"].astype(str).str.zfill(5)
        return df

    return cache.fetch("hk_spot_sina", "all", TTL_INTRADAY, _fetch)


def fetch_stock_snapshots_yf(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """HK stock snapshot via yfinance, keyed by 5-digit HK code.

    This is intentionally ticker-scoped. The Sina all-market endpoint can be
    slow on a cold cache because it crawls many pages, which makes the UI look
    empty while the request is still in flight.
    """
    if not tickers or yf is None:
        return {}
    normalized = [normalize_ticker(t) for t in tickers]
    key = ",".join(sorted(normalized))

    def _yf_symbol(ticker: str) -> str:
        return f"{ticker.lstrip('0').zfill(4)}.HK"

    def _fetch() -> dict[str, dict[str, Any]]:
        symbols = [_yf_symbol(t) for t in normalized]
        out: dict[str, dict[str, Any]] = {}
        hist = None
        try:
            hist = yf.download(
                symbols,
                period="5d",
                interval="1d",
                group_by="ticker",
                progress=False,
                auto_adjust=False,
                threads=True,
            )
        except Exception:
            hist = None

        for ticker, symbol in zip(normalized, symbols):
            name = price = change_pct = volume_hkd_mn = None
            try:
                if hist is not None:
                    df = hist if len(symbols) == 1 else hist.get(symbol)
                    if df is not None:
                        df = df.dropna(subset=["Close"])
                    if df is not None and len(df) >= 2:
                        last = float(df["Close"].iloc[-1])
                        prev = float(df["Close"].iloc[-2])
                        vol = float(df["Volume"].iloc[-1]) if "Volume" in df else 0
                        price = round(last, 3)
                        change_pct = round((last / prev - 1) * 100, 2) if prev else None
                        volume_hkd_mn = round(vol * last / 1_000_000, 2) if vol else None
            except Exception:
                pass
            try:
                info = yf.Ticker(symbol).info or {}
                name = info.get("shortName") or info.get("longName")
                if price is None:
                    price = _clean_num(info.get("currentPrice") or info.get("regularMarketPrice"))
                if volume_hkd_mn is None:
                    volume = _clean_num(info.get("volume") or info.get("regularMarketVolume"))
                    if volume and price:
                        volume_hkd_mn = round(volume * price / 1_000_000, 2)
            except Exception:
                pass
            out[ticker] = {
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume_hkd_mn": volume_hkd_mn,
            }
        return out

    try:
        return cache.fetch("hk_snapshot_yf", key, TTL_INTRADAY, _fetch)
    except Exception:
        return {}


# ─────────────────────────── Price history ───────────────────────────


def hk_stock_price_hist(ticker: str, years: int = 2) -> pd.DataFrame:
    """Daily forward-adjusted price history for a single HK stock (Sina).

    ticker: 5-digit zero-padded string, e.g. '00700'.
    Returns columns: date (ISO str), open, high, low, close, volume.
    """
    key = f"{ticker}:{years}"

    def _fetch() -> pd.DataFrame:
        df = ak.stock_hk_daily(symbol=ticker, adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].sort_values("date").reset_index(drop=True)
        cutoff = (dt.date.today() - dt.timedelta(days=365 * years)).strftime("%Y-%m-%d")
        return df[df["date"] >= cutoff].reset_index(drop=True)

    return cache.fetch("hk_stock_hist_sina", key, TTL_DAILY, _fetch)


def hstech_index_hist(years: int = 2) -> pd.DataFrame:
    """HSTECH index daily price history via Sina.

    Returns columns: date (ISO str), open, high, low, close, volume.
    """
    key = f"hstech:{years}"

    def _fetch() -> pd.DataFrame:
        df = ak.stock_hk_index_daily_sina(symbol="HSTECH")
        if df is None or df.empty:
            raise ValueError("HSTECH data empty from sina")
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].sort_values("date").reset_index(drop=True)
        cutoff = (dt.date.today() - dt.timedelta(days=365 * years)).strftime("%Y-%m-%d")
        return df[df["date"] >= cutoff].reset_index(drop=True)

    return cache.fetch("hstech_hist_sina", key, TTL_DAILY, _fetch)


# ─────────────────────────── Computed returns ───────────────────────────


def _pct_change(current: float, past: float | None) -> float | None:
    if past is None or past == 0:
        return None
    return round((current / past - 1) * 100, 2)


def compute_stock_returns(ticker: str) -> dict[str, Any]:
    """Compute 1M/3M/6M/12M price returns for a stock from cached history."""
    try:
        hist = hk_stock_price_hist(ticker, years=2)
    except Exception:
        hist = pd.DataFrame()

    empty = {"ticker": ticker, "ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12m": None}
    if hist.empty or "close" not in hist.columns:
        return empty

    today = dt.date.today()
    latest_price = float(hist.iloc[-1]["close"])

    def price_n_days_ago(n: int) -> float | None:
        target = (today - dt.timedelta(days=n)).strftime("%Y-%m-%d")
        mask = hist["date"] <= target
        if not mask.any():
            return None
        return float(hist[mask].iloc[-1]["close"])

    return {
        "ticker": ticker,
        "ret_1m":  _pct_change(latest_price, price_n_days_ago(30)),
        "ret_3m":  _pct_change(latest_price, price_n_days_ago(91)),
        "ret_6m":  _pct_change(latest_price, price_n_days_ago(182)),
        "ret_12m": _pct_change(latest_price, price_n_days_ago(365)),
    }


# ─────────────────────────── Technicals ───────────────────────────


def _rsi14(close: pd.Series) -> float | None:
    if len(close) < 15:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    if avg_loss is None or avg_loss == 0 or avg_loss != avg_loss:
        return 100.0 if avg_gain and avg_gain > 0 else None
    rs = float(avg_gain) / float(avg_loss)
    return round(100 - 100 / (1 + rs), 1)


def compute_stock_technicals(ticker: str) -> dict[str, Any]:
    """RSI14, dist from MA200 %, 20d ADTV (HKD mn) — from cached price history."""
    empty = {"ticker": ticker, "rsi14": None, "dist_ma200_pct": None, "adtv_20d_hkd_mn": None}
    try:
        hist = hk_stock_price_hist(ticker, years=2)
    except Exception:
        return empty
    if hist.empty or "close" not in hist.columns:
        return empty

    close = hist["close"].astype(float).reset_index(drop=True)
    latest = float(close.iloc[-1])

    rsi = _rsi14(close)

    dist_ma200 = None
    if len(close) >= 200:
        ma200 = float(close.tail(200).mean())
        if ma200 > 0:
            dist_ma200 = round((latest / ma200 - 1) * 100, 1)

    # Prefer Futu's true turnover field (accurate for HK); fallback to volume*close
    adtv = futu_client.fetch_adtv_20d(ticker)
    if adtv is None and "volume" in hist.columns and len(hist) >= 20:
        tail = hist.tail(20).copy()
        turnover = float((tail["volume"].astype(float) * tail["close"].astype(float)).mean())
        if turnover and turnover == turnover:
            adtv = round(turnover / 1_000_000, 2)

    # 52-week position: where is current price in the [52w_low, 52w_high] range (0-100)
    pos_52w = None
    if len(close) >= 60:
        win = close.tail(252) if len(close) >= 252 else close
        hi, lo = float(win.max()), float(win.min())
        if hi > lo:
            pos_52w = round((latest - lo) / (hi - lo) * 100, 1)

    return {
        "ticker": ticker, "rsi14": rsi, "dist_ma200_pct": dist_ma200,
        "adtv_20d_hkd_mn": adtv, "pos_52w_pct": pos_52w,
    }


# ─────────────────────────── Fundamentals via yfinance ───────────────────────────


def _clean_num(v: Any) -> float | None:
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    except (TypeError, ValueError):
        return None


def fetch_stock_fundamentals(ticker: str) -> dict[str, Any]:
    """Fetch fundamentals from yfinance (cached 4h). ticker is 5-digit HK code."""
    empty = {
        "ticker": ticker, "name": None, "pe_ttm": None,
        "pb": None, "ps_ttm": None, "market_cap_hkd_bn": None,
    }
    if yf is None:
        return empty

    def _fetch() -> dict[str, Any]:
        yf_symbol = f"{ticker.lstrip('0').zfill(4)}.HK"
        try:
            info = yf.Ticker(yf_symbol).info or {}
        except Exception:
            return empty
        pe = _clean_num(info.get("trailingPE"))
        pb = _clean_num(info.get("priceToBook"))
        ps = _clean_num(info.get("priceToSalesTrailing12Months"))
        mcap = _clean_num(info.get("marketCap"))
        # Keep only positive PE/PB (negative = loss, not meaningful for valuation)
        if pe is not None and pe <= 0:
            pe = None
        if pb is not None and pb <= 0:
            pb = None
        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName"),
            "pe_ttm": round(pe, 2) if pe else None,
            "pb": round(pb, 2) if pb else None,
            "ps_ttm": round(ps, 2) if ps else None,
            "market_cap_hkd_bn": round(mcap / 1e9, 2) if mcap else None,
        }

    try:
        result = cache.fetch("hk_fundamentals_yf", ticker, TTL_DAILY, _fetch)
    except Exception:
        result = dict(empty)

    # Futu fallback for missing PE/PB (esp. Meituan / MiniMax / 智谱)
    if result.get("pe_ttm") is None or result.get("pb") is None or result.get("name") is None:
        try:
            snap = futu_client.fetch_snapshot([ticker]).get(ticker)
        except Exception:
            snap = None
        if snap:
            if result.get("pe_ttm") is None:
                result["pe_ttm"] = snap.get("pe_ttm")
            if result.get("pb") is None:
                result["pb"] = snap.get("pb")
            if not result.get("name"):
                result["name"] = snap.get("name")
    return result


# ─────────────────────────── Market / macro ───────────────────────────


def fetch_market_liquidity() -> dict[str, Any]:
    """VHSI, USD/HKD, HIBOR, US10Y — best-effort, each field independent."""
    def _fetch() -> dict[str, Any]:
        out: dict[str, Any] = {
            "vhsi": None, "vhsi_change_pct": None, "usd_hkd": None,
            "hibor_1m": None, "hibor_3m": None, "us_10y_yield": None,
            "as_of": dt.date.today().isoformat(),
        }
        # VHSI via akshare sina
        try:
            vhsi_df = ak.stock_hk_index_daily_sina(symbol="VHSI")
            if vhsi_df is not None and not vhsi_df.empty:
                out["vhsi"] = round(float(vhsi_df["close"].iloc[-1]), 2)
                if len(vhsi_df) >= 2:
                    prev = float(vhsi_df["close"].iloc[-2])
                    if prev > 0:
                        out["vhsi_change_pct"] = round((out["vhsi"] / prev - 1) * 100, 2)
        except Exception:
            pass
        if yf is not None:
            # USD/HKD
            try:
                h = yf.Ticker("USDHKD=X").history(period="5d")
                if not h.empty:
                    out["usd_hkd"] = round(float(h["Close"].iloc[-1]), 4)
            except Exception:
                pass
            # US 10Y
            try:
                h = yf.Ticker("^TNX").history(period="5d")
                if not h.empty:
                    out["us_10y_yield"] = round(float(h["Close"].iloc[-1]), 2)
            except Exception:
                pass
        # akshare forex fallback for USD/HKD if yfinance failed
        if out.get("usd_hkd") is None:
            try:
                fx = ak.forex_hist_em(symbol="USDHKD")
                if fx is not None and not fx.empty:
                    out["usd_hkd"] = round(float(fx.iloc[-1]["最新价"]), 4)
            except Exception:
                pass
        # HIBOR via akshare (best-effort)
        try:
            hib = ak.rate_interbank(market="香港银行同业拆借市场", symbol="Hibor港币", indicator="1月")
            if hib is not None and not hib.empty:
                val = _clean_num(hib.iloc[-1].get("利率"))
                if val is not None:
                    out["hibor_1m"] = round(val, 3)
        except Exception:
            pass
        try:
            hib = ak.rate_interbank(market="香港银行同业拆借市场", symbol="Hibor港币", indicator="3月")
            if hib is not None and not hib.empty:
                val = _clean_num(hib.iloc[-1].get("利率"))
                if val is not None:
                    out["hibor_3m"] = round(val, 3)
        except Exception:
            pass
        return out

    try:
        return cache.fetch("hk_macro_liquidity", "v1", TTL_INTRADAY, _fetch)
    except Exception:
        return {
            "vhsi": None, "vhsi_change_pct": None, "usd_hkd": None,
            "hibor_1m": None, "hibor_3m": None, "us_10y_yield": None,
            "as_of": dt.date.today().isoformat(),
        }


def fetch_southbound_flow() -> dict[str, Any]:
    """Southbound (港股通) net inflow MTD/YTD in HKD billions."""
    empty = {
        "net_inflow_mtd_hkd_bn": None,
        "net_inflow_ytd_hkd_bn": None,
        "as_of": dt.date.today().isoformat(),
    }

    def _fetch() -> dict[str, Any]:
        try:
            df = ak.stock_hsgt_hist_em(symbol="港股通沪")
            df2 = ak.stock_hsgt_hist_em(symbol="港股通深")
        except Exception:
            return empty
        if df is None or df.empty:
            return empty
        # Expect columns like 日期, 当日资金流入/当日成交净买额
        def _extract(d: pd.DataFrame) -> pd.DataFrame:
            d = d.copy()
            if "日期" not in d.columns:
                return pd.DataFrame()
            d["日期"] = pd.to_datetime(d["日期"]).dt.date
            amt_col = None
            for c in ["当日成交净买额", "当日资金流入", "买入成交净额"]:
                if c in d.columns:
                    amt_col = c
                    break
            if amt_col is None:
                return pd.DataFrame()
            d["amt"] = pd.to_numeric(d[amt_col], errors="coerce")
            return d[["日期", "amt"]]

        a = _extract(df)
        b = _extract(df2)
        if a.empty and b.empty:
            return empty
        merged = pd.concat([a, b]).groupby("日期", as_index=False)["amt"].sum()
        today = dt.date.today()
        mtd_mask = merged["日期"].apply(lambda d: d.year == today.year and d.month == today.month)
        ytd_mask = merged["日期"].apply(lambda d: d.year == today.year)
        # Values from akshare are in 亿元 (HKD 100 mn). Convert to HKD bn (= 亿 / 10).
        mtd = merged.loc[mtd_mask, "amt"].sum() / 10
        ytd = merged.loc[ytd_mask, "amt"].sum() / 10
        return {
            "net_inflow_mtd_hkd_bn": round(float(mtd), 2) if mtd == mtd else None,
            "net_inflow_ytd_hkd_bn": round(float(ytd), 2) if ytd == ytd else None,
            "as_of": today.isoformat(),
        }

    try:
        return cache.fetch("hk_southbound_flow", "v1", TTL_DAILY, _fetch)
    except Exception:
        return empty
