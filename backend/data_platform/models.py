"""Shared domain models for AlphaLens data platform."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal

AssetType = Literal["stock", "fund", "etf", "index", "cash", "bond", "unknown"]
Market = Literal["CN", "HK", "US", "FUND", "GLOBAL", "UNKNOWN"]
Freshness = Literal["realtime", "intraday", "delayed", "eod"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class AssetIdentity:
    asset_type: AssetType
    market: Market
    code: str
    currency: str | None = None
    exchange: str | None = None
    name: str | None = None

    def normalized_code(self) -> str:
        code = self.code.strip().upper()
        if self.market == "HK" and code.isdigit():
            return code.lstrip("0").zfill(5)
        if self.market in ("CN", "FUND") and code.isdigit():
            return code.zfill(6)
        if self.market == "US":
            return code.replace(".", "-")
        return code


@dataclass(frozen=True)
class Quote:
    price: float | None
    change_pct: float | None = None
    name: str | None = None
    volume_mn: float | None = None
    currency: str | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class Returns:
    ticker: str
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None


@dataclass(frozen=True)
class Technicals:
    ticker: str
    rsi14: float | None = None
    dist_ma200_pct: float | None = None
    adtv_20d_hkd_mn: float | None = None
    adtv_20d_usd_mn: float | None = None
    adtv_20d_cny_mn: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None
    net_inflow_today_hkd_mn: float | None = None
    net_inflow_5d_hkd_mn: float | None = None
    pos_52w_pct: float | None = None
    bid_ask_spread_bps: float | None = None
    depth_ratio_5: float | None = None
    dist_ath_pct: float | None = None
    short_pct_float: float | None = None


@dataclass(frozen=True)
class Fundamentals:
    ticker: str
    name: str | None = None
    pe_ttm: float | None = None
    forward_pe: float | None = None
    pb: float | None = None
    peg: float | None = None
    ps_ttm: float | None = None
    market_cap_hkd_bn: float | None = None
    market_cap_usd_bn: float | None = None
    market_cap_cny_bn: float | None = None
    revenue_growth_pct: float | None = None
    gross_margin_pct: float | None = None
    roe_pct: float | None = None
    eps_ttm: float | None = None
    dividend_yield_pct: float | None = None
    beta: float | None = None


@dataclass(frozen=True)
class OfficialFilings:
    source: str
    status: str
    company_code: str | None = None
    company_name: str | None = None
    cik: str | None = None
    official_search_url: str | None = None
    filings: list[dict[str, Any]] = field(default_factory=list)
    financial_statement_snapshots: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FundProfile:
    code: str
    name: str | None = None
    fund_type: str | None = None
    market: str | None = None
    asset_class: str | None = None
    tag_l1: str | None = None
    tag_l2: str | None = None


@dataclass(frozen=True)
class DataMeta:
    source: str
    as_of: str | None
    fetched_at: str
    freshness: Freshness
    confidence: Confidence
    verified_by: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DataResult:
    asset: AssetIdentity
    data: Any
    meta: DataMeta

    def to_dict(self) -> dict:
        data = asdict(self.data) if is_dataclass(self.data) else self.data
        return {
            "asset": {
                "asset_type": self.asset.asset_type,
                "market": self.asset.market,
                "code": self.asset.normalized_code(),
                "currency": self.asset.currency,
                "exchange": self.asset.exchange,
                "name": self.asset.name,
            },
            "data": data,
            "meta": {
                "source": self.meta.source,
                "as_of": self.meta.as_of,
                "fetched_at": self.meta.fetched_at,
                "freshness": self.meta.freshness,
                "confidence": self.meta.confidence,
                "verified_by": self.meta.verified_by,
                "warnings": self.meta.warnings,
            },
        }


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    return dt.date.today().isoformat()
