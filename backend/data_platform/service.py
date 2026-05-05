"""Unified market data service with fallback and cross-source validation."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from backend.data import hk_client, us_client
from backend.data.cache import cache
from backend.data_platform.models import (
    AssetIdentity,
    Confidence,
    DataMeta,
    DataResult,
    Freshness,
    FundProfile,
    Fundamentals,
    OfficialFilings,
    Quote,
    Returns,
    Technicals,
    now_iso,
)
from backend.data_platform.providers import (
    DEFAULT_FUNDAMENTALS_PROVIDERS,
    DEFAULT_FUND_PROFILE_PROVIDERS,
    DEFAULT_OFFICIAL_FILINGS_PROVIDERS,
    DEFAULT_QUOTE_PROVIDERS,
    DEFAULT_RETURNS_PROVIDERS,
    DEFAULT_TECHNICALS_PROVIDERS,
    FundamentalsProvider,
    FundProfileProvider,
    OfficialFilingsProvider,
    QuoteProvider,
    ReturnsProvider,
    TechnicalsProvider,
)


class MarketDataService:
    def __init__(
        self,
        quote_providers: dict[str, QuoteProvider] | None = None,
        returns_providers: dict[str, ReturnsProvider] | None = None,
        technicals_providers: dict[str, TechnicalsProvider] | None = None,
        fundamentals_providers: dict[str, FundamentalsProvider] | None = None,
        official_filings_providers: dict[str, OfficialFilingsProvider] | None = None,
        fund_profile_providers: dict[str, FundProfileProvider] | None = None,
    ):
        self.quote_providers = DEFAULT_QUOTE_PROVIDERS if quote_providers is None else quote_providers
        self.returns_providers = DEFAULT_RETURNS_PROVIDERS if returns_providers is None else returns_providers
        self.technicals_providers = DEFAULT_TECHNICALS_PROVIDERS if technicals_providers is None else technicals_providers
        self.fundamentals_providers = (
            DEFAULT_FUNDAMENTALS_PROVIDERS if fundamentals_providers is None else fundamentals_providers
        )
        self.official_filings_providers = (
            DEFAULT_OFFICIAL_FILINGS_PROVIDERS
            if official_filings_providers is None
            else official_filings_providers
        )
        self.fund_profile_providers = (
            DEFAULT_FUND_PROFILE_PROVIDERS if fund_profile_providers is None else fund_profile_providers
        )
        self.price_deviation_warn_pct = float(os.environ.get("ALPHALENS_QUOTE_VERIFY_WARN_PCT", "1.0"))
        self.metric_deviation_warn_pct = float(os.environ.get("ALPHALENS_METRIC_VERIFY_WARN_PCT", "5.0"))

    def reset_quote_cache(self) -> None:
        for namespace in (
            "cn_bid_ask",
            "cn_individual_info",
            "cn_spot",
            "cn_stock_history",
            "fund_spot",
            "fund_one_nav",
            "fund_nav_history",
        ):
            cache.clear(namespace)

    def get_quote(
        self,
        asset: AssetIdentity,
        *,
        freshness: Freshness = "delayed",
        strategy: str | None = None,
        verify: bool = False,
    ) -> DataResult:
        chain = self._quote_provider_chain(asset, freshness, strategy)
        warnings: list[str] = []
        attempts: list[str] = []
        chosen: tuple[str, Quote] | None = None

        for provider_name in chain:
            provider = self.quote_providers.get(provider_name)
            if provider is None or not provider.supports(asset):
                continue
            attempts.append(provider_name)
            try:
                quote = provider.get_quote(asset)
            except Exception as exc:
                warnings.append(f"{provider_name} failed: {exc}")
                continue
            if quote and quote.price is not None:
                chosen = (provider_name, quote)
                break
            warnings.append(f"{provider_name} returned no quote")

        if chosen is None:
            return self._empty_quote(asset, freshness, attempts, warnings)

        source, quote = chosen
        verified_by: list[str] = []
        confidence: Confidence = "high" if not warnings else "medium"

        if verify:
            verification = self._verify_quote(asset, quote, source, chain)
            verified_by = verification["verified_by"]
            warnings.extend(verification["warnings"])
            confidence = verification["confidence"]

        return DataResult(
            asset=asset,
            data=quote,
            meta=DataMeta(
                source=source,
                as_of=quote.as_of,
                fetched_at=now_iso(),
                freshness=freshness,
                confidence=confidence,
                verified_by=verified_by,
                warnings=warnings,
            ),
        )

    def get_returns(self, asset: AssetIdentity, *, strategy: str | None = None, verify: bool = False) -> DataResult:
        return self._get_single_metric(
            asset,
            providers=self.returns_providers,
            chain=self._provider_chain_or_strategy(strategy, self._returns_provider_chain(asset)),
            getter=lambda provider, item: provider.get_returns(item),
            empty=Returns(ticker=asset.normalized_code()),
            freshness="eod",
            verify=verify,
        )

    def get_technicals(self, asset: AssetIdentity, *, strategy: str | None = None, verify: bool = False) -> DataResult:
        return self._get_single_metric(
            asset,
            providers=self.technicals_providers,
            chain=self._provider_chain_or_strategy(strategy, self._technicals_provider_chain(asset)),
            getter=lambda provider, item: provider.get_technicals(item),
            empty=Technicals(ticker=asset.normalized_code()),
            freshness="intraday",
            verify=verify,
        )

    def get_fundamentals(self, asset: AssetIdentity, *, strategy: str | None = None, verify: bool = False) -> DataResult:
        return self._get_single_metric(
            asset,
            providers=self.fundamentals_providers,
            chain=self._provider_chain_or_strategy(strategy, self._fundamentals_provider_chain(asset)),
            getter=lambda provider, item: provider.get_fundamentals(item),
            empty=Fundamentals(ticker=asset.normalized_code()),
            freshness="eod",
            verify=verify,
        )

    def get_official_filings(self, asset: AssetIdentity, *, strategy: str | None = None) -> DataResult:
        return self._get_single_metric(
            asset,
            providers=self.official_filings_providers,
            chain=self._provider_chain_or_strategy(strategy, self._official_filings_provider_chain(asset)),
            getter=lambda provider, item: provider.get_official_filings(item),
            empty=OfficialFilings(source="none", status="empty", company_code=asset.normalized_code()),
            freshness="eod",
        )

    def get_fund_profile(self, asset: AssetIdentity, *, strategy: str | None = None) -> DataResult:
        return self._get_single_metric(
            asset,
            providers=self.fund_profile_providers,
            chain=self._provider_chain_or_strategy(strategy, self._fund_profile_provider_chain(asset)),
            getter=lambda provider, item: provider.get_fund_profile(item),
            empty=FundProfile(code=asset.normalized_code()),
            freshness="eod",
        )

    def get_research_context(
        self,
        asset: AssetIdentity,
        *,
        freshness: Freshness = "delayed",
        verify: bool = False,
    ) -> DataResult:
        warnings: list[str] = []

        quote = self.get_quote(asset, freshness=freshness, verify=verify)
        warnings.extend(quote.meta.warnings)

        returns = self.get_returns(asset, verify=verify)
        warnings.extend(returns.meta.warnings)

        is_fund = asset.market == "FUND" or asset.asset_type in ("fund", "bond")
        fundamentals = None if is_fund else self.get_fundamentals(asset, verify=verify)
        if fundamentals:
            warnings.extend(fundamentals.meta.warnings)

        technicals = None if is_fund else self.get_technicals(asset, verify=verify)
        if technicals:
            warnings.extend(technicals.meta.warnings)

        official_filings = None if is_fund else self.get_official_filings(asset)
        if official_filings:
            warnings.extend(official_filings.meta.warnings)

        fund_profile = None
        if is_fund:
            fund_profile_result = self.get_fund_profile(asset)
            warnings.extend(fund_profile_result.meta.warnings)
            fund_profile = fund_profile_result.to_dict()["data"]

        macro_liquidity: dict[str, Any] = {}
        southbound_market_flow: dict[str, Any] = {}
        sources: dict[str, str] = {}
        limitations: list[str] = []
        if asset.market == "HK":
            macro_liquidity, southbound_market_flow, sources, limitations = self._hk_research_context(asset)
        elif asset.market == "US":
            macro_liquidity, sources, limitations = self._us_research_context(asset)
        elif asset.market == "CN":
            sources = {
                "quote_primary": (
                    f"https://quote.eastmoney.com/"
                    f"{'sh' if asset.normalized_code().startswith('6') else 'sz'}{asset.normalized_code()}.html"
                )
            }
            limitations = ["A 股数据来自东方财富/akshare 兼容接口，关键字段需与交易所公告和公司财报核验。"]

        data = {
            "symbol": asset.normalized_code(),
            "market": asset.market,
            "currency": asset.currency,
            "as_of": quote.meta.as_of,
            "quote": quote.to_dict(),
            "fundamentals": fundamentals.to_dict()["data"] if fundamentals else {},
            "returns": returns.to_dict()["data"],
            "technicals": technicals.to_dict()["data"] if technicals else {},
            "official_filings": official_filings.to_dict()["data"] if official_filings else {},
            "fund_profile": fund_profile,
            "macro_liquidity": macro_liquidity,
            "southbound_market_flow": southbound_market_flow,
            "sources": sources,
            "limitations": limitations,
        }
        return DataResult(
            asset=asset,
            data=data,
            meta=DataMeta(
                source="data_platform",
                as_of=quote.meta.as_of,
                fetched_at=now_iso(),
                freshness=freshness,
                confidence="medium" if warnings else "high",
                verified_by=quote.meta.verified_by,
                warnings=warnings,
            ),
        )

    def _get_single_metric(
        self,
        asset: AssetIdentity,
        *,
        providers: dict[str, Any],
        chain: list[str],
        getter: Callable[[Any, AssetIdentity], Any],
        empty: Any,
        freshness: Freshness,
        verify: bool = False,
    ) -> DataResult:
        warnings: list[str] = []
        attempts: list[str] = []
        chosen: tuple[str, Any] | None = None
        for provider_name in chain:
            provider = providers.get(provider_name)
            if provider is None or not provider.supports(asset):
                continue
            attempts.append(provider_name)
            try:
                data = getter(provider, asset)
            except Exception as exc:
                warnings.append(f"{provider_name} failed: {exc}")
                continue
            if data is not None:
                chosen = (provider_name, data)
                break
            warnings.append(f"{provider_name} returned no data")

        if chosen is not None:
            source, data = chosen
            verified_by: list[str] = []
            confidence: Confidence = "high" if not warnings else "medium"
            if verify:
                verification = self._verify_metric(
                    asset=asset,
                    data=data,
                    source=source,
                    chain=chain,
                    providers=providers,
                    getter=getter,
                )
                verified_by = verification["verified_by"]
                warnings.extend(verification["warnings"])
                confidence = verification["confidence"]
            return DataResult(
                asset=asset,
                data=data,
                meta=DataMeta(
                    source=source,
                    as_of=now_iso(),
                    fetched_at=now_iso(),
                    freshness=freshness,
                    confidence=confidence,
                    verified_by=verified_by,
                    warnings=warnings,
                ),
            )

        if attempts:
            warnings.append(f"No data available from providers: {', '.join(attempts)}")
        else:
            warnings.append("No provider supports this asset")
        return DataResult(
            asset=asset,
            data=empty,
            meta=DataMeta(
                source="none",
                as_of=None,
                fetched_at=now_iso(),
                freshness=freshness,
                confidence="low",
                warnings=warnings,
            ),
        )

    def _empty_quote(
        self,
        asset: AssetIdentity,
        freshness: Freshness,
        attempts: list[str],
        warnings: list[str],
    ) -> DataResult:
        msg = "No quote available"
        if attempts:
            msg += f" from providers: {', '.join(attempts)}"
        warnings = [*warnings, msg]
        return DataResult(
            asset=asset,
            data=Quote(price=None, currency=asset.currency),
            meta=DataMeta(
                source="none",
                as_of=None,
                fetched_at=now_iso(),
                freshness=freshness,
                confidence="low",
                verified_by=[],
                warnings=warnings,
            ),
        )

    def _quote_provider_chain(
        self,
        asset: AssetIdentity,
        freshness: Freshness,
        strategy: str | None,
    ) -> list[str]:
        if strategy:
            return [item.strip() for item in strategy.split(",") if item.strip()]
        if asset.market == "HK":
            if freshness == "realtime":
                return ["futu_hk", "yahoo_hk"]
            return ["yahoo_hk", "futu_hk"]
        if asset.market == "US":
            return ["yahoo_us"]
        if asset.market == "FUND" or asset.asset_type in ("fund", "bond"):
            return ["akshare_fund_nav"]
        if asset.market == "CN":
            return ["akshare_cn_bid_ask"]
        return []

    def _provider_chain_or_strategy(self, strategy: str | None, default_chain: list[str]) -> list[str]:
        if strategy:
            return [item.strip() for item in strategy.split(",") if item.strip()]
        return default_chain

    def _returns_provider_chain(self, asset: AssetIdentity) -> list[str]:
        if asset.market == "HK":
            return ["hk_history"]
        if asset.market == "US":
            return ["us_history"]
        if asset.market == "CN":
            return ["akshare_cn_history"]
        if asset.market == "FUND" or asset.asset_type in ("fund", "bond"):
            return ["akshare_fund_nav_history"]
        return []

    def _technicals_provider_chain(self, asset: AssetIdentity) -> list[str]:
        if asset.market == "HK":
            return ["hk_history_futu"]
        if asset.market == "US":
            return ["us_history"]
        if asset.market == "CN":
            return ["akshare_cn_history"]
        return []

    def _fundamentals_provider_chain(self, asset: AssetIdentity) -> list[str]:
        if asset.market == "HK":
            return ["yahoo_hk_fundamentals"]
        if asset.market == "US":
            return ["yahoo_us_fundamentals"]
        if asset.market == "CN":
            return ["akshare_cn_individual_fundamentals", "akshare_cn_spot_fundamentals"]
        return []

    def _official_filings_provider_chain(self, asset: AssetIdentity) -> list[str]:
        if asset.market == "HK":
            return ["hkexnews"]
        if asset.market == "US":
            return ["sec_edgar"]
        if asset.market == "CN":
            return ["cninfo"]
        return []

    def _fund_profile_provider_chain(self, asset: AssetIdentity) -> list[str]:
        if asset.market == "FUND" or asset.asset_type in ("fund", "bond"):
            return ["akshare_fund_profile"]
        return []

    def _hk_research_context(self, asset: AssetIdentity) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], list[str]]:
        liquidity: dict[str, Any] = {}
        southbound: dict[str, Any] = {}
        limitations: list[str] = []
        try:
            liquidity = hk_client.fetch_market_liquidity()
        except Exception as exc:
            limitations.append(f"港股宏观流动性抓取失败: {exc}")
        try:
            southbound = hk_client.fetch_southbound_flow()
        except Exception as exc:
            limitations.append(f"南向资金抓取失败: {exc}")
        code = asset.normalized_code()
        source_code = code.lstrip("0").zfill(4)
        sources = {
            "quote_primary": f"https://finance.yahoo.com/quote/{source_code}.HK",
            "quote_secondary": f"https://finance.sina.com.cn/stock/hkstock/quote.html?code={code}",
            "fundamentals": f"https://finance.yahoo.com/quote/{source_code}.HK/key-statistics",
            "macro": "Yahoo Finance / akshare HIBOR",
            "southbound": "akshare 港股通数据",
        }
        limitations.append(
            "PE/PB/PS 等估值主要来自 Yahoo Finance/Futu 兼容数据源，必要时需用官方财报二次核验。"
        )
        return liquidity, southbound, sources, limitations

    def _us_research_context(self, asset: AssetIdentity) -> tuple[dict[str, Any], dict[str, str], list[str]]:
        macro: dict[str, Any] = {}
        limitations: list[str] = []
        try:
            macro = us_client.fetch_macro()
        except Exception as exc:
            limitations.append(f"美股宏观数据抓取失败: {exc}")
        code = asset.normalized_code()
        sources = {
            "quote_primary": f"https://finance.yahoo.com/quote/{code}",
            "fundamentals": f"https://finance.yahoo.com/quote/{code}/key-statistics",
            "macro": "Yahoo Finance: ^VIX / ^TNX / DX-Y.NYB / ^IRX",
        }
        limitations.append("一致预期、目标价、13F 变化尚未自动采集；报告中不得编造这些字段。")
        return macro, sources, limitations

    def _verify_quote(
        self,
        asset: AssetIdentity,
        quote: Quote,
        source: str,
        chain: list[str],
    ) -> dict:
        verified_by: list[str] = []
        warnings: list[str] = []
        confidence: Confidence = "high"
        base = quote.price
        if base is None or base <= 0:
            return {"verified_by": verified_by, "warnings": warnings, "confidence": "low"}

        for provider_name in chain:
            if provider_name == source:
                continue
            provider = self.quote_providers.get(provider_name)
            if provider is None or not provider.supports(asset):
                continue
            try:
                other = provider.get_quote(asset)
            except Exception as exc:
                warnings.append(f"verification {provider_name} failed: {exc}")
                continue
            if other is None or other.price is None or other.price <= 0:
                continue
            verified_by.append(provider_name)
            diff_pct = abs(other.price / base - 1) * 100
            if diff_pct > self.price_deviation_warn_pct:
                warnings.append(
                    f"{provider_name} quote differs from {source} by {diff_pct:.2f}%"
                )
                confidence = "medium"
            break

        if not verified_by:
            confidence = "medium" if confidence == "high" else confidence
        return {"verified_by": verified_by, "warnings": warnings, "confidence": confidence}

    def _verify_metric(
        self,
        *,
        asset: AssetIdentity,
        data: Any,
        source: str,
        chain: list[str],
        providers: dict[str, Any],
        getter: Callable[[Any, AssetIdentity], Any],
    ) -> dict:
        verified_by: list[str] = []
        warnings: list[str] = []
        confidence: Confidence = "high"
        base = _data_to_dict(data)

        for provider_name in chain:
            if provider_name == source:
                continue
            provider = providers.get(provider_name)
            if provider is None or not provider.supports(asset):
                continue
            try:
                other = getter(provider, asset)
            except Exception as exc:
                warnings.append(f"verification {provider_name} failed: {exc}")
                continue
            if other is None:
                continue
            other_dict = _data_to_dict(other)
            comparable = 0
            for key, value in base.items():
                if key in {"ticker", "name"}:
                    continue
                other_value = other_dict.get(key)
                if not _is_number(value) or not _is_number(other_value) or float(value) == 0:
                    continue
                comparable += 1
                diff_pct = abs(float(other_value) / float(value) - 1) * 100
                if diff_pct > self.metric_deviation_warn_pct:
                    warnings.append(
                        f"{provider_name}.{key} differs from {source} by {diff_pct:.2f}%"
                    )
                    confidence = "medium"
            verified_by.append(provider_name)
            if comparable == 0:
                warnings.append(f"{provider_name} had no overlapping numeric fields for verification")
                confidence = "medium"
            break

        if not verified_by:
            confidence = "medium"
        return {"verified_by": verified_by, "warnings": warnings, "confidence": confidence}


def _data_to_dict(data: Any) -> dict[str, Any]:
    if is_dataclass(data):
        return asdict(data)
    return dict(data) if isinstance(data, dict) else {}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


market_data_service = MarketDataService()
