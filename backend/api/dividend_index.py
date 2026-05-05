"""API endpoints for the dividend-index dashboard."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.config import BENCHMARKS, DIVIDEND_INDICES, get_benchmark, get_index
from backend.data import akshare_client as ak_client
from backend.data import us_client
from backend.schemas import (
    BenchmarkCompare,
    BenchmarkMeta,
    ComparePoint,
    CompareSeries,
    Constituents,
    ConstituentItem,
    IndexMeta,
    Overview,
    RangeStats,
    TimeSeriesPoint,
    ValuationSeries,
    YearlyRow,
    YieldSpreadSeries,
)

router = APIRouter(prefix="/api/dividend", tags=["dividend-index"])


@router.get("/indices", response_model=list[IndexMeta])
def list_indices() -> list[IndexMeta]:
    return [
        IndexMeta(
            code=c.code,
            name=c.name,
            full_name=c.full_name,
            exchange=c.exchange,
            description=c.description,
            supports_long_history_pe=c.lg_symbol is not None,
        )
        for c in DIVIDEND_INDICES.values()
    ]


@router.get("/indices/{code}/overview", response_model=Overview)
def get_overview(code: str) -> Overview:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        return _get_us_overview(cfg)

    price = ak_client.index_daily_price(cfg.tx_symbol)
    last = price.iloc[-1]
    prev = price.iloc[-2] if len(price) >= 2 else None
    close = float(last["close"])
    change_pct = (
        (close / float(prev["close"]) - 1) * 100 if prev is not None else None
    )

    # Valuation snapshot — csindex is most authoritative
    pe_ttm = pe_static = div_yield = None
    try:
        val = ak_client.index_valuation_csindex(cfg.csindex_symbol)
        if not val.empty:
            vlast = val.iloc[-1]
            pe_ttm = _to_float(vlast.get("pe_ttm"))
            pe_static = _to_float(vlast.get("pe_static"))
            div_yield = _to_float(vlast.get("dividend_yield"))
    except Exception:
        pass

    # Yield spread vs 10Y
    yield_spread = None
    try:
        bond = ak_client.china_treasury_10y()
        if not bond.empty and div_yield is not None:
            yld_10y = float(bond.iloc[-1]["yield_10y"])
            yield_spread = div_yield - yld_10y
    except Exception:
        pass

    # PE percentiles across multiple lookback windows — csindex hist is the
    # authoritative long-history source and works for all our niche indices.
    pe_pct: dict[str, float | None] = {k: None for k in ("1y", "3y", "5y", "10y", "all")}
    pe_history_start: str | None = None
    try:
        pe_hist_df = ak_client.index_pe_history_csindex(cfg.csindex_symbol)
        if not pe_hist_df.empty and pe_ttm is not None:
            pe_pct = _pe_percentiles_by_window(pe_hist_df, pe_ttm)
            pe_history_start = str(pe_hist_df.iloc[0]["date"])
    except Exception:
        pass

    # Dividend-yield percentile — long history derived from price+TR indices
    # (falls back to csindex 20-day window if no TR counterpart is configured).
    div_pct: dict[str, float | None] = {k: None for k in ("1y", "3y", "5y", "10y", "all")}
    dy_history_start: str | None = None
    if cfg.tr_csindex_symbol and div_yield is not None:
        try:
            dy_hist_df = ak_client.index_dividend_yield_history(
                cfg.csindex_symbol, cfg.tr_csindex_symbol
            )
            if not dy_hist_df.empty:
                # Rank the derived *current* value (for self-consistency with its
                # own distribution), not the csindex snapshot, whose methodology
                # differs slightly.
                current_derived = float(dy_hist_df.iloc[-1]["dividend_yield"])
                div_pct = _dy_percentiles_by_window(dy_hist_df, current_derived)
                dy_history_start = str(dy_hist_df.iloc[0]["date"])
        except Exception:
            pass
    if all(v is None for v in div_pct.values()):
        # Fallback: csindex 20-day snapshot (better than nothing for 931233)
        try:
            val_hist = ak_client.index_valuation_csindex(cfg.csindex_symbol)
            if not val_hist.empty and div_yield is not None:
                rank = _percentile_rank(val_hist["dividend_yield"].dropna(), div_yield)
                div_pct = {"1y": None, "3y": None, "5y": None, "10y": None, "all": rank}
        except Exception:
            pass

    return Overview(
        code=cfg.code,
        name=cfg.name,
        as_of=str(last["date"]),
        close=close,
        change_pct=change_pct,
        pe_ttm=pe_ttm,
        pe_static=pe_static,
        dividend_yield=div_yield,
        yield_spread_bps=yield_spread,
        dividend_yield_percentile=div_pct,
        dividend_yield_history_start=dy_history_start,
        pe_percentile=pe_pct,
        pe_history_start=pe_history_start,
    )


@router.get("/indices/{code}/price-history")
def get_price_history(
    code: str,
    years: int = Query(default=10, ge=1, le=25),
) -> dict:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        df = us_client.fetch_asset_history(cfg.tx_symbol, years=years)
        return {"code": cfg.code, "points": df.to_dict(orient="records")}
    df = ak_client.index_daily_price(cfg.tx_symbol)
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
    df = df[df["date"] >= cutoff]
    return {
        "code": cfg.code,
        "points": df.to_dict(orient="records"),
    }


@router.get("/benchmarks", response_model=list[BenchmarkMeta])
def list_benchmarks() -> list[BenchmarkMeta]:
    return [BenchmarkMeta(code=b.code, name=b.name) for b in BENCHMARKS.values()]


@router.get("/indices/{code}/benchmark-compare", response_model=BenchmarkCompare)
def get_benchmark_compare(
    code: str,
    benchmark: str = Query(default="000300"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> BenchmarkCompare:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        benchmark = "SPY" if benchmark not in BENCHMARKS else benchmark
        return _get_us_benchmark_compare(cfg, benchmark, start, end)
    try:
        bcfg = get_benchmark(benchmark)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unsupported benchmark: {benchmark}")

    idx_df = ak_client.index_daily_price(cfg.tx_symbol)[["date", "close"]]
    bm_df = ak_client.index_daily_price(bcfg.tx_symbol)[["date", "close"]]

    # Align on intersection of trading days (handles holiday differences)
    merged = pd.merge(idx_df, bm_df, on="date", how="inner", suffixes=("_idx", "_bm"))
    merged = merged.sort_values("date").reset_index(drop=True)

    if merged.empty:
        raise HTTPException(status_code=500, detail="No overlapping data for index & benchmark")

    if start:
        merged = merged[merged["date"] >= start]
    if end:
        merged = merged[merged["date"] <= end]

    if merged.empty:
        raise HTTPException(status_code=400, detail="No data in selected range")

    actual_start = str(merged.iloc[0]["date"])
    actual_end = str(merged.iloc[-1]["date"])

    idx_closes = merged["close_idx"].astype(float).values
    bm_closes = merged["close_bm"].astype(float).values
    dates = merged["date"].tolist()

    idx_points = [ComparePoint(date=d, close=float(c)) for d, c in zip(dates, idx_closes)]
    bm_points = [ComparePoint(date=d, close=float(c)) for d, c in zip(dates, bm_closes)]

    return BenchmarkCompare(
        start=actual_start,
        end=actual_end,
        index=CompareSeries(
            code=cfg.code,
            name=cfg.name,
            points=idx_points,
            stats=_range_stats(idx_closes, dates),
        ),
        benchmark=CompareSeries(
            code=bcfg.code,
            name=bcfg.name,
            points=bm_points,
            stats=_range_stats(bm_closes, dates),
        ),
        yearly=_yearly_rows(merged),
    )


@router.get("/indices/{code}/valuation-history", response_model=ValuationSeries)
def get_valuation_history(
    code: str,
    years: int = Query(default=10, ge=1, le=25),
) -> ValuationSeries:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        return _get_us_valuation_history(cfg, years)
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    pe_ttm_pts: list[TimeSeriesPoint] = []
    pe_static_pts: list[TimeSeriesPoint] = []
    pb_pts: list[TimeSeriesPoint] = []
    div_pts: list[TimeSeriesPoint] = []

    # Long-history PE TTM from csindex perf endpoint (all our indices)
    try:
        pe_df = ak_client.index_pe_history_csindex(cfg.csindex_symbol)
        pe_df = pe_df[pe_df["date"] >= cutoff]
        pe_ttm_pts = _to_series(pe_df, "date", "pe_ttm")
    except Exception:
        pass

    # legulegu supplements pe_static/pb if the index is supported
    if cfg.lg_symbol:
        try:
            lg_df = ak_client.index_pe_history_lg(cfg.lg_symbol)
            lg_df = lg_df[lg_df["date"] >= cutoff]
            pe_static_pts = _to_series(lg_df, "date", "pe_static")
            if not pe_ttm_pts:
                pe_ttm_pts = _to_series(lg_df, "date", "pe_ttm")
        except Exception:
            pass
        try:
            pb_df = ak_client.index_pb_history_lg(cfg.lg_symbol)
            pb_df = pb_df[pb_df["date"] >= cutoff]
            pb_pts = _to_series(pb_df, "date", "pb")
        except Exception:
            pass

    # Dividend yield — long-history from derived TR series; fallback to csindex snapshot
    if cfg.tr_csindex_symbol:
        try:
            dy_df = ak_client.index_dividend_yield_history(
                cfg.csindex_symbol, cfg.tr_csindex_symbol
            )
            dy_df = dy_df[dy_df["date"] >= cutoff]
            div_pts = _to_series(dy_df, "date", "dividend_yield")
        except Exception:
            pass
    if not div_pts:
        try:
            v_df = ak_client.index_valuation_csindex(cfg.csindex_symbol)
            v_df = v_df[v_df["date"] >= cutoff]
            div_pts = _to_series(v_df, "date", "dividend_yield")
            if not pe_static_pts:
                pe_static_pts = _to_series(v_df, "date", "pe_static")
        except Exception:
            pass

    return ValuationSeries(
        code=cfg.code,
        pe_ttm=pe_ttm_pts,
        pe_static=pe_static_pts,
        dividend_yield=div_pts,
        pb=pb_pts,
    )


@router.get("/indices/{code}/yield-spread", response_model=YieldSpreadSeries)
def get_yield_spread(
    code: str,
    years: int = Query(default=10, ge=1, le=25),
) -> YieldSpreadSeries:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        return _get_us_yield_spread(cfg, years)
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    bond = ak_client.china_treasury_10y()
    bond = bond[bond["date"] >= cutoff]

    points: list[dict] = []
    try:
        # Prefer derived long-history DY; fall back to csindex 20-day snapshot
        if cfg.tr_csindex_symbol:
            dy_df = ak_client.index_dividend_yield_history(
                cfg.csindex_symbol, cfg.tr_csindex_symbol
            )
            dy_df = dy_df[dy_df["date"] >= cutoff].rename(
                columns={"dividend_yield": "dividend_yield"}
            )
        else:
            v_df = ak_client.index_valuation_csindex(cfg.csindex_symbol)
            dy_df = v_df[v_df["date"] >= cutoff][["date", "dividend_yield"]].copy()

        merged = pd.merge(dy_df, bond, on="date", how="inner")
        for _, row in merged.iterrows():
            dy = _to_float(row.get("dividend_yield"))
            y10 = _to_float(row.get("yield_10y"))
            if dy is None or y10 is None:
                continue
            points.append({
                "date": row["date"],
                "dividend_yield": dy,
                "yield_10y": y10,
                "spread": dy - y10,
            })
    except Exception:
        pass

    return YieldSpreadSeries(code=cfg.code, points=points)


@router.get("/indices/{code}/constituents", response_model=Constituents)
def get_constituents(code: str, limit: int = Query(default=30, ge=1, le=200)) -> Constituents:
    cfg = _get_or_404(code)
    if _is_us_dividend(cfg):
        return _get_us_constituents(cfg)
    df = ak_client.index_constituents(cfg.csindex_symbol)
    # sort by weight if present
    if df["weight"].notna().any():
        df = df.sort_values("weight", ascending=False)
    total = len(df)
    df = df.head(limit)
    as_of = df.iloc[0]["date"] if not df.empty else ""
    items = [
        ConstituentItem(
            stock_code=row["stock_code"],
            stock_name=row["stock_name"],
            exchange=row["exchange"],
            weight=_to_float(row.get("weight")),
        )
        for _, row in df.iterrows()
    ]
    return Constituents(code=cfg.code, as_of=str(as_of), total=total, items=items)


# ----------------------------- US dividend ETF --------------------------

def _is_us_dividend(cfg) -> bool:
    return cfg.exchange == "us"


def _get_us_overview(cfg) -> Overview:
    hist = us_client.fetch_asset_history(cfg.tx_symbol, years=2)
    fundamentals = us_client.fetch_fundamentals(cfg.tx_symbol)
    close = change_pct = None
    as_of = pd.Timestamp.today().strftime("%Y-%m-%d")
    if not hist.empty:
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else None
        close = _to_float(last.get("close"))
        as_of = str(last.get("date"))
        if close is not None and prev is not None:
            prev_close = _to_float(prev.get("close"))
            change_pct = round((close / prev_close - 1) * 100, 2) if prev_close else None

    dividend_yield = _to_float(fundamentals.get("dividend_yield_pct"))
    pe_ttm = _to_float(fundamentals.get("pe_ttm"))
    pe_pct = {k: None for k in ("1y", "3y", "5y", "10y", "all")}
    div_pct = {k: None for k in ("1y", "3y", "5y", "10y", "all")}

    yield_spread = None
    try:
        macro = us_client.fetch_macro()
        us_10y = _to_float(macro.get("us_10y"))
        if dividend_yield is not None and us_10y is not None:
            yield_spread = dividend_yield - us_10y
    except Exception:
        pass

    return Overview(
        code=cfg.code,
        name=cfg.name,
        as_of=as_of,
        close=close,
        change_pct=change_pct,
        pe_ttm=pe_ttm,
        pe_static=None,
        dividend_yield=dividend_yield,
        yield_spread_bps=yield_spread,
        dividend_yield_percentile=div_pct,
        dividend_yield_history_start=None,
        pe_percentile=pe_pct,
        pe_history_start=None,
    )


def _get_us_benchmark_compare(
    cfg,
    benchmark: str,
    start: str | None,
    end: str | None,
) -> BenchmarkCompare:
    try:
        bcfg = get_benchmark(benchmark)
    except KeyError:
        bcfg = get_benchmark("SPY")

    idx_df = us_client.fetch_index_history(cfg.tx_symbol, years=25)[["date", "close"]]
    bm_df = us_client.fetch_index_history(bcfg.tx_symbol, years=25)[["date", "close"]]
    merged = pd.merge(idx_df, bm_df, on="date", how="inner", suffixes=("_idx", "_bm"))
    merged = merged.sort_values("date").reset_index(drop=True)
    if start:
        merged = merged[merged["date"] >= start]
    if end:
        merged = merged[merged["date"] <= end]
    if merged.empty:
        raise HTTPException(status_code=500, detail="No overlapping US ETF data")

    dates = merged["date"].tolist()
    idx_closes = merged["close_idx"].astype(float).values
    bm_closes = merged["close_bm"].astype(float).values
    return BenchmarkCompare(
        start=str(merged.iloc[0]["date"]),
        end=str(merged.iloc[-1]["date"]),
        index=CompareSeries(
            code=cfg.code,
            name=cfg.name,
            points=[ComparePoint(date=d, close=float(c)) for d, c in zip(dates, idx_closes)],
            stats=_range_stats(idx_closes, dates),
        ),
        benchmark=CompareSeries(
            code=bcfg.code,
            name=bcfg.name,
            points=[ComparePoint(date=d, close=float(c)) for d, c in zip(dates, bm_closes)],
            stats=_range_stats(bm_closes, dates),
        ),
        yearly=_yearly_rows(merged),
    )


def _get_us_valuation_history(cfg, years: int) -> ValuationSeries:
    fundamentals = us_client.fetch_fundamentals(cfg.tx_symbol)
    hist = us_client.fetch_asset_history(cfg.tx_symbol, years=years)
    if hist.empty:
        return ValuationSeries(code=cfg.code, pe_ttm=[], pe_static=[], dividend_yield=[], pb=[])
    dividend_yield = _to_float(fundamentals.get("dividend_yield_pct"))
    pe_ttm = _to_float(fundamentals.get("pe_ttm"))
    pb = _to_float(fundamentals.get("pb"))
    dates = hist["date"].tolist()
    return ValuationSeries(
        code=cfg.code,
        pe_ttm=[TimeSeriesPoint(date=d, value=pe_ttm) for d in dates] if pe_ttm is not None else [],
        pe_static=[],
        dividend_yield=(
            [TimeSeriesPoint(date=d, value=dividend_yield) for d in dates]
            if dividend_yield is not None
            else []
        ),
        pb=[TimeSeriesPoint(date=d, value=pb) for d in dates] if pb is not None else [],
    )


def _get_us_yield_spread(cfg, years: int) -> YieldSpreadSeries:
    hist = us_client.fetch_asset_history(cfg.tx_symbol, years=years)
    fundamentals = us_client.fetch_fundamentals(cfg.tx_symbol)
    dividend_yield = _to_float(fundamentals.get("dividend_yield_pct"))
    if hist.empty or dividend_yield is None:
        return YieldSpreadSeries(code=cfg.code, points=[])
    try:
        macro = us_client.fetch_macro()
        us_10y = _to_float(macro.get("us_10y"))
    except Exception:
        us_10y = None
    if us_10y is None:
        return YieldSpreadSeries(code=cfg.code, points=[])
    points = [
        {
            "date": row["date"],
            "dividend_yield": dividend_yield,
            "yield_10y": us_10y,
            "spread": dividend_yield - us_10y,
        }
        for _, row in hist.iterrows()
    ]
    return YieldSpreadSeries(code=cfg.code, points=points)


def _get_us_constituents(cfg) -> Constituents:
    items = [
        ConstituentItem(stock_code="SCHD", stock_name=cfg.full_name, exchange="US", weight=100.0)
    ]
    return Constituents(
        code=cfg.code,
        as_of=pd.Timestamp.today().strftime("%Y-%m-%d"),
        total=1,
        items=items,
    )


# ----------------------------- helpers ---------------------------------

def _get_or_404(code: str):
    try:
        return get_index(code)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unsupported index: {code}")


def _to_float(v) -> float | None:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except Exception:
        return None


def _to_series(df: pd.DataFrame, date_col: str, value_col: str) -> list[TimeSeriesPoint]:
    if value_col not in df.columns:
        return []
    out: list[TimeSeriesPoint] = []
    for _, row in df.iterrows():
        v = _to_float(row[value_col])
        out.append(TimeSeriesPoint(date=row[date_col], value=v))
    return out


def _range_stats(closes, dates) -> RangeStats:
    import numpy as np

    closes = list(closes)
    if len(closes) < 2:
        return RangeStats(
            return_pct=None, annualized_pct=None,
            max_drawdown=None, max_gain=None, volatility=None,
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
    dd = (s - running_max) / running_max * 100
    max_dd = float(dd.min())

    running_min = s.cummin()
    gains = (s - running_min) / running_min * 100
    max_g = float(gains.max())

    return RangeStats(
        return_pct=round(float(ret), 2),
        annualized_pct=round(float(ann), 2) if ann is not None else None,
        max_drawdown=round(max_dd, 2),
        max_gain=round(max_g, 2),
        volatility=round(vol, 2) if vol is not None else None,
    )


def _yearly_rows(merged: pd.DataFrame) -> list[YearlyRow]:
    import numpy as np

    if merged.empty:
        return []
    df = merged.copy()
    df["year"] = pd.to_datetime(df["date"]).dt.year
    years_sorted = sorted(df["year"].unique().tolist(), reverse=True)

    rows: list[YearlyRow] = []
    for y in years_sorted:
        ydf = df[df["year"] == y]
        if len(ydf) < 2:
            continue

        # Start reference: previous year's last close if available
        prev = df[df["year"] < y]
        prev_last_idx = prev.iloc[-1]["close_idx"] if not prev.empty else ydf.iloc[0]["close_idx"]
        prev_last_bm = prev.iloc[-1]["close_bm"] if not prev.empty else ydf.iloc[0]["close_bm"]
        end_idx = ydf.iloc[-1]["close_idx"]
        end_bm = ydf.iloc[-1]["close_bm"]

        def stats(closes_list):
            s = pd.Series(closes_list).astype(float)
            dr = s.pct_change().dropna()
            vol = float(dr.std() * np.sqrt(252) * 100) if len(dr) > 1 else None
            rm = s.cummax()
            dd = float(((s - rm) / rm * 100).min())
            rn = s.cummin()
            mg = float(((s - rn) / rn * 100).max())
            return vol, dd, mg

        idx_series = [prev_last_idx] + ydf["close_idx"].tolist() if not prev.empty else ydf["close_idx"].tolist()
        bm_series = [prev_last_bm] + ydf["close_bm"].tolist() if not prev.empty else ydf["close_bm"].tolist()
        ivol, idd, img = stats(idx_series)
        bvol, bdd, bmg = stats(bm_series)

        rows.append(YearlyRow(
            year=int(y),
            index_return=round(float((end_idx / prev_last_idx - 1) * 100), 2),
            benchmark_return=round(float((end_bm / prev_last_bm - 1) * 100), 2),
            index_volatility=round(ivol, 2) if ivol is not None else None,
            benchmark_volatility=round(bvol, 2) if bvol is not None else None,
            index_max_drawdown=round(idd, 2),
            benchmark_max_drawdown=round(bdd, 2),
            index_max_gain=round(img, 2),
            benchmark_max_gain=round(bmg, 2),
        ))
    return rows


_WINDOW_YEARS: dict[str, int | None] = {
    "1y": 1,
    "3y": 3,
    "5y": 5,
    "10y": 10,
    "all": None,
}


def _percentiles_by_window(
    df: pd.DataFrame, col: str, current: float
) -> dict[str, float | None]:
    """Generic multi-window percentile rank helper.

    df must be sorted ascending by 'date' and contain ``col``.
    Requires ≥100 samples in a window; returns None otherwise.
    """
    today = pd.Timestamp.today()
    out: dict[str, float | None] = {}
    for key, years in _WINDOW_YEARS.items():
        if years is None:
            window = df
        else:
            cutoff = (today - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
            window = df[df["date"] >= cutoff]
        series = window[col].dropna()
        out[key] = _percentile_rank(series, current) if len(series) >= 100 else None
    return out


def _pe_percentiles_by_window(pe_df: pd.DataFrame, current: float) -> dict[str, float | None]:
    return _percentiles_by_window(pe_df, "pe_ttm", current)


def _dy_percentiles_by_window(dy_df: pd.DataFrame, current: float) -> dict[str, float | None]:
    return _percentiles_by_window(dy_df, "dividend_yield", current)


def _percentile_rank(series: pd.Series, value: float) -> float:
    """Return 0-100 percentile rank of ``value`` against ``series``.

    Lower rank = cheaper (for PE) or lower (for yield, meaning expensive).
    """
    if series.empty:
        return 0.0
    rank = (series <= value).mean() * 100
    return round(float(rank), 2)
