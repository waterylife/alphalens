"""Pydantic models for API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IndexMeta(BaseModel):
    code: str
    name: str
    full_name: str
    exchange: str
    description: str
    supports_long_history_pe: bool = Field(
        description="Whether 10y+ PE history is available via legulegu"
    )


class Overview(BaseModel):
    code: str
    name: str
    as_of: str
    close: float | None
    change_pct: float | None = Field(description="1-day change in percent")
    pe_ttm: float | None
    pe_static: float | None
    dividend_yield: float | None = Field(description="Percent, e.g. 4.71 means 4.71%")
    yield_spread_bps: float | None = Field(
        description="dividend_yield - 10Y treasury yield, in percentage points"
    )
    dividend_yield_percentile: float | None = Field(
        description="0-100; current dividend yield rank against its own history"
    )
    pe_percentile: float | None = Field(
        description="0-100; current PE TTM rank against its own history (lower=cheaper)"
    )


class TimeSeriesPoint(BaseModel):
    date: str
    value: float | None


class PriceSeries(BaseModel):
    code: str
    points: list[dict]  # {date, open, high, low, close, volume}


class ValuationSeries(BaseModel):
    code: str
    pe_ttm: list[TimeSeriesPoint]
    pe_static: list[TimeSeriesPoint]
    dividend_yield: list[TimeSeriesPoint]
    pb: list[TimeSeriesPoint] = Field(default_factory=list)


class YieldSpreadSeries(BaseModel):
    code: str
    points: list[dict]  # {date, dividend_yield, yield_10y, spread}


class BenchmarkMeta(BaseModel):
    code: str
    name: str


class RangeStats(BaseModel):
    return_pct: float | None
    annualized_pct: float | None
    max_drawdown: float | None
    max_gain: float | None
    volatility: float | None


class ComparePoint(BaseModel):
    date: str
    close: float


class CompareSeries(BaseModel):
    code: str
    name: str
    points: list[ComparePoint]
    stats: RangeStats


class YearlyRow(BaseModel):
    year: int
    index_return: float | None
    benchmark_return: float | None
    index_volatility: float | None
    benchmark_volatility: float | None
    index_max_drawdown: float | None
    benchmark_max_drawdown: float | None
    index_max_gain: float | None
    benchmark_max_gain: float | None


class BenchmarkCompare(BaseModel):
    start: str
    end: str
    index: CompareSeries
    benchmark: CompareSeries
    yearly: list[YearlyRow]


class ConstituentItem(BaseModel):
    stock_code: str
    stock_name: str
    exchange: str
    weight: float | None


class Constituents(BaseModel):
    code: str
    as_of: str
    total: int
    items: list[ConstituentItem]
