"""API endpoints for the dividend-index dashboard."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.config import DIVIDEND_INDICES, get_index
from backend.data import akshare_client as ak_client
from backend.schemas import (
    Constituents,
    ConstituentItem,
    IndexMeta,
    Overview,
    TimeSeriesPoint,
    ValuationSeries,
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

    # Percentiles — requires long history
    div_pct = pe_pct = None
    if cfg.lg_symbol:
        try:
            pe_hist = ak_client.index_pe_history_lg(cfg.lg_symbol)
            if not pe_hist.empty and pe_ttm is not None:
                pe_pct = _percentile_rank(pe_hist["pe_ttm"].dropna(), pe_ttm)
        except Exception:
            pass

    # Dividend yield percentile — use csindex history if available, else skip
    try:
        val_hist = ak_client.index_valuation_csindex(cfg.csindex_symbol)
        if not val_hist.empty and div_yield is not None:
            div_pct = _percentile_rank(val_hist["dividend_yield"].dropna(), div_yield)
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
        pe_percentile=pe_pct,
    )


@router.get("/indices/{code}/price-history")
def get_price_history(
    code: str,
    years: int = Query(default=10, ge=1, le=25),
) -> dict:
    cfg = _get_or_404(code)
    df = ak_client.index_daily_price(cfg.tx_symbol)
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
    df = df[df["date"] >= cutoff]
    return {
        "code": cfg.code,
        "points": df.to_dict(orient="records"),
    }


@router.get("/indices/{code}/valuation-history", response_model=ValuationSeries)
def get_valuation_history(
    code: str,
    years: int = Query(default=10, ge=1, le=25),
) -> ValuationSeries:
    cfg = _get_or_404(code)
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    pe_ttm_pts: list[TimeSeriesPoint] = []
    pe_static_pts: list[TimeSeriesPoint] = []
    pb_pts: list[TimeSeriesPoint] = []
    div_pts: list[TimeSeriesPoint] = []

    # Long-history PE/PB from legulegu if available
    if cfg.lg_symbol:
        try:
            pe_df = ak_client.index_pe_history_lg(cfg.lg_symbol)
            pe_df = pe_df[pe_df["date"] >= cutoff]
            pe_ttm_pts = _to_series(pe_df, "date", "pe_ttm")
            pe_static_pts = _to_series(pe_df, "date", "pe_static")
        except Exception:
            pass
        try:
            pb_df = ak_client.index_pb_history_lg(cfg.lg_symbol)
            pb_df = pb_df[pb_df["date"] >= cutoff]
            pb_pts = _to_series(pb_df, "date", "pb")
        except Exception:
            pass

    # Dividend yield from csindex (short history) — always try
    try:
        v_df = ak_client.index_valuation_csindex(cfg.csindex_symbol)
        v_df = v_df[v_df["date"] >= cutoff]
        div_pts = _to_series(v_df, "date", "dividend_yield")
        if not pe_ttm_pts:  # fallback if no legulegu history
            pe_ttm_pts = _to_series(v_df, "date", "pe_ttm")
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
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    bond = ak_client.china_treasury_10y()
    bond = bond[bond["date"] >= cutoff]

    points: list[dict] = []
    try:
        val = ak_client.index_valuation_csindex(cfg.csindex_symbol)
        val = val[val["date"] >= cutoff]
        merged = pd.merge(val, bond, on="date", how="inner")
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


def _percentile_rank(series: pd.Series, value: float) -> float:
    """Return 0-100 percentile rank of ``value`` against ``series``.

    Lower rank = cheaper (for PE) or lower (for yield, meaning expensive).
    """
    if series.empty:
        return 0.0
    rank = (series <= value).mean() * 100
    return round(float(rank), 2)
