"""API endpoints for the HK tech stock dashboard."""

from __future__ import annotations

import datetime as dt
import concurrent.futures
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query

from backend.data import hk_client, futu_client
from backend.strategy import hk_signals
from backend.schemas import (
    BenchmarkCompare,
    ComparePoint,
    CompareSeries,
    HKStockSnapshot,
    HKStockReturn,
    HKStockSearchResult,
    HKIndexChart,
    HKIndexChartPoint,
    HKStockTechnical,
    HKStockFundamental,
    HKMarketLiquidity,
    HKSouthbound,
    HKSectorFlow,
    HKSectorFlowRow,
    HKETFPanel,
    HKETFRow,
    RangeStats,
    HKStrategySignal,
    HKStrategyComponents,
    YearlyRow,
)

router = APIRouter(prefix="/api/hktech", tags=["hk-tech"])

DEFAULT_TICKERS = ["00700", "09988", "03690", "09961", "00100", "02513"]


def _safe_float(val: Any) -> float | None:
    try:
        f = float(val)
        return f if (f == f) else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _snapshot_from_row(ticker: str, row: pd.Series, as_of: str) -> HKStockSnapshot:
    """Build a HKStockSnapshot from a row of stock_hk_spot (Sina) DataFrame.

    Sina does not publish PE/PB in this endpoint — those fields are null.
    涨跌幅 from Sina is already in percent (e.g. -0.61633 means -0.62%... actually
    Sina returns the value directly as a percent like '-0.61633' for -0.61%).
    """
    price = _safe_float(row.get("最新价"))
    change_pct = _safe_float(row.get("涨跌幅"))
    vol_raw = _safe_float(row.get("成交额"))
    volume_hkd_mn = round(vol_raw / 1_000_000, 2) if vol_raw else None

    name = (
        str(row.get("中文名称", "") or row.get("名称", "") or row.get("英文名称", ""))
        or None
    )
    return HKStockSnapshot(
        ticker=ticker,
        name=name,
        price=price,
        change_pct=change_pct,
        pe_ttm=None,
        pb=None,
        volume_hkd_mn=volume_hkd_mn,
        as_of=as_of,
    )


