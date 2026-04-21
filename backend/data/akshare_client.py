"""Typed data-access layer on top of akshare.

Each public function returns normalized pandas DataFrames (English column
names, ISO date strings as index) and transparently caches via SQLite.
"""

from __future__ import annotations

import datetime as dt
import pandas as pd
import akshare as ak

from backend.data.cache import cache


# TTLs (seconds)
TTL_INTRADAY = 60 * 10       # 10 min — for current-day snapshots
TTL_DAILY = 60 * 60 * 4      # 4h — end-of-day data, T+1 pipeline
TTL_STATIC = 60 * 60 * 24    # 24h — constituents, metadata


# --------------------------- Index prices ---------------------------

def index_daily_price(tx_symbol: str) -> pd.DataFrame:
    """Daily OHLCV for an index. Tencent first (20y+), falls back to Eastmoney
    for indices Tencent doesn't cover (e.g. CSI-series like 930955).

    Returns columns: date (str ISO), open, high, low, close, volume.
    """
    def _fetch_tx() -> pd.DataFrame:
        df = ak.stock_zh_index_daily_tx(symbol=tx_symbol)
        if df is None or df.empty:
            raise ValueError(f"Tencent returned empty for {tx_symbol}")
        df = df.rename(columns={"amount": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[["date", "open", "high", "low", "close", "volume"]].copy()

    def _fetch_csindex() -> pd.DataFrame:
        # Official csindex endpoint — reliable for CSI-series (9xxxxx) indices.
        code = tx_symbol[2:] if tx_symbol[:2] in ("sh", "sz") else tx_symbol
        end = dt.date.today().strftime("%Y%m%d")
        df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20050101", end_date=end)
        if df is None or df.empty:
            raise ValueError(f"csindex returned empty for {code}")
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[["date", "open", "high", "low", "close", "volume"]].copy()

    def _fetch_em() -> pd.DataFrame:
        code = tx_symbol[2:] if tx_symbol[:2] in ("sh", "sz") else tx_symbol
        em_symbol = f"csi{code}" if code.startswith("9") else tx_symbol
        df = ak.stock_zh_index_daily_em(symbol=em_symbol)
        if df is None or df.empty:
            raise ValueError(f"Eastmoney returned empty for {em_symbol}")
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[["date", "open", "high", "low", "close", "volume"]].copy()

    def _fetch() -> pd.DataFrame:
        try:
            return _fetch_tx()
        except Exception:
            pass
        try:
            return _fetch_csindex()
        except Exception:
            return _fetch_em()

    return cache.fetch("index_daily", tx_symbol, TTL_DAILY, _fetch)


# --------------------------- Valuation (csindex, official) ---------------------------

def index_valuation_csindex(code: str) -> pd.DataFrame:
    """Official csindex PE and dividend-yield snapshot (last ~20 trading days).

    Returns columns: date, pe_static, pe_ttm, dividend_yield, dividend_yield_ttm.
    """
    def _fetch() -> pd.DataFrame:
        df = ak.stock_zh_index_value_csindex(symbol=code)
        # csindex convention: 市盈率1/股息率1 = 滚动 (TTM); 市盈率2/股息率2 = 静态
        df = df.rename(columns={
            "日期": "date",
            "市盈率1": "pe_ttm",
            "市盈率2": "pe_static",
            "股息率1": "dividend_yield",
            "股息率2": "dividend_yield_static",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[[
            "date", "pe_static", "pe_ttm", "dividend_yield", "dividend_yield_static"
        ]].sort_values("date").reset_index(drop=True)

    return cache.fetch("index_val_csindex", code, TTL_INTRADAY, _fetch)


# --------------------------- Valuation history (csindex, long) ---------------------------

def index_pe_history_csindex(code: str) -> pd.DataFrame:
    """Long-history PE TTM from csindex 历史行情 endpoint.

    Covers the index from its inception — 3k+ trading days for mature indices
    like 000922 (中证红利). Only returns date + pe_ttm; csindex does not publish
    long-history 静态市盈率 or 股息率 through this endpoint.

    Returns columns: date, pe_ttm.
    """
    def _fetch() -> pd.DataFrame:
        end = dt.date.today().strftime("%Y%m%d")
        df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20050101", end_date=end)
        if df is None or df.empty:
            raise ValueError(f"csindex perf returned empty for {code}")
        df = df.rename(columns={"日期": "date", "滚动市盈率": "pe_ttm"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return (
            df[["date", "pe_ttm"]]
            .dropna(subset=["pe_ttm"])
            .sort_values("date")
            .reset_index(drop=True)
        )

    return cache.fetch("index_pe_csindex", code, TTL_DAILY, _fetch)


# --------------------------- Total-return series (csindex, long) ---------------------------

def index_tr_history_csindex(tr_code: str) -> pd.DataFrame:
    """Long-history close of a csindex total-return index (e.g. H00922).

    Used to derive rolling dividend yield: DY ≈ TR_return / Price_return - 1.

    Returns columns: date, close.
    """
    def _fetch() -> pd.DataFrame:
        end = dt.date.today().strftime("%Y%m%d")
        df = ak.stock_zh_index_hist_csindex(symbol=tr_code, start_date="20050101", end_date=end)
        if df is None or df.empty:
            raise ValueError(f"csindex perf returned empty for {tr_code}")
        df = df.rename(columns={"日期": "date", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return (
            df[["date", "close"]]
            .dropna(subset=["close"])
            .sort_values("date")
            .reset_index(drop=True)
        )

    return cache.fetch("index_tr_csindex", tr_code, TTL_DAILY, _fetch)


def index_dividend_yield_history(price_code: str, tr_code: str, window: int = 252) -> pd.DataFrame:
    """Derived rolling dividend yield from price + total-return csindex series.

    For each trading day t, DY(t) ≈ (TR(t)/TR(t-window)) / (P(t)/P(t-window)) - 1,
    expressed in percent. With window=252 trading days, this approximates the
    trailing-12-month dividend yield. Systematic difference from csindex's
    published 股息率 is ~5-10% (relative), because reinvested-dividend compounding
    is embedded in the TR series — but the historical *ranking* is faithful.

    Returns columns: date, dividend_yield (percent).
    """
    key = f"{price_code}:{tr_code}:{window}"

    def _fetch() -> pd.DataFrame:
        # Reuse the already-cached price series (from index_daily_price? no — that's
        # Tencent; use csindex's own close for consistent trading calendar with TR).
        end = dt.date.today().strftime("%Y%m%d")
        price_df = ak.stock_zh_index_hist_csindex(
            symbol=price_code, start_date="20050101", end_date=end
        )
        price_df = price_df.rename(columns={"日期": "date", "收盘": "price"})
        price_df["date"] = pd.to_datetime(price_df["date"]).dt.strftime("%Y-%m-%d")
        price_df = price_df[["date", "price"]].dropna()

        tr_df = index_tr_history_csindex(tr_code).rename(columns={"close": "tr"})

        m = pd.merge(price_df, tr_df, on="date").sort_values("date").reset_index(drop=True)
        m["dividend_yield"] = (
            (m["tr"] / m["tr"].shift(window)) / (m["price"] / m["price"].shift(window)) - 1
        ) * 100
        return (
            m[["date", "dividend_yield"]]
            .dropna(subset=["dividend_yield"])
            .reset_index(drop=True)
        )

    return cache.fetch("index_dy_derived", key, TTL_DAILY, _fetch)


# --------------------------- Valuation history (legulegu, 20y) ---------------------------

def index_pe_history_lg(lg_symbol: str) -> pd.DataFrame:
    """Long-history PE (static + TTM) from legulegu.

    Returns columns: date, index_value, pe_static, pe_ttm, pe_static_median, pe_ttm_median.
    """
    def _fetch() -> pd.DataFrame:
        df = ak.stock_index_pe_lg(symbol=lg_symbol)
        df = df.rename(columns={
            "日期": "date",
            "指数": "index_value",
            "静态市盈率": "pe_static",
            "滚动市盈率": "pe_ttm",
            "静态市盈率中位数": "pe_static_median",
            "滚动市盈率中位数": "pe_ttm_median",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        keep = ["date", "index_value", "pe_static", "pe_ttm", "pe_static_median", "pe_ttm_median"]
        return df[keep].sort_values("date").reset_index(drop=True)

    return cache.fetch("index_pe_lg", lg_symbol, TTL_DAILY, _fetch)


def index_pb_history_lg(lg_symbol: str) -> pd.DataFrame:
    """Long-history PB from legulegu."""
    def _fetch() -> pd.DataFrame:
        df = ak.stock_index_pb_lg(symbol=lg_symbol)
        df = df.rename(columns={
            "日期": "date",
            "指数": "index_value",
            "市净率": "pb",
            "市净率中位数": "pb_median",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        keep = [c for c in ["date", "index_value", "pb", "pb_median"] if c in df.columns]
        return df[keep].sort_values("date").reset_index(drop=True)

    return cache.fetch("index_pb_lg", lg_symbol, TTL_DAILY, _fetch)


# --------------------------- Constituents ---------------------------

def index_constituents(code: str) -> pd.DataFrame:
    """Current index constituents with weights (if available).

    Weight data is published monthly (end of month); may lag real-time holdings.
    """
    def _fetch() -> pd.DataFrame:
        try:
            df = ak.index_stock_cons_weight_csindex(symbol=code)
            df = df.rename(columns={
                "日期": "date",
                "成分券代码": "stock_code",
                "成分券名称": "stock_name",
                "交易所": "exchange",
                "权重": "weight",
            })
            return df[["date", "stock_code", "stock_name", "exchange", "weight"]].copy()
        except Exception:
            df = ak.index_stock_cons_csindex(symbol=code)
            df = df.rename(columns={
                "日期": "date",
                "成分券代码": "stock_code",
                "成分券名称": "stock_name",
                "交易所": "exchange",
            })
            df["weight"] = None
            return df[["date", "stock_code", "stock_name", "exchange", "weight"]].copy()

    return cache.fetch("index_cons", code, TTL_STATIC, _fetch)


# --------------------------- Treasury yield ---------------------------

def china_treasury_10y(start_date: str | None = None) -> pd.DataFrame:
    """China 10-year treasury yield time series.

    Returns columns: date, yield_10y.
    """
    if start_date is None:
        start_date = (dt.date.today() - dt.timedelta(days=365 * 11)).strftime("%Y%m%d")

    def _fetch() -> pd.DataFrame:
        df = ak.bond_zh_us_rate(start_date=start_date)
        df = df.rename(columns={
            "日期": "date",
            "中国国债收益率10年": "yield_10y",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[["date", "yield_10y"]].dropna().sort_values("date").reset_index(drop=True)

    return cache.fetch("bond_10y", start_date, TTL_DAILY, _fetch)
