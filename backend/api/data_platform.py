"""OpenAPI endpoints for AlphaLens data platform."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.data_platform.models import AssetIdentity
from backend.data_platform.service import market_data_service

router = APIRouter(prefix="/api/data", tags=["data-platform"])


class DataResponse(BaseModel):
    asset: dict
    data: dict
    meta: dict


def _asset(market: str, code: str, asset_type: str, currency: str | None) -> AssetIdentity:
    return AssetIdentity(
        asset_type=asset_type,  # type: ignore[arg-type]
        market=market.upper(),  # type: ignore[arg-type]
        code=code,
        currency=currency,
    )


@router.get("/quote", response_model=DataResponse)
def get_quote(
    market: str = Query(description="CN / HK / US / FUND / GLOBAL"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL, 011961"),
    asset_type: str = Query(default="unknown", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    freshness: str = Query(default="delayed", description="realtime / intraday / delayed / eod"),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
    verify: bool = Query(default=False, description="Cross-check with another provider when possible"),
) -> DataResponse:
    asset = _asset(market, code, asset_type, currency)
    result = market_data_service.get_quote(
        asset,
        freshness=freshness,  # type: ignore[arg-type]
        strategy=strategy,
        verify=verify,
    )
    return DataResponse(**result.to_dict())


@router.get("/returns", response_model=DataResponse)
def get_returns(
    market: str = Query(description="CN / HK / US / FUND / GLOBAL"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL"),
    asset_type: str = Query(default="stock", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
    verify: bool = Query(default=False, description="Cross-check with another provider when possible"),
) -> DataResponse:
    result = market_data_service.get_returns(_asset(market, code, asset_type, currency), strategy=strategy, verify=verify)
    return DataResponse(**result.to_dict())


@router.get("/technicals", response_model=DataResponse)
def get_technicals(
    market: str = Query(description="CN / HK / US / FUND / GLOBAL"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL"),
    asset_type: str = Query(default="stock", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
    verify: bool = Query(default=False, description="Cross-check with another provider when possible"),
) -> DataResponse:
    result = market_data_service.get_technicals(_asset(market, code, asset_type, currency), strategy=strategy, verify=verify)
    return DataResponse(**result.to_dict())


@router.get("/fundamentals", response_model=DataResponse)
def get_fundamentals(
    market: str = Query(description="CN / HK / US / FUND / GLOBAL"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL"),
    asset_type: str = Query(default="stock", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
    verify: bool = Query(default=False, description="Cross-check with another provider when possible"),
) -> DataResponse:
    result = market_data_service.get_fundamentals(_asset(market, code, asset_type, currency), strategy=strategy, verify=verify)
    return DataResponse(**result.to_dict())


@router.get("/official-filings", response_model=DataResponse)
def get_official_filings(
    market: str = Query(description="CN / HK / US"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL, 600519"),
    asset_type: str = Query(default="stock", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
) -> DataResponse:
    result = market_data_service.get_official_filings(_asset(market, code, asset_type, currency), strategy=strategy)
    return DataResponse(**result.to_dict())


@router.get("/fund-profile", response_model=DataResponse)
def get_fund_profile(
    code: str = Query(description="Fund code, e.g. 011961"),
    currency: str | None = Query(default="CNY"),
    strategy: str | None = Query(default=None, description="Comma-separated provider names for override"),
) -> DataResponse:
    result = market_data_service.get_fund_profile(
        _asset("FUND", code, "fund", currency),
        strategy=strategy,
    )
    return DataResponse(**result.to_dict())


@router.get("/research-context", response_model=DataResponse)
def get_research_context(
    market: str = Query(description="CN / HK / US / FUND / GLOBAL"),
    code: str = Query(description="Asset code, e.g. 00700, AAPL"),
    asset_type: str = Query(default="stock", description="stock / fund / etf / index / bond"),
    currency: str | None = Query(default=None),
    freshness: str = Query(default="delayed", description="realtime / intraday / delayed / eod"),
    verify: bool = Query(default=False, description="Cross-check with another provider when possible"),
) -> DataResponse:
    result = market_data_service.get_research_context(
        _asset(market, code, asset_type, currency),
        freshness=freshness,  # type: ignore[arg-type]
        verify=verify,
    )
    return DataResponse(**result.to_dict())
