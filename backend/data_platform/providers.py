"""Quote provider adapters for AlphaLens data platform."""

from __future__ import annotations

import datetime as dt
import os
import re
import warnings
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from backend.data import futu_client, hk_client, us_client
from backend.data.cache import cache
from backend.data_platform.models import (
    AssetIdentity,
    FundProfile,
    Fundamentals,
    OfficialFilings,
    Quote,
    Returns,
    Technicals,
    today_iso,
)

try:
    import akshare as ak
except ImportError:
    ak = None

TTL_INTRADAY = 60 * 10
TTL_DAILY = 60 * 60 * 6
PROXY_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


class QuoteProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        ...


class ReturnsProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        ...


class TechnicalsProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_technicals(self, asset: AssetIdentity) -> Technicals | None:
        ...


class FundamentalsProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        ...


class OfficialFilingsProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_official_filings(self, asset: AssetIdentity) -> OfficialFilings | None:
        ...


class FundProfileProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, asset: AssetIdentity) -> bool:
        ...

    @abstractmethod
    def get_fund_profile(self, asset: AssetIdentity) -> FundProfile | None:
        ...


@contextmanager
def _no_proxy():
    saved = {key: os.environ.pop(key, None) for key in PROXY_VARS}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _rsi14(close: pd.Series) -> float | None:
    if len(close) < 15:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    if avg_loss is None or avg_loss == 0 or avg_loss != avg_loss:
        return 100.0 if avg_gain and avg_gain > 0 else None
    rs = float(avg_gain) / float(avg_loss)
    return round(100 - 100 / (1 + rs), 1)


def _http_get_json(url: str) -> dict:
    headers = {
        "User-Agent": "AlphaLens research app shawn@example.com",
        "Accept-Encoding": "gzip, deflate",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _http_get_text(url: str) -> str:
    headers = {
        "User-Agent": "AlphaLens research app shawn@example.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_html_snippet(url: str, max_chars: int = 5000) -> str | None:
    try:
        html = _http_get_text(url)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "ix:header", "ix:hidden"]):
            tag.decompose()
        text = soup.get_text("\n")
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        clean = "\n".join(line for line in lines if len(line) >= 20)
        return clean[:max_chars] if clean else None
    except Exception:
        return None


class HKYahooQuoteProvider(QuoteProvider):
    name = "yahoo_hk"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        code = asset.normalized_code()
        data = hk_client.fetch_stock_snapshots_yf([code]).get(code)
        if not data or data.get("price") is None:
            return None
        return Quote(
            price=data.get("price"),
            change_pct=data.get("change_pct"),
            name=data.get("name"),
            volume_mn=data.get("volume_hkd_mn"),
            currency="HKD",
            as_of=today_iso(),
        )


class HKFutuQuoteProvider(QuoteProvider):
    name = "futu_hk"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        code = asset.normalized_code()
        data = futu_client.fetch_snapshot([code]).get(code)
        if not data or data.get("last_price") is None:
            return None
        return Quote(
            price=data.get("last_price"),
            change_pct=data.get("change_pct"),
            name=data.get("name"),
            volume_mn=data.get("turnover_hkd_mn"),
            currency="HKD",
            as_of=today_iso(),
        )


class USYahooQuoteProvider(QuoteProvider):
    name = "yahoo_us"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "US" and asset.asset_type in ("stock", "etf", "unknown")

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        code = asset.normalized_code()
        data = us_client.fetch_snapshot([code]).get(code)
        if not data or data.get("price") is None:
            return None
        return Quote(
            price=data.get("price"),
            change_pct=data.get("change_pct"),
            name=data.get("name"),
            volume_mn=data.get("volume_usd_mn"),
            currency="USD",
            as_of=today_iso(),
        )


class FundAkshareQuoteProvider(QuoteProvider):
    name = "akshare_fund_nav"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "FUND" or asset.asset_type in ("fund", "bond")

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        code = asset.normalized_code()
        price = _fund_spot().get(code)
        if price is None:
            price = _fund_one_nav(code)
        if price is None:
            return None
        profile = _fund_profile_map().get(code) or {}
        return Quote(
            price=price,
            name=profile.get("name"),
            currency=asset.currency or "CNY",
            as_of=today_iso(),
        )


