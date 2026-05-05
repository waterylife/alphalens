"""Pydantic models for the portfolio API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Holding(BaseModel):
    id: int
    market: str
    asset_class: str
    tag_l1: str | None
    tag_l2: str | None
    name: str
    code: str | None
    currency: str
    current_price: float | None
    cost_price: float | None
    quantity: float | None
    cost_value_cny: float
    market_value_cny: float
    unrealized_pnl_cny: float | None
    return_pct: float | None
    broker: str
    weight: float = Field(description="Weight in total portfolio market value, 0–1")
    as_of: str


class FxSnapshot(BaseModel):
    pair: str
    rate: float
    as_of: str


class AllocationBucket(BaseModel):
    key: str
    market_value_cny: float
    weight: float


class Summary(BaseModel):
    total_market_value_cny: float
    total_cost_value_cny: float
    total_unrealized_pnl_cny: float
    total_return_pct: float | None
    n_positions: int
    last_updated: str | None
    fx_rates: list[FxSnapshot]
    by_market: list[AllocationBucket]
    by_asset_class: list[AllocationBucket]
    by_tag_l1: list[AllocationBucket]
    by_broker: list[AllocationBucket]


class SyncRun(BaseModel):
    id: int
    source: str
    started_at: str
    finished_at: str | None
    status: str
    n_rows: int | None
    error_msg: str | None


class SyncResult(BaseModel):
    id: int
    status: str
    n_inserted: int
    n_updated: int
    fx_rates: dict[str, float]


class ScreenshotRow(BaseModel):
    name: str
    code: str | None = None
    quantity: float | None = None
    cost_price: float | None = None
    current_price: float | None = None
    market_value: float | None = None
    cost_value: float | None = None
    unrealized_pnl: float | None = None
    return_pct: float | None = None
    currency: str = "CNY"


class ScreenshotParseResult(BaseModel):
    rows: list[ScreenshotRow]
    warnings: list[str]


class ImportRow(BaseModel):
    """A row the user has reviewed and is ready to commit."""
    market: str
    asset_class: str
    tag_l1: str | None = None
    tag_l2: str | None = None
    name: str
    code: str | None = None
    currency: str = "CNY"
    quantity: float | None = None
    cost_price: float | None = None
    current_price: float | None = None
    market_value_cny: float
    cost_value_cny: float | None = None
    unrealized_pnl_cny: float | None = None
    return_pct: float | None = None


class ImportRequest(BaseModel):
    broker: str = Field(description="天天基金 / 东方财富 / 蚂蚁财富 / etc.")
    rows: list[ImportRow]


class ImportResult(BaseModel):
    id: int
    status: str
    n_inserted: int
    n_updated: int


class TiantianBrowserRow(BaseModel):
    name: str
    code: str
    quantity: float
    cost_price: float = Field(description="摊薄单价 / 成本价")


class TiantianBrowserImportRequest(BaseModel):
    rows: list[TiantianBrowserRow]


class TagsConfig(BaseModel):
    tag_l1: list[str]
    tag_l2: list[str]


class RefreshPricesResult(BaseModel):
    id: int
    status: str
    n_updated: int
    n_no_quote: int
    n_skipped: int
    skipped_examples: list[str]
    fx_rates: dict[str, float]


class HoldingTagPatch(BaseModel):
    tag_l1: str | None = None
    tag_l2: str | None = None


class PortfolioTarget(BaseModel):
    id: int
    category_l1: str
    category_l2: str
    target_weight_pct: float
    target_market_value_cny: float | None = None
    role_positioning: str | None = None
    expected_asset_return_pct: float | None = None
    expected_total_return_pct: float | None = None
    optimistic_asset_return_pct: float | None = None
    optimistic_total_return_pct: float | None = None
    pessimistic_asset_return_pct: float | None = None
    pessimistic_total_return_pct: float | None = None
    sort_order: int = 0
    updated_at: str


class PortfolioTargetInput(BaseModel):
    id: int | None = None
    category_l1: str
    category_l2: str
    target_weight_pct: float
    target_market_value_cny: float | None = None
    role_positioning: str | None = None
    expected_asset_return_pct: float | None = None
    expected_total_return_pct: float | None = None
    optimistic_asset_return_pct: float | None = None
    optimistic_total_return_pct: float | None = None
    pessimistic_asset_return_pct: float | None = None
    pessimistic_total_return_pct: float | None = None
    sort_order: int = 0


class PortfolioTargetsUpdate(BaseModel):
    rows: list[PortfolioTargetInput]


class PortfolioTargetActual(BaseModel):
    target_id: int
    category_l1: str
    category_l2: str
    target_weight_pct: float
    actual_weight_pct: float
    gap_pct: float
    target_market_value_cny: float | None
    actual_market_value_cny: float
    gap_market_value_cny: float | None


class PortfolioTargetAnalysis(BaseModel):
    as_of: str
    provider: str
    total_market_value_cny: float
    conclusion: str
    actuals: list[PortfolioTargetActual]
