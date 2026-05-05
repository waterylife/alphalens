"""US equity data client — yfinance primary, Futu US as supplement.

yfinance is 15-min delayed but free and reliable for:
- Prices / K-line / VIX / US10Y / DXY / sector ETFs
- Fundamentals (PE, PB, PEG, forward PE, market cap, ROE, margins, growth)

Futu US gives real-time snapshots if the market data subscription is active;
otherwise turnover/last_price may be stale.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

from backend.data.cache import cache
from backend.data import futu_client

TTL_INTRADAY = 60 * 5
TTL_DAILY = 60 * 60 * 4
TTL_STATIC = 60 * 60 * 24

# Magnificent 7 + broad-market ETFs
DEFAULT_US_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "SPY", "QQQ",
]

# 11 SPDR sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Cons. Disc.",
    "XLP": "Cons. Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Comm. Services",
}


def normalize_us(ticker: str) -> str:
    """Uppercase the ticker, strip spaces, allow BRK.B / BRK-B style."""
    return ticker.strip().upper()


def _yf_ticker(t: str):
    return yf.Ticker(t) if _YF_OK else None


def _download_frame_for_ticker(hist: pd.DataFrame | None, ticker: str, n_tickers: int) -> pd.DataFrame | None:
    """Extract one ticker's OHLCV frame from yfinance.download output.

    yfinance may return columns as either (Ticker, Price) when batch
    downloading, or (Price, Ticker) for some single-ticker symbols such as
    BRK-B. Normalize both shapes to a plain Close/Volume frame.
    """
    if hist is None:
        return None
    if not isinstance(hist.columns, pd.MultiIndex):
        return hist

    level0 = set(map(str, hist.columns.get_level_values(0)))
    level1 = set(map(str, hist.columns.get_level_values(1)))
    if ticker in level0:
        return hist[ticker]
    if ticker in level1:
        return hist.xs(ticker, axis=1, level=1)
    if n_tickers == 1:
        return hist.droplevel(1, axis=1)
    return None


def _price_to_book(ticker: str, info: dict[str, Any]) -> float | None:
    """Return a usable P/B ratio from yfinance info.

    yfinance reports BRK-B's ``bookValue`` on Berkshire Class A share terms,
    while ``currentPrice`` is Class B. Since 1 BRK-A = 1500 BRK-B, adjust the
    book value before deriving P/B. The raw ``priceToBook`` for BRK-B is
    therefore tiny (~0.001) and should not be displayed.
    """
    raw_pb = _as_float(info.get("priceToBook"))
    if raw_pb is not None and raw_pb >= 0.01:
        return raw_pb

    price = _as_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    book_value = _as_float(info.get("bookValue"))
    if price is None or book_value is None or book_value <= 0:
        return raw_pb if raw_pb and raw_pb > 0 else None

    if ticker.upper().replace(".", "-") == "BRK-B" and book_value > 10_000:
        book_value = book_value / 1500

    pb = price / book_value
    return pb if pb > 0 else None


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ─────────────────────────── Snapshot ───────────────────────────


def fetch_snapshot(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Return {ticker: {name, price, change_pct, volume_usd_mn}} via yfinance
    (falls back per-ticker on failure)."""
    if not tickers or not _YF_OK:
        return {}
    key = ",".join(sorted(tickers))

    def _fetch() -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        # yfinance batch via download for prices
        try:
            hist = yf.download(
                tickers, period="5d", interval="1d",
                group_by="ticker", progress=False, auto_adjust=False,
                threads=True,
            )
        except Exception:
            hist = None

        for t in tickers:
            name = price = chg = vol_usd_mn = None
            try:
                if hist is not None:
                    df = _download_frame_for_ticker(hist, t, len(tickers))
                    df = df.dropna(subset=["Close"]) if df is not None else None
                    if df is not None and len(df) >= 2:
                        last = float(df["Close"].iloc[-1])
                        prev = float(df["Close"].iloc[-2])
                        vol = float(df["Volume"].iloc[-1]) if "Volume" in df else 0
                        price = round(last, 2)
                        chg = round((last / prev - 1) * 100, 2) if prev else None
                        vol_usd_mn = round(vol * last / 1_000_000, 1) if vol else None
            except Exception:
                pass
            # Get name from info (cheap)
            try:
                info = _yf_ticker(t).info
                name = info.get("shortName") or info.get("longName")
            except Exception:
                pass
            out[t] = {
                "ticker": t, "name": name, "price": price,
                "change_pct": chg, "volume_usd_mn": vol_usd_mn,
            }
        return out

    try:
        return cache.fetch("us_snapshot", key, TTL_INTRADAY, _fetch)
    except Exception:
        return {}