class CNAkshareQuoteProvider(QuoteProvider):
    name = "akshare_cn_bid_ask"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_quote(self, asset: AssetIdentity) -> Quote | None:
        if ak is None:
            return None
        code = asset.normalized_code()
        data = _cn_bid_ask(code)
        price = _safe_float(data.get("最新"))
        if price is None:
            return None
        info = _cn_individual_info(code)
        volume_cny_mn = _safe_float(data.get("金额"))
        return Quote(
            price=price,
            change_pct=_safe_float(data.get("涨幅")),
            name=str(info.get("股票简称") or "") or None,
            volume_mn=round(volume_cny_mn / 1_000_000, 2) if volume_cny_mn else None,
            currency="CNY",
            as_of=today_iso(),
        )


class HKReturnsProvider(ReturnsProvider):
    name = "hk_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        data = hk_client.compute_stock_returns(asset.normalized_code())
        return Returns(**data)


class HKTechnicalsProvider(TechnicalsProvider):
    name = "hk_history_futu"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_technicals(self, asset: AssetIdentity) -> Technicals | None:
        code = asset.normalized_code()
        data = hk_client.compute_stock_technicals(code)
        try:
            snap = futu_client.fetch_snapshot([code]).get(code) or {}
            data["turnover_rate"] = snap.get("turnover_rate")
            data["volume_ratio"] = snap.get("volume_ratio")
        except Exception:
            data["turnover_rate"] = None
            data["volume_ratio"] = None
        try:
            cf = futu_client.fetch_capital_flow(code)
            data["net_inflow_today_hkd_mn"] = cf.get("net_inflow_today_hkd_mn")
            data["net_inflow_5d_hkd_mn"] = cf.get("net_inflow_5d_hkd_mn")
        except Exception:
            data["net_inflow_today_hkd_mn"] = None
            data["net_inflow_5d_hkd_mn"] = None
        try:
            ob = futu_client.fetch_order_book_metrics(code)
            data["bid_ask_spread_bps"] = ob.get("bid_ask_spread_bps")
            data["depth_ratio_5"] = ob.get("depth_ratio_5")
        except Exception:
            data["bid_ask_spread_bps"] = None
            data["depth_ratio_5"] = None
        return Technicals(**data)


class HKFundamentalsProvider(FundamentalsProvider):
    name = "yahoo_hk_fundamentals"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        data = hk_client.fetch_stock_fundamentals(asset.normalized_code())
        return Fundamentals(**data)


class USReturnsProvider(ReturnsProvider):
    name = "us_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "US" and asset.asset_type in ("stock", "etf", "unknown")

    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        data = us_client.compute_returns(asset.normalized_code())
        return Returns(**data)


class USTechnicalsProvider(TechnicalsProvider):
    name = "us_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "US" and asset.asset_type in ("stock", "etf", "unknown")

    def get_technicals(self, asset: AssetIdentity) -> Technicals | None:
        data = us_client.compute_technicals(asset.normalized_code())
        return Technicals(**data)


class USFundamentalsProvider(FundamentalsProvider):
    name = "yahoo_us_fundamentals"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "US" and asset.asset_type in ("stock", "etf", "unknown")

    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        data = us_client.fetch_fundamentals(asset.normalized_code())
        return Fundamentals(**data)


class CNReturnsProvider(ReturnsProvider):
    name = "akshare_cn_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        hist = _cn_history(asset.normalized_code())
        empty = Returns(ticker=asset.normalized_code())
        if hist.empty or "收盘" not in hist.columns:
            return empty
        close = hist["收盘"].astype(float).dropna().reset_index(drop=True)
        if close.empty:
            return empty
        latest = float(close.iloc[-1])

        def lookback(days: int) -> float | None:
            if len(close) <= days:
                return None
            prev = float(close.iloc[-1 - days])
            if prev <= 0:
                return None
            return round((latest / prev - 1) * 100, 2)

        return Returns(
            ticker=asset.normalized_code(),
            ret_1m=lookback(21),
            ret_3m=lookback(63),
            ret_6m=lookback(126),
            ret_12m=lookback(252),
        )


