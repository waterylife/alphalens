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
    dividend_yield_percentile: dict[str, float | None] = Field(
        default_factory=dict,
        description=(
            "0-100 dividend yield percentile by lookback window "
            "('1y','3y','5y','10y','all'). Higher = cheaper."
        ),
    )
    dividend_yield_history_start: str | None = Field(
        default=None,
        description="Earliest date available in the derived DY series (ISO date)",
    )
    pe_percentile: dict[str, float | None] = Field(
        default_factory=dict,
        description=(
            "0-100 PE TTM percentile rank by lookback window. "
            "Keys: '1y', '3y', '5y', '10y', 'all'. Lower = cheaper."
        ),
    )
    pe_history_start: str | None = Field(
        default=None,
        description="Earliest date available in the long-history PE series (ISO date)",
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


# ─────────────────────────── HK Tech Dashboard ───────────────────────────


class HKStockSnapshot(BaseModel):
    ticker: str
    name: str | None
    price: float | None
    change_pct: float | None = Field(description="1-day change in percent")
    pe_ttm: float | None = Field(description="Dynamic PE (TTM), None if N/A or negative")
    pb: float | None
    volume_hkd_mn: float | None = Field(description="Transaction amount today in HKD millions")
    as_of: str


class HKStockReturn(BaseModel):
    ticker: str
    ret_1m: float | None
    ret_3m: float | None
    ret_6m: float | None
    ret_12m: float | None


class HKStockSearchResult(BaseModel):
    ticker: str
    name: str


class HKIndexChartPoint(BaseModel):
    date: str
    close: float


class HKIndexChart(BaseModel):
    points: list[HKIndexChartPoint]


class HKStockTechnical(BaseModel):
    ticker: str
    rsi14: float | None = Field(description="14-day RSI, 0-100")
    dist_ma200_pct: float | None = Field(description="Percent distance of price from 200d MA")
    adtv_20d_hkd_mn: float | None = Field(description="20-day avg daily turnover in HKD millions")
    turnover_rate: float | None = Field(default=None, description="Today turnover rate %")
    volume_ratio: float | None = Field(default=None, description="量比 (today vs avg)")
    net_inflow_today_hkd_mn: float | None = Field(default=None, description="Net capital inflow today, HKD mn")
    net_inflow_5d_hkd_mn: float | None = Field(default=None, description="5-day cumulative net capital inflow, HKD mn")
    pos_52w_pct: float | None = Field(default=None, description="52-week price position percentile, 0-100")
    bid_ask_spread_bps: float | None = Field(default=None, description="Bid-ask spread in basis points")
    depth_ratio_5: float | None = Field(default=None, description="Top-5 bid volume / ask volume ratio")


class HKStockFundamental(BaseModel):
    ticker: str
    name: str | None
    pe_ttm: float | None
    forward_pe: float | None = None
    pb: float | None
    peg: float | None = None
    ps_ttm: float | None
    market_cap_hkd_bn: float | None = Field(description="Market cap in HKD billions")
    revenue_growth_pct: float | None = None
    gross_margin_pct: float | None = None
    roe_pct: float | None = None
    beta: float | None = None


class HKMarketLiquidity(BaseModel):
    vhsi: float | None = Field(description="恒生波指 VHSI")
    vhsi_change_pct: float | None
    usd_hkd: float | None = Field(description="USD/HKD spot")
    hibor_1m: float | None = Field(description="1M HIBOR in percent")
    hibor_3m: float | None
    us_10y_yield: float | None = Field(description="US 10Y treasury yield in percent")
    as_of: str


class HKSouthbound(BaseModel):
    net_inflow_mtd_hkd_bn: float | None
    net_inflow_ytd_hkd_bn: float | None
    as_of: str


class HKSectorFlowRow(BaseModel):
    ticker: str
    name: str | None = None
    today_hkd_mn: float | None = None
    d5_hkd_mn: float | None = None


class HKSectorFlow(BaseModel):
    total_today_hkd_mn: float | None
    total_5d_hkd_mn: float | None
    breakdown: list[HKSectorFlowRow]
    as_of: str


class HKETFRow(BaseModel):
    ticker: str
    name: str | None
    price: float | None
    change_pct: float | None
    volume_hkd_mn: float | None
    tracking_gap_pct: float | None = Field(default=None, description="ETF change - HSTECH change today, bps scale")


class HKETFPanel(BaseModel):
    index_change_pct: float | None
    items: list[HKETFRow]
    as_of: str


class HKStrategyComponents(BaseModel):
    valuation: float | None = None
    momentum: float | None = None
    flow: float | None = None
    liquidity: float | None = None
    macro_delta: float | None = None


class HKStrategySignal(BaseModel):
    ticker: str
    action: str = Field(description="buy / hold / sell")
    score: float | None = None
    components: HKStrategyComponents
    triggers: list[str] = Field(default_factory=list)
    explanation: str | None = None


# ─────────────────────────── US Tech Dashboard ───────────────────────────


class USStockSnapshot(BaseModel):
    ticker: str
    name: str | None = None
    price: float | None = None
    change_pct: float | None = None
    volume_usd_mn: float | None = None
    as_of: str


class USStockReturn(BaseModel):
    ticker: str
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None


class USStockFundamental(BaseModel):
    ticker: str
    name: str | None = None
    pe_ttm: float | None = None
    forward_pe: float | None = None
    peg: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    market_cap_usd_bn: float | None = None
    revenue_growth_pct: float | None = None
    gross_margin_pct: float | None = None
    roe_pct: float | None = None
    eps_ttm: float | None = None
    dividend_yield_pct: float | None = None
    beta: float | None = None


class USStockTechnical(BaseModel):
    ticker: str
    rsi14: float | None = None
    dist_ma200_pct: float | None = None
    pos_52w_pct: float | None = None
    dist_ath_pct: float | None = None
    adtv_20d_usd_mn: float | None = None
    short_pct_float: float | None = None


class USMacro(BaseModel):
    vix: float | None
    vix_change_pct: float | None
    us_10y: float | None
    us_2y: float | None
    dxy: float | None
    fed_funds_13w: float | None
    curve_2s10s_bps: float | None
    as_of: str


class USSectorRow(BaseModel):
    ticker: str
    sector: str
    price: float | None
    change_pct: float | None
    change_5d_pct: float | None
    volume_usd_mn: float | None


class USSectorFlow(BaseModel):
    items: list[USSectorRow]
    as_of: str


class USIndexChartPoint(BaseModel):
    date: str
    close: float


class USIndexChart(BaseModel):
    symbol: str
    points: list[USIndexChartPoint]


class USStockSearchResult(BaseModel):
    ticker: str
    name: str


class USStrategyComponents(BaseModel):
    valuation: float | None = None
    momentum: float | None = None
    quality: float | None = None
    risk: float | None = None
    macro_delta: float | None = None


class USStrategySignal(BaseModel):
    ticker: str
    action: str = Field(description="buy / hold / sell")
    score: float | None = Field(default=None, description="0-100 composite score")
    components: USStrategyComponents
    triggers: list[str] = Field(default_factory=list)
    explanation: str | None = None