# ─────────────────────────── Fundamentals ───────────────────────────


def fetch_fundamentals(ticker: str) -> dict[str, Any]:
    """Core fundamentals via yfinance .info."""
    empty = {
        "ticker": ticker, "name": None, "pe_ttm": None, "forward_pe": None,
        "peg": None, "pb": None, "ps_ttm": None, "market_cap_usd_bn": None,
        "revenue_growth_pct": None, "gross_margin_pct": None, "roe_pct": None,
        "eps_ttm": None, "dividend_yield_pct": None, "beta": None,
    }
    if not _YF_OK:
        return empty

    def _fetch() -> dict[str, Any]:
        try:
            info = _yf_ticker(ticker).info
        except Exception:
            return empty

        def num(k: str) -> float | None:
            v = info.get(k)
            try:
                f = float(v)
                return f if f == f else None
            except (TypeError, ValueError):
                return None

        def pct(k: str) -> float | None:
            v = num(k)
            return round(v * 100, 2) if v is not None else None

        mc = num("marketCap")
        pe = num("trailingPE")
        pb = _price_to_book(ticker, info)
        fpe = num("forwardPE")
        peg = num("pegRatio")
        ps = num("priceToSalesTrailing12Months")

        def positive_rounded(v: float | None, digits = 2) -> float | None:
            if v is None or v <= 0:
                return None
            rounded = round(v, digits)
            return rounded if rounded > 0 else None

        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName"),
            "pe_ttm": round(pe, 2) if pe and pe > 0 else None,
            "forward_pe": round(fpe, 2) if fpe and fpe > 0 else None,
            "peg": positive_rounded(peg),
            "pb": positive_rounded(pb),
            "ps_ttm": positive_rounded(ps),
            "market_cap_usd_bn": round(mc / 1_000_000_000, 1) if mc else None,
            "revenue_growth_pct": pct("revenueGrowth"),
            "gross_margin_pct": pct("grossMargins"),
            "roe_pct": pct("returnOnEquity"),
            "eps_ttm": round(num("trailingEps"), 2) if num("trailingEps") else None,
            "dividend_yield_pct": pct("dividendYield") if info.get("dividendYield") and info.get("dividendYield") < 1 else num("dividendYield"),
            "beta": round(num("beta"), 2) if num("beta") else None,
        }

    try:
        return cache.fetch("us_fund", ticker, TTL_DAILY, _fetch)
    except Exception:
        return empty


# ─────────────────────────── Price history & technicals ───────────────────────────