class CNTechnicalsProvider(TechnicalsProvider):
    name = "akshare_cn_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_technicals(self, asset: AssetIdentity) -> Technicals | None:
        code = asset.normalized_code()
        hist = _cn_history(code)
        empty = Technicals(ticker=code)
        if hist.empty or "收盘" not in hist.columns:
            return empty
        close = hist["收盘"].astype(float).dropna().reset_index(drop=True)
        if close.empty:
            return empty
        latest = float(close.iloc[-1])
        dist_ma200 = None
        if len(close) >= 200:
            ma200 = float(close.tail(200).mean())
            if ma200 > 0:
                dist_ma200 = round((latest / ma200 - 1) * 100, 1)
        pos_52w = None
        if len(close) >= 60:
            win = close.tail(252) if len(close) >= 252 else close
            hi, lo = float(win.max()), float(win.min())
            if hi > lo:
                pos_52w = round((latest - lo) / (hi - lo) * 100, 1)
        adtv = None
        if "成交额" in hist.columns and len(hist) >= 20:
            turnover = hist.tail(20)["成交额"].astype(float).dropna()
            if not turnover.empty:
                adtv = round(float(turnover.mean()) / 1_000_000, 2)
        return Technicals(
            ticker=code,
            rsi14=_rsi14(close),
            dist_ma200_pct=dist_ma200,
            pos_52w_pct=pos_52w,
            adtv_20d_cny_mn=adtv,
        )


class CNIndividualFundamentalsProvider(FundamentalsProvider):
    name = "akshare_cn_individual_fundamentals"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        if ak is None:
            return None
        code = asset.normalized_code()
        info = _cn_individual_info(code)
        market_cap = _safe_float(info.get("总市值"))
        return Fundamentals(
            ticker=code,
            name=str(info.get("股票简称") or "") or None,
            market_cap_cny_bn=round(market_cap / 1_000_000_000, 1) if market_cap else None,
        )


class CNSpotFundamentalsProvider(FundamentalsProvider):
    name = "akshare_cn_spot_fundamentals"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_fundamentals(self, asset: AssetIdentity) -> Fundamentals | None:
        if ak is None:
            return None
        code = asset.normalized_code()
        info = _cn_individual_info(code)
        spot = _cn_spot_row(code)
        market_cap = _safe_float(info.get("总市值") or spot.get("总市值"))
        return Fundamentals(
            ticker=code,
            name=str(info.get("股票简称") or spot.get("名称") or "") or None,
            pe_ttm=_safe_float(spot.get("市盈率-动态")),
            pb=_safe_float(spot.get("市净率")),
            market_cap_cny_bn=round(market_cap / 1_000_000_000, 1) if market_cap else None,
            ps_ttm=None,
            revenue_growth_pct=None,
            gross_margin_pct=None,
            roe_pct=None,
            beta=None,
        )


class FundReturnsProvider(ReturnsProvider):
    name = "akshare_fund_nav_history"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "FUND" or asset.asset_type in ("fund", "bond")

    def get_returns(self, asset: AssetIdentity) -> Returns | None:
        code = asset.normalized_code()
        df = _fund_nav_history(code)
        empty = Returns(ticker=code)
        if df.empty:
            return empty
        value_col = next((col for col in ("单位净值", "累计净值", "净值") if col in df.columns), None)
        if not value_col:
            return empty
        nav = df[value_col].astype(float).dropna().reset_index(drop=True)
        if nav.empty:
            return empty
        latest = float(nav.iloc[-1])

        def lookback(days: int) -> float | None:
            if len(nav) <= days:
                return None
            prev = float(nav.iloc[-1 - days])
            if prev <= 0:
                return None
            return round((latest / prev - 1) * 100, 2)

        return Returns(
            ticker=code,
            ret_1m=lookback(21),
            ret_3m=lookback(63),
            ret_6m=lookback(126),
            ret_12m=lookback(252),
        )


class FundProfileAkshareProvider(FundProfileProvider):
    name = "akshare_fund_profile"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "FUND" or asset.asset_type in ("fund", "bond")

    def get_fund_profile(self, asset: AssetIdentity) -> FundProfile | None:
        code = asset.normalized_code()
        meta = _fund_profile_map().get(code)
        if not meta:
            return FundProfile(code=code)
        classification = classify_fund_profile(meta.get("name") or "", meta.get("type") or "")
        return FundProfile(
            code=code,
            name=meta.get("name"),
            fund_type=meta.get("type"),
            **classification,
        )