def _resolve_code_column(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a '代码' column exists with 5-digit HK codes."""
    if "代码" in df.columns:
        df = df.copy()
        df["代码"] = df["代码"].astype(str).str.zfill(5)
        return df
    idx_name = df.index.name or ""
    if idx_name == "代码" or df.index.dtype == object:
        df = df.reset_index()
        df = df.rename(columns={df.columns[0]: "代码"})
        df["代码"] = df["代码"].astype(str).str.zfill(5)
        return df
    df = df.copy()
    df.insert(0, "代码", df.iloc[:, 0].astype(str).str.zfill(5))
    return df


# ─────────────────────────── Endpoints ───────────────────────────


@router.get("/stocks/defaults", response_model=list[str])
def get_default_tickers() -> list[str]:
    """Return the default 6 HK tech tickers."""
    return DEFAULT_TICKERS


@router.get("/stocks/snapshot", response_model=list[HKStockSnapshot])
def get_stocks_snapshot(
    tickers: str = Query(
        default=",".join(DEFAULT_TICKERS),
        description="Comma-separated 4- or 5-digit HK tickers, e.g. '0700,9988'",
    ),
) -> list[HKStockSnapshot]:
    ticker_list = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]
    as_of = dt.date.today().isoformat()
    yf_lookup = hk_client.fetch_stock_snapshots_yf(ticker_list)

    results: list[HKStockSnapshot] = []
    for ticker in ticker_list:
        if ticker in yf_lookup:
            d = yf_lookup[ticker]
            results.append(HKStockSnapshot(
                ticker=ticker,
                name=d.get("name"),
                price=d.get("price"),
                change_pct=d.get("change_pct"),
                pe_ttm=None,
                pb=None,
                volume_hkd_mn=d.get("volume_hkd_mn"),
                as_of=as_of,
            ))
        else:
            results.append(HKStockSnapshot(ticker=ticker, name=None, price=None,
                                           change_pct=None, pe_ttm=None, pb=None,
                                           volume_hkd_mn=None, as_of=as_of))
    return results


@router.get("/stocks/returns", response_model=list[HKStockReturn])
def get_stocks_returns(
    tickers: str = Query(
        default=",".join(DEFAULT_TICKERS),
        description="Comma-separated HK tickers",
    ),
) -> list[HKStockReturn]:
    """Compute 1M/3M/6M/12M returns for each ticker from price history (parallel)."""
    ticker_list = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]

    def compute(t: str) -> HKStockReturn:
        try:
            d = hk_client.compute_stock_returns(t)
        except Exception:
            d = {"ticker": t, "ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12m": None}
        return HKStockReturn(**d)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(compute, t): t for t in ticker_list}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Preserve input order
    order = {t: i for i, t in enumerate(ticker_list)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/stocks/search", response_model=list[HKStockSearchResult])
def search_stocks(
    q: str = Query(description="Stock code or name fragment, min 1 char"),
    limit: int = Query(default=10, le=30),
) -> list[HKStockSearchResult]:
    """Search HK stocks by code or name fragment."""
    q = q.strip()
    if not q:
        return []

    try:
        all_df = hk_client.hk_stocks_all_snapshot()
        all_df = _resolve_code_column(all_df)
    except Exception:
        return []

    q_lower = q.lower()
    q_padded = hk_client.normalize_ticker(q) if q.isdigit() else None

    mask = all_df["代码"].str.contains(q, na=False)
    for name_col in ("中文名称", "名称", "英文名称"):
        if name_col in all_df.columns:
            mask = mask | all_df[name_col].astype(str).str.contains(q_lower, case=False, na=False)
    if q_padded:
        mask = mask | (all_df["代码"] == q_padded)

    subset = all_df[mask].head(limit)
    out = []
    for _, row in subset.iterrows():
        name = row.get("中文名称") or row.get("名称") or row.get("英文名称") or ""
        out.append(HKStockSearchResult(ticker=str(row["代码"]).zfill(5), name=str(name)))
    return out


@router.get("/stocks/technicals", response_model=list[HKStockTechnical])
def get_stocks_technicals(
    tickers: str = Query(default=",".join(DEFAULT_TICKERS)),
) -> list[HKStockTechnical]:
    """RSI14 / dist_MA200 / ADTV_20d + Futu snapshot (turnover_rate / volume_ratio) + capital flow."""
    ticker_list = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]

    # Bulk snapshot once (cheap single RPC)
    snap_map = futu_client.fetch_snapshot(ticker_list)

    def compute(t: str) -> HKStockTechnical:
        try:
            d = hk_client.compute_stock_technicals(t)
        except Exception:
            d = {"ticker": t, "rsi14": None, "dist_ma200_pct": None, "adtv_20d_hkd_mn": None}
        snap = snap_map.get(t) or {}
        d["turnover_rate"] = snap.get("turnover_rate")
        d["volume_ratio"] = snap.get("volume_ratio")
        try:
            cf = futu_client.fetch_capital_flow(t)
            d["net_inflow_today_hkd_mn"] = cf.get("net_inflow_today_hkd_mn")
            d["net_inflow_5d_hkd_mn"] = cf.get("net_inflow_5d_hkd_mn")
        except Exception:
            d["net_inflow_today_hkd_mn"] = None
            d["net_inflow_5d_hkd_mn"] = None
        try:
            ob = futu_client.fetch_order_book_metrics(t)
            d["bid_ask_spread_bps"] = ob.get("bid_ask_spread_bps")
            d["depth_ratio_5"] = ob.get("depth_ratio_5")
        except Exception:
            d["bid_ask_spread_bps"] = None
            d["depth_ratio_5"] = None
        return HKStockTechnical(**d)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(compute, t): t for t in ticker_list}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(ticker_list)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/stocks/fundamentals", response_model=list[HKStockFundamental])
def get_stocks_fundamentals(
    tickers: str = Query(default=",".join(DEFAULT_TICKERS)),
) -> list[HKStockFundamental]:
    """PE / PB / PS / market cap per ticker via yfinance (parallel)."""
    ticker_list = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]

    def fetch(t: str) -> HKStockFundamental:
        try:
            d = hk_client.fetch_stock_fundamentals(t)
        except Exception:
            d = {"ticker": t, "name": None, "pe_ttm": None, "pb": None,
                 "ps_ttm": None, "market_cap_hkd_bn": None}
        return HKStockFundamental(**d)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, t): t for t in ticker_list}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(ticker_list)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/market/liquidity", response_model=HKMarketLiquidity)
def get_market_liquidity() -> HKMarketLiquidity:
    d = hk_client.fetch_market_liquidity()
    return HKMarketLiquidity(**d)


@router.get("/market/southbound", response_model=HKSouthbound)
def get_southbound() -> HKSouthbound:
    d = hk_client.fetch_southbound_flow()
    return HKSouthbound(**d)


@router.get("/market/sector-flow", response_model=HKSectorFlow)
def get_sector_flow(
    tickers: str = Query(default=",".join(DEFAULT_TICKERS)),
) -> HKSectorFlow:
    """Aggregate net capital inflow across the watchlist (HK tech proxy)."""
    ticker_list = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]
    snap_map = futu_client.fetch_snapshot(ticker_list)

    def one(t: str) -> HKSectorFlowRow:
        try:
            cf = futu_client.fetch_capital_flow(t)
        except Exception:
            cf = {}
        name = (snap_map.get(t) or {}).get("name")
        return HKSectorFlowRow(
            ticker=t,
            name=name,
            today_hkd_mn=cf.get("net_inflow_today_hkd_mn"),
            d5_hkd_mn=cf.get("net_inflow_5d_hkd_mn"),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(one, ticker_list))

    today_vals = [r.today_hkd_mn for r in rows if r.today_hkd_mn is not None]
    d5_vals = [r.d5_hkd_mn for r in rows if r.d5_hkd_mn is not None]
    return HKSectorFlow(
        total_today_hkd_mn=round(sum(today_vals), 1) if today_vals else None,
        total_5d_hkd_mn=round(sum(d5_vals), 1) if d5_vals else None,
        breakdown=rows,
        as_of=dt.date.today().isoformat(),
    )


HK_TECH_ETFS = ["03033", "03067", "03088"]


@router.get("/market/etf-panel", response_model=HKETFPanel)
def get_etf_panel() -> HKETFPanel:
    """HK tech ETFs price + change vs HSTECH index (tracking gap today)."""
    # HSTECH today change
    idx_chg: float | None = None
    try:
        df = hk_client.hstech_index_hist(years=1)
        if not df.empty and "close" in df.columns and len(df) >= 2:
            last, prev = float(df.iloc[-1]["close"]), float(df.iloc[-2]["close"])
            if prev > 0:
                idx_chg = round((last / prev - 1) * 100, 2)
    except Exception:
        pass

    # ETFs via Sina snapshot (names/price/change) + Futu fallback
    try:
        all_df = hk_client.hk_stocks_all_snapshot()
        all_df = _resolve_code_column(all_df)
        lookup = all_df.set_index("代码")
    except Exception:
        lookup = pd.DataFrame()

    futu_snap = futu_client.fetch_snapshot(HK_TECH_ETFS)
    items: list[HKETFRow] = []
    for t in HK_TECH_ETFS:
        price = chg = vol_mn = None
        name = None
        if not lookup.empty and t in lookup.index:
            row = lookup.loc[t]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            price = _safe_float(row.get("最新价"))
            chg = _safe_float(row.get("涨跌幅"))
            v = _safe_float(row.get("成交额"))
            vol_mn = round(v / 1_000_000, 2) if v else None
            name = str(row.get("中文名称") or row.get("名称") or "") or None
        fs = futu_snap.get(t) or {}
        if not name:
            name = fs.get("name")
        if price is None:
            price = fs.get("last_price")
        if chg is None:
            chg = fs.get("change_pct")
        if vol_mn is None:
            vol_mn = fs.get("turnover_hkd_mn")
        gap = (
            round(chg - idx_chg, 2)
            if (chg is not None and idx_chg is not None)
            else None
        )
        items.append(
            HKETFRow(
                ticker=t, name=name, price=price, change_pct=chg,
                volume_hkd_mn=vol_mn, tracking_gap_pct=gap,
            )
        )
    return HKETFPanel(
        index_change_pct=idx_chg,
        items=items,
        as_of=dt.date.today().isoformat(),
    )


@router.get("/index/chart", response_model=HKIndexChart)
def get_index_chart(years: int = Query(default=1, ge=1, le=5)) -> HKIndexChart:
    """HSTECH index price history."""
    try:
        df = hk_client.hstech_index_hist(years=years)
    except Exception:
        return HKIndexChart(points=[])

    if df.empty or "close" not in df.columns:
        return HKIndexChart(points=[])

    points = [
        HKIndexChartPoint(date=str(row["date"]), close=float(row["close"]))
        for _, row in df.iterrows()
        if row["close"] and row["close"] == row["close"]
    ]
    return HKIndexChart(points=points)


@router.get("/index/benchmark-compare", response_model=BenchmarkCompare)
def get_index_benchmark_compare(
    years: int = Query(default=3, ge=1, le=5),
) -> BenchmarkCompare:
    """Compare HSTECH with Hang Seng Index over the selected range."""
    idx_df = hk_client.hstech_index_hist(years=years)[["date", "close"]]
    bm_df = hk_client.hsi_index_hist(years=years)[["date", "close"]]
    merged = pd.merge(idx_df, bm_df, on="date", how="inner", suffixes=("_idx", "_bm"))
    merged = merged.sort_values("date").reset_index(drop=True)

    if merged.empty:
        empty = _range_stats([], [])
        return BenchmarkCompare(
            start="",
            end="",
            index=CompareSeries(code="HSTECH", name="恒生科技指数", points=[], stats=empty),
            benchmark=CompareSeries(code="HSI", name="恒生指数", points=[], stats=empty),
            yearly=[],
        )

    dates = merged["date"].astype(str).tolist()
    idx_closes = merged["close_idx"].astype(float).values
    bm_closes = merged["close_bm"].astype(float).values

    return BenchmarkCompare(
        start=str(merged.iloc[0]["date"]),
        end=str(merged.iloc[-1]["date"]),
        index=CompareSeries(
            code="HSTECH",
            name="恒生科技指数",
            points=[ComparePoint(date=d, close=float(c)) for d, c in zip(dates, idx_closes)],
            stats=_range_stats(idx_closes, dates),
        ),
        benchmark=CompareSeries(
            code="HSI",
            name="恒生指数",
            points=[ComparePoint(date=d, close=float(c)) for d, c in zip(dates, bm_closes)],
            stats=_range_stats(bm_closes, dates),
        ),
        yearly=_yearly_rows(merged),
    )


@router.get("/stocks/signals", response_model=list[HKStrategySignal])
def get_stocks_signals(
    tickers: str = Query(default=",".join(DEFAULT_TICKERS)),
) -> list[HKStrategySignal]:
    tl = [hk_client.normalize_ticker(t) for t in tickers.split(",") if t.strip()]
    try:
        macro = hk_client.fetch_market_liquidity()
    except Exception:
        macro = None
    try:
        southbound = hk_client.fetch_southbound_flow()
    except Exception:
        southbound = None

    def one(t: str) -> HKStrategySignal:
        try:
            d = hk_signals.compute_signal_with_rationale(t, macro, southbound)
            return HKStrategySignal(
                ticker=d.get("ticker", t),
                action=d.get("action", "hold"),
                score=d.get("score"),
                components=HKStrategyComponents(**(d.get("components") or {})),
                triggers=d.get("triggers") or [],
                explanation=d.get("explanation"),
            )
        except Exception:
            return HKStrategySignal(
                ticker=t, action="hold", score=None,
                components=HKStrategyComponents(), triggers=[], explanation=None,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, t): t for t in tl}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(tl)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


def _range_stats(closes, dates) -> RangeStats:
    import numpy as np

    closes = list(closes)
    if len(closes) < 2:
        return RangeStats(
            return_pct=None,
            annualized_pct=None,
            max_drawdown=None,
            max_gain=None,
            volatility=None,
        )

    s = pd.Series(closes).astype(float)
    first, last = s.iloc[0], s.iloc[-1]
    ret = (last / first - 1) * 100

    d0 = pd.to_datetime(dates[0])
    dN = pd.to_datetime(dates[-1])
    years = max((dN - d0).days / 365.25, 1e-9)
    ann = ((last / first) ** (1 / years) - 1) * 100 if first > 0 else None

    dr = s.pct_change().dropna()
    vol = float(dr.std() * np.sqrt(252) * 100) if len(dr) > 1 else None
    running_max = s.cummax()
    max_dd = float(((s - running_max) / running_max * 100).min())
    running_min = s.cummin()
    max_gain = float(((s - running_min) / running_min * 100).max())

    return RangeStats(
        return_pct=round(float(ret), 2),
        annualized_pct=round(float(ann), 2) if ann is not None else None,
        max_drawdown=round(max_dd, 2),
        max_gain=round(max_gain, 2),
        volatility=round(vol, 2) if vol is not None else None,
    )


def _yearly_rows(merged: pd.DataFrame) -> list[YearlyRow]:
    import numpy as np

    if merged.empty:
        return []
    df = merged.copy()
    df["year"] = pd.to_datetime(df["date"]).dt.year
    rows: list[YearlyRow] = []

    for year in sorted(df["year"].unique().tolist(), reverse=True):
        ydf = df[df["year"] == year]
        if len(ydf) < 2:
            continue

        prev = df[df["year"] < year]
        prev_last_idx = prev.iloc[-1]["close_idx"] if not prev.empty else ydf.iloc[0]["close_idx"]
        prev_last_bm = prev.iloc[-1]["close_bm"] if not prev.empty else ydf.iloc[0]["close_bm"]
        end_idx = ydf.iloc[-1]["close_idx"]
        end_bm = ydf.iloc[-1]["close_bm"]

        def stats(closes_list):
            s = pd.Series(closes_list).astype(float)
            dr = s.pct_change().dropna()
            vol = float(dr.std() * np.sqrt(252) * 100) if len(dr) > 1 else None
            running_max = s.cummax()
            max_dd = float(((s - running_max) / running_max * 100).min())
            running_min = s.cummin()
            max_gain = float(((s - running_min) / running_min * 100).max())
            return vol, max_dd, max_gain

        idx_series = [prev_last_idx] + ydf["close_idx"].tolist() if not prev.empty else ydf["close_idx"].tolist()
        bm_series = [prev_last_bm] + ydf["close_bm"].tolist() if not prev.empty else ydf["close_bm"].tolist()
        idx_vol, idx_dd, idx_gain = stats(idx_series)
        bm_vol, bm_dd, bm_gain = stats(bm_series)

        rows.append(
            YearlyRow(
                year=int(year),
                index_return=round(float((end_idx / prev_last_idx - 1) * 100), 2),
                benchmark_return=round(float((end_bm / prev_last_bm - 1) * 100), 2),
                index_volatility=round(idx_vol, 2) if idx_vol is not None else None,
                benchmark_volatility=round(bm_vol, 2) if bm_vol is not None else None,
                index_max_drawdown=round(idx_dd, 2),
                benchmark_max_drawdown=round(bm_dd, 2),
                index_max_gain=round(idx_gain, 2),
                benchmark_max_gain=round(bm_gain, 2),
            )
        )

    return rows