def _history(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Cached daily history."""
    def _fetch() -> pd.DataFrame:
        try:
            df = _yf_ticker(ticker).history(period=period, auto_adjust=False)
            return df if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    try:
        return cache.fetch("us_hist", f"{ticker}:{period}", TTL_DAILY, _fetch)
    except Exception:
        return pd.DataFrame()


def compute_returns(ticker: str) -> dict[str, Any]:
    """1M / 3M / 6M / 12M returns."""
    empty = {"ticker": ticker, "ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12m": None}
    df = _history(ticker, period="2y")
    if df.empty or "Close" not in df.columns:
        return empty
    close = df["Close"].dropna()
    if close.empty:
        return empty
    latest = float(close.iloc[-1])

    def lookback(days: int) -> float | None:
        if len(close) <= days:
            return None
        prev = float(close.iloc[-1 - days])
        if prev <= 0:
            return None
        return round((latest / prev - 1) * 100, 2)

    return {
        "ticker": ticker,
        "ret_1m": lookback(21),
        "ret_3m": lookback(63),
        "ret_6m": lookback(126),
        "ret_12m": lookback(252),
    }


def compute_technicals(ticker: str) -> dict[str, Any]:
    """RSI14, dist MA200, 52w pos, dist ATH, ADTV 20d."""
    empty = {
        "ticker": ticker, "rsi14": None, "dist_ma200_pct": None,
        "pos_52w_pct": None, "dist_ath_pct": None, "adtv_20d_usd_mn": None,
        "short_pct_float": None,
    }
    df = _history(ticker, period="2y")
    if df.empty or "Close" not in df.columns:
        return empty
    close = df["Close"].dropna()
    if close.empty:
        return empty
    latest = float(close.iloc[-1])

    # RSI14
    rsi = None
    if len(close) >= 15:
        delta = close.diff().dropna()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        if not loss.empty and loss.iloc[-1] > 0:
            rs = float(gain.iloc[-1]) / float(loss.iloc[-1])
            rsi = round(100 - 100 / (1 + rs), 1)

    # MA200
    dist_ma200 = None
    if len(close) >= 200:
        ma = float(close.tail(200).mean())
        if ma > 0:
            dist_ma200 = round((latest - ma) / ma * 100, 2)

    # 52w pos
    pos_52w = None
    if len(close) >= 60:
        win = close.tail(252) if len(close) >= 252 else close
        hi, lo = float(win.max()), float(win.min())
        if hi > lo:
            pos_52w = round((latest - lo) / (hi - lo) * 100, 1)

    # Distance from all-time high (within this 2y window)
    ath = float(close.max())
    dist_ath = round((latest - ath) / ath * 100, 2) if ath > 0 else None

    # ADTV 20d (USD mn) = mean(Volume × Close)
    adtv = None
    if "Volume" in df.columns:
        last20 = df.tail(20)
        dol = (last20["Volume"].fillna(0) * last20["Close"].fillna(0))
        if not dol.empty:
            adtv = round(float(dol.mean()) / 1_000_000, 1)

    # Short interest % float — from info
    short_pct = None
    try:
        info = _yf_ticker(ticker).info
        v = info.get("shortPercentOfFloat")
        if v is not None:
            short_pct = round(float(v) * 100, 2)
    except Exception:
        pass

    return {
        "ticker": ticker, "rsi14": rsi, "dist_ma200_pct": dist_ma200,
        "pos_52w_pct": pos_52w, "dist_ath_pct": dist_ath,
        "adtv_20d_usd_mn": adtv, "short_pct_float": short_pct,
    }


# ─────────────────────────── Macro ───────────────────────────


def fetch_macro() -> dict[str, Any]:
    """VIX · US10Y · US2Y · DXY · Fed Funds (IRX 13W)."""
    empty = {
        "vix": None, "vix_change_pct": None,
        "us_10y": None, "us_2y": None, "dxy": None, "fed_funds_13w": None,
        "curve_2s10s_bps": None, "as_of": dt.date.today().isoformat(),
    }

    def _fetch() -> dict[str, Any]:
        if not _YF_OK:
            return empty
        out = dict(empty)

        def latest(sym: str, days: int = 5) -> tuple[float | None, float | None]:
            try:
                h = yf.Ticker(sym).history(period=f"{days}d")
                if h.empty:
                    return None, None
                last = float(h["Close"].iloc[-1])
                prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else None
                chg = round((last / prev - 1) * 100, 2) if prev else None
                return round(last, 3), chg
            except Exception:
                return None, None

        out["vix"], out["vix_change_pct"] = latest("^VIX")
        us10, _ = latest("^TNX")
        us2, _ = latest("^UST2YR")
        if us2 is None:
            # Fallback: 2Y yield via different symbol — else leave None
            us2, _ = latest("2YY=F")
        out["us_10y"] = us10
        out["us_2y"] = us2
        out["dxy"], _ = latest("DX-Y.NYB")
        out["fed_funds_13w"], _ = latest("^IRX")
        if us10 is not None and us2 is not None:
            out["curve_2s10s_bps"] = round((us10 - us2) * 100, 1)
        return out

    try:
        return cache.fetch("us_macro", "main", TTL_INTRADAY * 2, _fetch)
    except Exception:
        return empty


# ─────────────────────────── Sector ETFs ───────────────────────────


def fetch_sector_flow() -> dict[str, Any]:
    """11 SPDR sector ETF 1-day and 5-day returns."""
    empty = {"items": [], "as_of": dt.date.today().isoformat()}

    def _fetch() -> dict[str, Any]:
        if not _YF_OK:
            return empty
        items = []
        for sym, sector in SECTOR_ETFS.items():
            try:
                h = yf.Ticker(sym).history(period="1mo")
                if h.empty or len(h) < 6:
                    continue
                close = h["Close"].dropna()
                last = float(close.iloc[-1])
                d1 = (last / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else None
                d5 = (last / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else None
                vol = float(h["Volume"].iloc[-1]) if "Volume" in h else 0
                items.append({
                    "ticker": sym, "sector": sector,
                    "price": round(last, 2),
                    "change_pct": round(d1, 2) if d1 is not None else None,
                    "change_5d_pct": round(d5, 2) if d5 is not None else None,
                    "volume_usd_mn": round(vol * last / 1_000_000, 1) if vol else None,
                })
            except Exception:
                continue
        items.sort(key=lambda x: (x.get("change_pct") or -999), reverse=True)
        return {"items": items, "as_of": dt.date.today().isoformat()}

    try:
        return cache.fetch("us_sector", "flow", TTL_INTRADAY, _fetch)
    except Exception:
        return empty


# ─────────────────────────── Indices chart ───────────────────────────


def fetch_index_history(symbol: str, years: int = 1) -> pd.DataFrame:
    period = f"{max(1, years)}y"

    def _fetch() -> pd.DataFrame:
        if not _YF_OK:
            return pd.DataFrame()
        try:
            df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.reset_index()
            df = df.rename(columns={"Date": "date", "Close": "close"})
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            return df[["date", "close"]]
        except Exception:
            return pd.DataFrame()

    try:
        return cache.fetch("us_idx_hist", f"{symbol}:{years}", TTL_DAILY, _fetch)
    except Exception:
        return pd.DataFrame()


def fetch_asset_history(symbol: str, years: int = 10) -> pd.DataFrame:
    """Daily OHLCV history for a US ETF/stock, normalized to dashboard columns."""
    period = f"{max(1, years)}y"

    def _fetch() -> pd.DataFrame:
        if not _YF_OK:
            return pd.DataFrame()
        try:
            df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.reset_index()
            df = df.rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            cols = ["date", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]
        except Exception:
            return pd.DataFrame()

    try:
        return cache.fetch("us_asset_hist", f"{symbol}:{years}", TTL_DAILY, _fetch)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────── Search ───────────────────────────


def search_us_tickers(q: str, limit: int = 10) -> list[dict[str, str]]:
    """Fallback search via yfinance Tickers — simplest approach is prefix match
    against a small in-memory dictionary + direct .info lookup."""
    q = q.strip().upper()
    if not q or not _YF_OK:
        return []
    # Try direct lookup first
    try:
        info = yf.Ticker(q).info
        if info and (info.get("shortName") or info.get("longName")):
            return [{"ticker": q, "name": info.get("shortName") or info.get("longName")}]
    except Exception:
        pass
    return []