class SECOfficialFilingsProvider(OfficialFilingsProvider):
    name = "sec_edgar"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "US" and asset.asset_type in ("stock", "etf", "unknown")

    def get_official_filings(self, asset: AssetIdentity) -> OfficialFilings | None:
        ticker = asset.normalized_code()
        out = OfficialFilings(source="SEC EDGAR", status="not_found", company_code=ticker)
        try:
            mapping = _http_get_json("https://www.sec.gov/files/company_tickers.json")
            target = ticker.upper().replace("-", ".")
            match = None
            for item in mapping.values():
                if str(item.get("ticker", "")).upper() == target:
                    match = item
                    break
            if not match:
                return OfficialFilings(
                    **{**out.__dict__, "notes": ["SEC company_tickers.json 未匹配到该 ticker。"]}
                )
            cik = str(match["cik_str"]).zfill(10)
            submissions = _http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
            recent = submissions.get("filings", {}).get("recent", {})
            filings = []
            for form, accession, doc, filing_date in zip(
                recent.get("form", []),
                recent.get("accessionNumber", []),
                recent.get("primaryDocument", []),
                recent.get("filingDate", []),
            ):
                if form not in {"10-K", "10-Q", "20-F", "40-F"}:
                    continue
                accession_nodash = accession.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{doc}"
                filings.append(
                    {
                        "form": form,
                        "filing_date": filing_date,
                        "accession": accession,
                        "url": url,
                        "text_snippet": _extract_html_snippet(url),
                    }
                )
                if len(filings) >= 3:
                    break
            return OfficialFilings(
                source="SEC EDGAR",
                status="ok" if filings else "empty",
                company_code=ticker,
                company_name=match.get("title"),
                cik=cik,
                official_search_url=f"https://www.sec.gov/edgar/search/#/q={ticker}",
                filings=filings,
            )
        except Exception as exc:
            return OfficialFilings(**{**out.__dict__, "status": "error", "notes": [str(exc)]})


class HKEXOfficialFilingsProvider(OfficialFilingsProvider):
    name = "hkexnews"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "HK" and asset.asset_type in ("stock", "etf", "unknown")

    def get_official_filings(self, asset: AssetIdentity) -> OfficialFilings | None:
        ticker = asset.normalized_code()
        official_url = (
            "https://www1.hkexnews.hk/search/titlesearch.xhtml"
            f"?lang=zh&market=SEHK&stockId={ticker.lstrip('0')}"
        )
        snapshots: dict[str, Any] = {}
        notes = ["HKEX PDF 正文暂未自动下载/解析；请以 official_search_url 人工核验最新年报/中报。"]
        status = "search_link_only"
        if ak is None:
            notes.append("akshare 不可用，无法补充东方财富港股三大报表。")
        else:
            try:
                for statement in ["资产负债表", "利润表", "现金流量表"]:
                    df = cache.fetch(
                        "hk_financial_report",
                        f"{ticker}:{statement}:annual",
                        TTL_DAILY,
                        lambda statement=statement: ak.stock_financial_hk_report_em(
                            stock=ticker,
                            symbol=statement,
                            indicator="年度",
                        ),
                    )
                    if df is None or df.empty:
                        continue
                    snapshots[statement] = df.head(5).to_dict(orient="records")
                if snapshots:
                    status = "supplemented"
                    notes.append("已补充东方财富港股财务报表快照，非官方源，仅用于辅助。")
            except Exception as exc:
                notes.append(f"东方财富港股财报快照抓取失败: {exc}")
        return OfficialFilings(
            source="HKEXnews",
            status=status,
            company_code=ticker,
            official_search_url=official_url,
            financial_statement_snapshots=snapshots,
            notes=notes,
        )


class CNInfoOfficialFilingsProvider(OfficialFilingsProvider):
    name = "cninfo"

    def supports(self, asset: AssetIdentity) -> bool:
        return asset.market == "CN" and asset.asset_type in ("stock", "unknown")

    def get_official_filings(self, asset: AssetIdentity) -> OfficialFilings | None:
        ticker = asset.normalized_code()
        official_url = "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"
        notes: list[str] = []
        if ak is None:
            return OfficialFilings(
                source="巨潮资讯 CNINFO",
                status="empty",
                company_code=ticker,
                official_search_url=official_url,
                notes=["akshare 不可用，无法查询巨潮资讯公告。"],
            )
        end = dt.date.today()
        start = end - dt.timedelta(days=365 * 3)
        filings = []
        for category in ["年报", "半年报", "一季报", "三季报"]:
            try:
                df = cache.fetch(
                    "cninfo_disclosure",
                    f"{ticker}:{category}:{start:%Y%m%d}:{end:%Y%m%d}",
                    TTL_DAILY,
                    lambda category=category: ak.stock_zh_a_disclosure_report_cninfo(
                        symbol=ticker,
                        market="沪深京",
                        category=category,
                        start_date=start.strftime("%Y%m%d"),
                        end_date=end.strftime("%Y%m%d"),
                    ),
                )
                if df is None or df.empty:
                    continue
                for _, row in df.head(3).iterrows():
                    filings.append({k: str(v) for k, v in row.to_dict().items()})
            except Exception as exc:
                notes.append(f"{category} 查询失败: {exc}")
        return OfficialFilings(
            source="巨潮资讯 CNINFO",
            status="ok" if filings else "empty",
            company_code=ticker,
            official_search_url=official_url,
            filings=filings[:8],
            notes=notes,
        )


