"""API endpoints for US tech dashboard (yfinance-backed, Futu US optional)."""

from __future__ import annotations

import datetime as dt
import concurrent.futures

from fastapi import APIRouter, Query

from backend.data import us_client
from backend.data_platform.models import AssetIdentity
from backend.data_platform.service import market_data_service
from backend.strategy import us_signals
from backend.schemas import (
    USStockSnapshot, USStockReturn, USStockFundamental, USStockTechnical,
    USMacro, USSectorFlow, USSectorRow, USIndexChart, USIndexChartPoint,
    USStockSearchResult, USStrategySignal, USStrategyComponents,
)

router = APIRouter(prefix="/api/us", tags=["us-tech"])

DEFAULT = us_client.DEFAULT_US_TICKERS


@router.get("/stocks/defaults", response_model=list[str])
def get_defaults() -> list[str]:
    return DEFAULT


@router.get("/stocks/snapshot", response_model=list[USStockSnapshot])
def get_snapshot(
    tickers: str = Query(default=",".join(DEFAULT)),
) -> list[USStockSnapshot]:
    tl = [us_client.normalize_us(t) for t in tickers.split(",") if t.strip()]
    as_of = dt.date.today().isoformat()
    out = []
    for t in tl:
        quote = market_data_service.get_quote(
            AssetIdentity(asset_type="stock", market="US", code=t, currency="USD")
        )
        out.append(USStockSnapshot(
            ticker=t, name=quote.data.name, price=quote.data.price,
            change_pct=quote.data.change_pct, volume_usd_mn=quote.data.volume_mn,
            as_of=quote.data.as_of or as_of,
        ))
    return out


@router.get("/stocks/returns", response_model=list[USStockReturn])
def get_returns(
    tickers: str = Query(default=",".join(DEFAULT)),
) -> list[USStockReturn]:
    tl = [us_client.normalize_us(t) for t in tickers.split(",") if t.strip()]

    def one(t: str) -> USStockReturn:
        try:
            result = market_data_service.get_returns(
                AssetIdentity(asset_type="stock", market="US", code=t, currency="USD")
            )
            return USStockReturn(**result.to_dict()["data"])
        except Exception:
            return USStockReturn(ticker=t)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, t): t for t in tl}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(tl)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/stocks/fundamentals", response_model=list[USStockFundamental])
def get_fundamentals(
    tickers: str = Query(default=",".join(DEFAULT)),
) -> list[USStockFundamental]:
    tl = [us_client.normalize_us(t) for t in tickers.split(",") if t.strip()]

    def one(t: str) -> USStockFundamental:
        try:
            result = market_data_service.get_fundamentals(
                AssetIdentity(asset_type="stock", market="US", code=t, currency="USD")
            )
            return USStockFundamental(**result.to_dict()["data"])
        except Exception:
            return USStockFundamental(ticker=t)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, t): t for t in tl}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(tl)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/stocks/technicals", response_model=list[USStockTechnical])
def get_technicals(
    tickers: str = Query(default=",".join(DEFAULT)),
) -> list[USStockTechnical]:
    tl = [us_client.normalize_us(t) for t in tickers.split(",") if t.strip()]

    def one(t: str) -> USStockTechnical:
        try:
            result = market_data_service.get_technicals(
                AssetIdentity(asset_type="stock", market="US", code=t, currency="USD")
            )
            return USStockTechnical(**result.to_dict()["data"])
        except Exception:
            return USStockTechnical(ticker=t)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, t): t for t in tl}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(tl)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/stocks/search", response_model=list[USStockSearchResult])
def search_stocks(q: str = Query(min_length=1)) -> list[USStockSearchResult]:
    return [USStockSearchResult(**r) for r in us_client.search_us_tickers(q)]


@router.get("/market/macro", response_model=USMacro)
def get_macro() -> USMacro:
    return USMacro(**us_client.fetch_macro())


@router.get("/market/sector-flow", response_model=USSectorFlow)
def get_sector_flow() -> USSectorFlow:
    d = us_client.fetch_sector_flow()
    return USSectorFlow(
        items=[USSectorRow(**r) for r in d.get("items", [])],
        as_of=d.get("as_of", dt.date.today().isoformat()),
    )


@router.get("/stocks/signals", response_model=list[USStrategySignal])
def get_signals(
    tickers: str = Query(default=",".join(DEFAULT)),
) -> list[USStrategySignal]:
    tl = [us_client.normalize_us(t) for t in tickers.split(",") if t.strip()]
    try:
        macro = us_client.fetch_macro()
    except Exception:
        macro = None

    def one(t: str) -> USStrategySignal:
        try:
            d = us_signals.compute_signal_with_rationale(t, macro)
            comps = d.get("components") or {}
            return USStrategySignal(
                ticker=d.get("ticker", t),
                action=d.get("action", "hold"),
                score=d.get("score"),
                components=USStrategyComponents(**comps),
                triggers=d.get("triggers") or [],
                explanation=d.get("explanation"),
            )
        except Exception:
            return USStrategySignal(
                ticker=t, action="hold", score=None,
                components=USStrategyComponents(), triggers=[], explanation=None,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, t): t for t in tl}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {t: i for i, t in enumerate(tl)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@router.get("/indices/chart", response_model=USIndexChart)
def get_index_chart(
    symbol: str = Query(default="^GSPC"),
    years: int = Query(default=1, ge=1, le=10),
) -> USIndexChart:
    df = us_client.fetch_index_history(symbol, years=years)
    if df.empty:
        return USIndexChart(symbol=symbol, points=[])
    pts = [USIndexChartPoint(date=str(r["date"]), close=float(r["close"]))
           for _, r in df.iterrows() if r["close"] == r["close"]]
    return USIndexChart(symbol=symbol, points=pts)
