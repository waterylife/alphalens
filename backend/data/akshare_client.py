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
    """20y+ daily OHLCV for an index from Tencent (most reliable, current).

    Returns columns: date (str ISO), open, high, low, close, volume.
    Indexed by date.
    """
    def _fetch() -> pd.DataFrame:
        df = ak.stock_zh_index_daily_tx(symbol=tx_symbol)
        df = df.rename(columns={"amount": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[["date", "open", "high", "low", "close", "volume"]].copy()

    return cache.fetch("index_daily_tx", tx_symbol, TTL_DAILY, _fetch)


# --------------------------- Valuation (csindex, official) ---------------------------

def index_valuation_csindex(code: str) -> pd.DataFrame:
    """Official csindex PE and dividend-yield snapshot (last ~20 trading days).

    Returns columns: date, pe_static, pe_ttm, dividend_yield, dividend_yield_ttm.
    """
    def _fetch() -> pd.DataFrame:
        df = ak.stock_zh_index_value_csindex(symbol=code)
        df = df.rename(columns={
            "日期": "date",
            "市盈率1": "pe_static",
            "市盈率2": "pe_ttm",
            "股息率1": "dividend_yield",
            "股息率2": "dividend_yield_ttm",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[[
            "date", "pe_static", "pe_ttm", "dividend_yield", "dividend_yield_ttm"
        ]].sort_values("date").reset_index(drop=True)

    return cache.fetch("index_val_csindex", code, TTL_INTRADAY, _fetch)


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