def _cn_history(code: str) -> pd.DataFrame:
    if ak is None:
        return pd.DataFrame()
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * 3)
    try:
        df = cache.fetch(
            "cn_stock_history",
            f"{code}:{start:%Y%m%d}:{end:%Y%m%d}:qfq",
            TTL_DAILY,
            lambda: ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            ),
        )
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _cn_bid_ask(code: str) -> dict[str, Any]:
    if ak is None:
        return {}
    try:
        df = cache.fetch(
            "cn_bid_ask",
            code,
            TTL_INTRADAY,
            lambda: ak.stock_bid_ask_em(symbol=code),
        )
        if df is None or df.empty:
            return {}
        return {str(row["item"]): row["value"] for _, row in df.iterrows()}
    except Exception:
        return {}


def _cn_individual_info(code: str) -> dict[str, Any]:
    if ak is None:
        return {}
    try:
        df = cache.fetch(
            "cn_individual_info",
            code,
            TTL_DAILY,
            lambda: ak.stock_individual_info_em(symbol=code),
        )
        if df is None or df.empty:
            return {}
        return {str(row["item"]): row["value"] for _, row in df.iterrows()}
    except Exception:
        return {}


def _cn_spot_row(code: str) -> dict[str, Any]:
    if ak is None:
        return {}
    try:
        df = cache.fetch("cn_spot", "stock_zh_a_spot_em", TTL_INTRADAY, ak.stock_zh_a_spot_em)
        if df is None or df.empty or "代码" not in df.columns:
            return {}
        row = df[df["代码"].astype(str).str.zfill(6) == code]
        if row.empty:
            return {}
        return row.iloc[0].to_dict()
    except Exception:
        return {}


def _fund_spot() -> dict[str, float]:
    if ak is None:
        return {}

    def produce() -> dict[str, float]:
        with _no_proxy():
            df = ak.fund_value_estimation_em()
        nav_col = next((col for col in df.columns if col.endswith("公布数据-单位净值")), None)
        est_col = next((col for col in df.columns if col.endswith("估算数据-估算值")), None)
        out: dict[str, float] = {}
        for _, row in df.iterrows():
            code = str(row["基金代码"]).strip().zfill(6)
            for col in (nav_col, est_col):
                if not col:
                    continue
                value = _safe_float(row.get(col))
                if value and value > 0:
                    out[code] = value
                    break
        return out

    try:
        return cache.fetch("fund_spot", "fund_value_estimation_em", TTL_INTRADAY, produce)
    except Exception:
        return {}


def _fund_one_nav(code: str) -> float | None:
    if ak is None:
        return None

    def produce() -> float | None:
        with _no_proxy():
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            return None
        return _safe_float(df.iloc[-1].get("单位净值"))

    try:
        return cache.fetch("fund_one_nav", code, TTL_INTRADAY, produce)
    except Exception:
        return None


def _fund_nav_history(code: str) -> pd.DataFrame:
    if ak is None:
        return pd.DataFrame()

    def produce() -> pd.DataFrame:
        with _no_proxy():
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        return df if df is not None else pd.DataFrame()

    try:
        return cache.fetch("fund_nav_history", code, TTL_DAILY, produce)
    except Exception:
        return pd.DataFrame()


def _fund_profile_map() -> dict[str, dict[str, str]]:
    if ak is None:
        return {}

    def produce() -> dict[str, dict[str, str]]:
        with _no_proxy():
            df = ak.fund_name_em()
        out: dict[str, dict[str, str]] = {}
        for _, row in df.iterrows():
            code = str(row["基金代码"]).strip().zfill(6)
            out[code] = {
                "name": str(row.get("基金简称") or "").strip(),
                "type": str(row.get("基金类型") or "").strip(),
            }
        return out

    try:
        return cache.fetch("fund_profiles", "fund_name_em", 24 * 60 * 60, produce)
    except Exception:
        return {}


