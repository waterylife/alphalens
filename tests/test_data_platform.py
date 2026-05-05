from __future__ import annotations

import pytest

from backend.data_platform.models import (
    AssetIdentity,
    FundProfile,
    Fundamentals,
    Quote,
    Returns,
)
from backend.data_platform.service import MarketDataService


class FakeQuoteProvider:
    def __init__(self, quote: Quote | None = None, *, exc: Exception | None = None, supports: bool = True):
        self.quote = quote
        self.exc = exc
        self._supports = supports

    def supports(self, asset: AssetIdentity) -> bool:
        return self._supports

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        if self.exc:
            raise self.exc
        return self.quote


class FakeReturnsProvider:
    def __init__(self, data: Returns | None):
        self.data = data

    def supports(self, asset: AssetIdentity) -> bool:
        return True

    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        return self.data


class FakeFundamentalsProvider:
    def __init__(self, data: Fundamentals | None):
        self.data = data

    def supports(self, asset: AssetIdentity) -> bool:
        return True

    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        return self.data


class FakeFundProfileProvider:
    def __init__(self, data: FundProfile | None):
        self.data = data

    def supports(self, asset: AssetIdentity) -> bool:
        return True

    def get_fund_profile(self, asset: AssetIdentity) -> FundProfile | None:
        return self.data


def test_asset_identity_normalizes_market_codes() -> None:
    assert AssetIdentity(asset_type="stock", market="HK", code="700").normalized_code() == "00700"
    assert AssetIdentity(asset_type="stock", market="CN", code="600519").normalized_code() == "600519"
    assert AssetIdentity(asset_type="fund", market="FUND", code="11961").normalized_code() == "011961"
    assert AssetIdentity(asset_type="stock", market="US", code="BRK.B").normalized_code() == "BRK-B"


def test_quote_uses_fallback_provider_when_primary_fails() -> None:
    service = MarketDataService(
        quote_providers={
            "bad": FakeQuoteProvider(exc=RuntimeError("boom")),
            "good": FakeQuoteProvider(Quote(price=477.6, currency="HKD", as_of="2026-05-05")),
        },
        returns_providers={},
        technicals_providers={},
        fundamentals_providers={},
        official_filings_providers={},
        fund_profile_providers={},
    )
    asset = AssetIdentity(asset_type="stock", market="HK", code="00700", currency="HKD")

    result = service.get_quote(asset, strategy="bad,good")

    assert result.meta.source == "good"
    assert result.data.price == 477.6
    assert result.meta.confidence == "medium"
    assert any("bad failed" in warning for warning in result.meta.warnings)


def test_quote_cross_validation_records_warning_on_large_price_gap() -> None:
    service = MarketDataService(
        quote_providers={
            "primary": FakeQuoteProvider(Quote(price=100.0, currency="USD", as_of="2026-05-05")),
            "secondary": FakeQuoteProvider(Quote(price=103.0, currency="USD", as_of="2026-05-05")),
        },
        returns_providers={},
        technicals_providers={},
        fundamentals_providers={},
        official_filings_providers={},
        fund_profile_providers={},
    )
    service.price_deviation_warn_pct = 1.0
    asset = AssetIdentity(asset_type="stock", market="US", code="AAPL", currency="USD")

    result = service.get_quote(asset, strategy="primary,secondary", verify=True)

    assert result.meta.source == "primary"
    assert result.meta.verified_by == ["secondary"]
    assert result.meta.confidence == "medium"
    assert any("secondary quote differs from primary" in warning for warning in result.meta.warnings)


def test_metric_cross_validation_compares_overlapping_numeric_fields() -> None:
    service = MarketDataService(
        quote_providers={},
        returns_providers={},
        technicals_providers={},
        fundamentals_providers={
            "primary": FakeFundamentalsProvider(
                Fundamentals(ticker="AAPL", pe_ttm=30.0, market_cap_usd_bn=3000.0)
            ),
            "secondary": FakeFundamentalsProvider(
                Fundamentals(ticker="AAPL", pe_ttm=31.0, market_cap_usd_bn=3600.0)
            ),
        },
        official_filings_providers={},
        fund_profile_providers={},
    )
    service.metric_deviation_warn_pct = 5.0
    asset = AssetIdentity(asset_type="stock", market="US", code="AAPL", currency="USD")

    result = service.get_fundamentals(asset, strategy="primary,secondary", verify=True)

    assert result.meta.source == "primary"
    assert result.meta.verified_by == ["secondary"]
    assert any("secondary.market_cap_usd_bn differs from primary" in warning for warning in result.meta.warnings)


def test_strategy_override_selects_named_provider() -> None:
    service = MarketDataService(
        quote_providers={},
        returns_providers={},
        technicals_providers={},
        fundamentals_providers={
            "a": FakeFundamentalsProvider(Fundamentals(ticker="AAPL", pb=10.0)),
            "b": FakeFundamentalsProvider(Fundamentals(ticker="AAPL", pb=12.0)),
        },
        official_filings_providers={},
        fund_profile_providers={},
    )
    asset = AssetIdentity(asset_type="stock", market="US", code="AAPL", currency="USD")

    result = service.get_fundamentals(asset, strategy="b")

    assert result.meta.source == "b"
    assert result.data.pb == 12.0


def test_fund_research_context_uses_fund_specific_providers_only() -> None:
    service = MarketDataService(
        quote_providers={
            "akshare_fund_nav": FakeQuoteProvider(
                Quote(price=1.2345, change_pct=0.1, currency="CNY", as_of="2026-05-05")
            )
        },
        returns_providers={
            "akshare_fund_nav_history": FakeReturnsProvider(Returns(ticker="011961", ret_12m=2.5))
        },
        technicals_providers={},
        fundamentals_providers={},
        official_filings_providers={},
        fund_profile_providers={
            "akshare_fund_profile": FakeFundProfileProvider(
                FundProfile(
                    code="011961",
                    name="东方臻裕债券A",
                    asset_class="债券",
                    tag_l1="纯债",
                    tag_l2="纯债-中国",
                )
            )
        },
    )
    asset = AssetIdentity(asset_type="fund", market="FUND", code="011961", currency="CNY")

    result = service.get_research_context(asset)
    data = result.data

    assert data["quote"]["data"]["price"] == 1.2345
    assert data["fund_profile"]["tag_l1"] == "纯债"
    assert data["fundamentals"] == {}
    assert data["technicals"] == {}
    assert data["official_filings"] == {}
    assert not any("No provider supports" in warning for warning in result.meta.warnings)


@pytest.mark.parametrize(
    ("asset", "expected_chain"),
    [
        (AssetIdentity(asset_type="fund", market="FUND", code="011961"), ["akshare_fund_nav"]),
        (AssetIdentity(asset_type="stock", market="CN", code="600519"), ["akshare_cn_bid_ask"]),
        (AssetIdentity(asset_type="stock", market="HK", code="00700"), ["yahoo_hk", "futu_hk"]),
        (AssetIdentity(asset_type="stock", market="HK", code="00700"), ["futu_hk", "yahoo_hk"]),
    ],
)
def test_quote_provider_chain_routes_by_market_and_freshness(asset: AssetIdentity, expected_chain: list[str]) -> None:
    service = MarketDataService(
        quote_providers={},
        returns_providers={},
        technicals_providers={},
        fundamentals_providers={},
        official_filings_providers={},
        fund_profile_providers={},
    )
    freshness = "realtime" if expected_chain[0] == "futu_hk" else "delayed"

    assert service._quote_provider_chain(asset, freshness, None) == expected_chain