def classify_fund_profile(name: str, fund_type: str = "") -> dict[str, str | None]:
    text = f"{name} {fund_type}"
    asset_class = "股票"
    tag_l1: str | None = "价值成长"
    tag_l2: str | None = None
    market = "中国"

    if any(key in text for key in ("货币", "现金", "同业存单")):
        asset_class, tag_l1, tag_l2 = "现金", "现金", "现金"
    elif any(key in text for key in ("债", "短债", "中短债", "纯债", "可转债")):
        asset_class = "债券"
        is_mixed = any(key in text for key in ("混合债", "混合一级", "混合二级", "可转债", "增强债"))
        tag_l1 = "混合债券" if is_mixed else "纯债"
        tag_l2 = "混合债券" if is_mixed else "纯债-中国"
        if "QDII" in text.upper() and any(key in text for key in ("美元", "美国", "全球", "亚洲")):
            tag_l2 = "混合债券" if is_mixed else "纯债-美国"
    elif any(key in text for key in ("黄金", "贵金属")):
        asset_class, tag_l1, tag_l2 = "黄金", "黄金/虚拟币", "黄金/虚拟币"
    elif any(key in text for key in ("红利", "低波")):
        asset_class, tag_l1 = "股票", "红利低波"
        if any(key in text for key in ("港", "恒生", "香港")):
            tag_l2 = "港股红利"
        elif any(key in text for key in ("美", "标普", "纳斯达克")):
            tag_l2 = "美股红利"
        else:
            tag_l2 = "沪深红利"
    elif any(key in text for key in ("科技", "互联网", "纳斯达克", "恒生科技")):
        asset_class, tag_l1 = "股票", "价值成长"
        if any(key in text for key in ("港", "恒生")):
            tag_l2 = "港股科技"
        elif any(key in text for key in ("美", "纳斯达克", "标普", "全球")):
            tag_l2 = "美股科技"

    return {
        "market": market,
        "asset_class": asset_class,
        "tag_l1": tag_l1,
        "tag_l2": tag_l2,
    }


DEFAULT_QUOTE_PROVIDERS: dict[str, QuoteProvider] = {
    "akshare_cn_spot": CNAkshareQuoteProvider(),
    "akshare_cn_bid_ask": CNAkshareQuoteProvider(),
    "akshare_fund_nav": FundAkshareQuoteProvider(),
    "yahoo_hk": HKYahooQuoteProvider(),
    "futu_hk": HKFutuQuoteProvider(),
    "yahoo_us": USYahooQuoteProvider(),
}

DEFAULT_RETURNS_PROVIDERS: dict[str, ReturnsProvider] = {
    "akshare_cn_history": CNReturnsProvider(),
    "akshare_fund_nav_history": FundReturnsProvider(),
    "hk_history": HKReturnsProvider(),
    "us_history": USReturnsProvider(),
}

DEFAULT_TECHNICALS_PROVIDERS: dict[str, TechnicalsProvider] = {
    "akshare_cn_history": CNTechnicalsProvider(),
    "hk_history_futu": HKTechnicalsProvider(),
    "us_history": USTechnicalsProvider(),
}

DEFAULT_FUNDAMENTALS_PROVIDERS: dict[str, FundamentalsProvider] = {
    "akshare_cn_individual_fundamentals": CNIndividualFundamentalsProvider(),
    "akshare_cn_spot_fundamentals": CNSpotFundamentalsProvider(),
    "yahoo_hk_fundamentals": HKFundamentalsProvider(),
    "yahoo_us_fundamentals": USFundamentalsProvider(),
}

DEFAULT_OFFICIAL_FILINGS_PROVIDERS: dict[str, OfficialFilingsProvider] = {
    "cninfo": CNInfoOfficialFilingsProvider(),
    "hkexnews": HKEXOfficialFilingsProvider(),
    "sec_edgar": SECOfficialFilingsProvider(),
}

DEFAULT_FUND_PROFILE_PROVIDERS: dict[str, FundProfileProvider] = {
    "akshare_fund_profile": FundProfileAkshareProvider(),
}
