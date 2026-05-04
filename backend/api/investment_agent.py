"""Investment agent document store and lightweight conversation entry."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.data import hk_client, us_client
from backend.strategy.llm import call_gemini, call_minimax

try:
    import akshare as ak
except ImportError:
    ak = None


_DEFAULT_DB_PATH = Path(
    os.environ.get(
        "ALPHALENS_AGENT_DB",
        Path.home() / "Code" / "alphalens" / ".cache" / "investment_agent.sqlite",
    )
)

_SKILL_DIR = Path.home() / ".codex" / "skills" / "value-stock-decider"
_SKILL_MD = _SKILL_DIR / "SKILL.md"
_REFERENCE_FILES = [
    _SKILL_DIR / "references" / "strategy-framework.md",
    _SKILL_DIR / "references" / "quality-rubric.md",
    _SKILL_DIR / "references" / "valuation-methods.md",
    _SKILL_DIR / "references" / "scenario-design.md",
    _SKILL_DIR / "references" / "indicators.md",
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT '策略分析',
    symbols     TEXT NOT NULL DEFAULT '',
    thesis      TEXT NOT NULL DEFAULT '',
    conclusion  TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_documents_updated
ON strategy_documents(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_documents_category
ON strategy_documents(category);
"""


router = APIRouter(prefix="/api/agent", tags=["investment-agent"])


class StrategyDocument(BaseModel):
    id: int
    title: str
    category: str
    symbols: list[str]
    thesis: str
    conclusion: str
    summary: str
    content: str
    tags: list[str]
    status: str
    created_at: str
    updated_at: str


class StrategyDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: str = Field(default="策略分析", min_length=1, max_length=40)
    symbols: list[str] = Field(default_factory=list)
    thesis: str = Field(default="", max_length=2000)
    conclusion: str = Field(default="", max_length=4000)
    summary: str = Field(default="", max_length=2000)
    content: str = Field(default="", max_length=20000)
    tags: list[str] = Field(default_factory=list)
    status: Literal["draft", "running", "completed", "error", "archived"] = "draft"


class AgentConversationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    category: str = Field(default="个股投资决策", min_length=1, max_length=40)
    symbols: list[str] = Field(default_factory=list)
    provider: Literal["gemini", "minimax"] = "gemini"


class AgentConversationResult(BaseModel):
    document: StrategyDocument
    reply: str


class DocumentList(BaseModel):
    items: list[StrategyDocument]
    total: int


@contextmanager
def _connect():
    _DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _join(values: list[str]) -> str:
    return ",".join(v.strip() for v in values if v and v.strip())


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _row_to_doc(row: sqlite3.Row) -> StrategyDocument:
    return StrategyDocument(
        id=int(row["id"]),
        title=str(row["title"]),
        category=str(row["category"]),
        symbols=_split(str(row["symbols"] or "")),
        thesis=str(row["thesis"] or ""),
        conclusion=str(row["conclusion"] or ""),
        summary=str(row["summary"] or ""),
        content=str(row["content"] or ""),
        tags=_split(str(row["tags"] or "")),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _build_summary(payload: StrategyDocumentCreate) -> str:
    if payload.summary.strip():
        return payload.summary.strip()
    if payload.conclusion.strip():
        return payload.conclusion.strip()[:500]
    if payload.thesis.strip():
        return payload.thesis.strip()[:500]
    return payload.content.strip()[:500]


@router.get("/documents", response_model=DocumentList)
def list_documents(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentList:
    clauses: list[str] = []
    params: list[str | int] = []
    if category and category != "全部":
        clauses.append("category = ?")
        params.append(category)
    if q:
        like = f"%{q.strip()}%"
        clauses.append(
            "(title LIKE ? OR symbols LIKE ? OR thesis LIKE ? OR conclusion LIKE ? OR summary LIKE ? OR content LIKE ? OR tags LIKE ?)"
        )
        params.extend([like] * 7)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) AS n FROM strategy_documents {where}", params).fetchone()["n"])
        rows = conn.execute(
            f"""
            SELECT * FROM strategy_documents
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return DocumentList(items=[_row_to_doc(r) for r in rows], total=total)


@router.get("/documents/recent", response_model=StrategyDocument | None)
def recent_document() -> StrategyDocument | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM strategy_documents
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return _row_to_doc(row) if row else None


@router.get("/documents/{doc_id}", response_model=StrategyDocument)
def get_document(doc_id: int) -> StrategyDocument:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM strategy_documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return _row_to_doc(row)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int) -> dict[str, bool]:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM strategy_documents WHERE id = ?", (doc_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}


@router.get("/categories", response_model=list[str])
def list_categories() -> list[str]:
    return ["个股投资决策"]


@router.post("/documents", response_model=StrategyDocument)
def create_document(payload: StrategyDocumentCreate) -> StrategyDocument:
    now = _now()
    summary = _build_summary(payload)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO strategy_documents
            (title, category, symbols, thesis, conclusion, summary, content, tags, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title.strip(),
                payload.category.strip(),
                _join(payload.symbols),
                payload.thesis.strip(),
                payload.conclusion.strip(),
                summary,
                payload.content.strip(),
                _join(payload.tags),
                payload.status,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM strategy_documents WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_doc(row)


@router.post("/chat", response_model=AgentConversationResult)
def start_conversation(
    payload: AgentConversationRequest,
    background_tasks: BackgroundTasks,
) -> AgentConversationResult:
    """Create a document and run value-stock-decider through the selected model API."""
    symbols = _normalize_symbols(payload.symbols)
    provider = payload.provider
    provider_name = _provider_name(provider)
    title = _make_title(payload.message, symbols)
    doc = create_document(
        StrategyDocumentCreate(
            title=title,
            category="个股投资决策",
            symbols=symbols,
            thesis=payload.message.strip(),
            summary=f"{provider_name} 正在按 value-stock-decider 生成个股投资决策分析。",
            content=payload.message.strip(),
            tags=[provider_name, "value-stock-decider"],
            status="running",
        )
    )
    background_tasks.add_task(_run_model_analysis, doc.id, payload.message.strip(), symbols, provider)
    return AgentConversationResult(
        document=doc,
        reply=f"已启动 {provider_name} 分析任务，正在按 value-stock-decider 生成个股投资决策报告。",
    )


def _normalize_symbols(symbols: list[str]) -> list[str]:
    out: list[str] = []
    for symbol in symbols:
        clean = re.sub(r"\s+", "", symbol.upper())
        if clean and clean not in out:
            out.append(clean)
    return out[:5]


def _make_title(message: str, symbols: list[str]) -> str:
    prefix = f"{', '.join(symbols)} 投资决策分析" if symbols else "个股投资决策分析"
    first_line = message.strip().splitlines()[0][:48]
    return f"{prefix} - {first_line}"[:120]


def _provider_name(provider: Literal["gemini", "minimax"]) -> str:
    return "MiniMax" if provider == "minimax" else "Gemini"


def _update_document(
    doc_id: int,
    *,
    status: str,
    summary: str,
    conclusion: str,
    content: str,
    tags: list[str] | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE strategy_documents
            SET status = ?, summary = ?, conclusion = ?, content = ?, tags = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                summary.strip()[:2000],
                conclusion.strip()[:4000],
                content.strip()[:20000],
                _join(tags or ["Gemini", "value-stock-decider"]),
                _now(),
                doc_id,
            ),
        )


def _run_model_analysis(
    doc_id: int,
    message: str,
    symbols: list[str],
    provider: Literal["gemini", "minimax"],
) -> None:
    provider_name = _provider_name(provider)
    try:
        if not _SKILL_MD.exists():
            raise RuntimeError(f"未找到 value-stock-decider skill: {_SKILL_MD}")

        market_data = _collect_market_data(symbols)
        prompt = _build_analysis_prompt(doc_id, message, symbols, market_data, provider_name)
        if provider == "minimax":
            raw_content = call_minimax(prompt, max_tokens=6000, temperature=0.2)
        else:
            raw_content = call_gemini(prompt, max_tokens=6000, temperature=0.2)
        if not raw_content:
            env_hint = "MINIMAX_API_KEY / MINIMAX_MODEL" if provider == "minimax" else "GEMINI_API_KEY / GEMINI_MODEL"
            raise RuntimeError(f"{provider_name} 未返回分析内容。请检查 {env_hint} 配置。")
        content = _sanitize_report(raw_content)
        summary = _extract_section(content, "结论摘要") or content[:800]
        conclusion = (
            _extract_section(content, "投资决策")
            or _extract_section(content, "核心结论")
            or summary
        )
        _update_document(
            doc_id,
            status="completed",
            summary=summary,
            conclusion=conclusion,
            content=content,
            tags=[provider_name, "value-stock-decider", "个股决策"],
        )
    except Exception as exc:
        _update_document(
            doc_id,
            status="error",
            summary=f"分析失败：{exc}",
            conclusion=f"分析失败：{exc}",
            content=f"分析失败：{exc}",
            tags=[provider_name, "分析失败"],
        )


def _read_skill_context() -> str:
    chunks: list[str] = []
    for path in [_SKILL_MD, *_REFERENCE_FILES]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        chunks.append(f"## {path.relative_to(_SKILL_DIR)}\n{text[:6000]}")
    return "\n\n".join(chunks)[:24000]


def _detect_market(symbol: str) -> str:
    clean = symbol.upper().strip()
    if clean.endswith(".HK") or re.fullmatch(r"\d{4,5}", clean):
        return "HK"
    if re.fullmatch(r"\d{6}", clean):
        return "CN"
    return "US"


def _normalize_for_market(symbol: str, market: str) -> str:
    clean = symbol.upper().strip()
    if market == "HK":
        return clean.removesuffix(".HK").lstrip("0").zfill(5)
    if market == "CN":
        return clean.removesuffix(".SS").removesuffix(".SZ")
    return clean.replace(".", "-")


def _collect_market_data(symbols: list[str]) -> dict:
    primary = symbols[0] if symbols else ""
    if not primary:
        return {
            "status": "missing_symbol",
            "notes": ["用户没有填写标的代码；请模型从请求文本中识别，无法识别则列为待补充。"],
        }

    market = _detect_market(primary)
    symbol = _normalize_for_market(primary, market)
    try:
        if market == "HK":
            return _collect_hk_data(symbol)
        if market == "US":
            return _collect_us_data(symbol)
        return _collect_cn_data(symbol)
    except Exception as exc:
        return {
            "symbol": symbol,
            "market": market,
            "status": "error",
            "error": str(exc),
            "notes": ["联网取数失败；报告中必须把实时数据列为待补充。"],
        }


def _collect_hk_data(ticker: str) -> dict:
    snapshot = hk_client.fetch_stock_snapshots_yf([ticker]).get(ticker, {})
    fundamentals = hk_client.fetch_stock_fundamentals(ticker)
    returns = hk_client.compute_stock_returns(ticker)
    technicals = hk_client.compute_stock_technicals(ticker)
    try:
        liquidity = hk_client.fetch_market_liquidity()
    except Exception:
        liquidity = {}
    try:
        southbound = hk_client.fetch_southbound_flow()
    except Exception:
        southbound = {}
    official_filings = _fetch_hk_official_filings(ticker)

    return {
        "symbol": ticker,
        "market": "HK",
        "currency": "HKD",
        "as_of": dt.date.today().isoformat(),
        "quote": snapshot,
        "fundamentals": fundamentals,
        "returns": returns,
        "technicals": technicals,
        "macro_liquidity": liquidity,
        "southbound_market_flow": southbound,
        "official_filings": official_filings,
        "sources": {
            "quote_primary": f"https://finance.yahoo.com/quote/{ticker.lstrip('0').zfill(4)}.HK",
            "quote_secondary": f"https://finance.sina.com.cn/stock/hkstock/quote.html?code={ticker}",
            "fundamentals": f"https://finance.yahoo.com/quote/{ticker.lstrip('0').zfill(4)}.HK/key-statistics",
            "official_filings": "https://www.hkexnews.hk",
            "macro": "Yahoo Finance / akshare HIBOR",
            "southbound": "akshare 港股通数据",
        },
        "limitations": [
            "HKEX 年报/季报正文 PDF 暂未自动 OCR；已提供官方检索入口/候选公告，关键财报字段需人工核验原文。",
            "PE/PB/PS 等估值主要来自 Yahoo Finance/Futu 兼容数据源，必要时需用富途/雪球二次交叉验证。",
        ],
    }


def _collect_us_data(ticker: str) -> dict:
    snapshot = us_client.fetch_snapshot([ticker]).get(ticker, {})
    fundamentals = us_client.fetch_fundamentals(ticker)
    returns = us_client.compute_returns(ticker)
    technicals = us_client.compute_technicals(ticker)
    macro = us_client.fetch_macro()
    official_filings = _fetch_sec_filings(ticker)

    return {
        "symbol": ticker,
        "market": "US",
        "currency": "USD",
        "as_of": dt.date.today().isoformat(),
        "quote": snapshot,
        "fundamentals": fundamentals,
        "returns": returns,
        "technicals": technicals,
        "macro_liquidity": macro,
        "official_filings": official_filings,
        "sources": {
            "quote_primary": f"https://finance.yahoo.com/quote/{ticker}",
            "fundamentals": f"https://finance.yahoo.com/quote/{ticker}/key-statistics",
            "official_filings": f"https://www.sec.gov/edgar/search/#/q={ticker}",
            "macro": "Yahoo Finance: ^VIX / ^TNX / DX-Y.NYB / ^IRX",
        },
        "limitations": [
            "SEC 10-K/10-Q 已自动抓取候选原文并抽取前段文本；完整 XBRL/表格指标后续可继续增强。",
            "一致预期、目标价、13F 变化尚未自动采集；报告中不得编造这些字段。",
        ],
    }


def _collect_cn_data(ticker: str) -> dict:
    out: dict = {
        "symbol": ticker,
        "market": "CN",
        "currency": "CNY",
        "as_of": dt.date.today().isoformat(),
        "quote": {},
        "fundamentals": {},
        "sources": {
            "quote_primary": f"https://quote.eastmoney.com/{'sh' if ticker.startswith('6') else 'sz'}{ticker}.html",
            "official_filings": "http://www.cninfo.com.cn",
            "macro": "中国债券信息网 / SHIBOR / PBOC",
        },
        "limitations": [
            "A 股完整财报、估值分位、北向资金和宏观数据尚未全部自动采集；缺失项必须列为待补充。",
        ],
    }
    if ak is None:
        out["limitations"].append("akshare 不可用，无法执行 A 股在线取数。")
        return out
    try:
        spot = ak.stock_zh_a_spot_em()
        if spot is not None and not spot.empty and "代码" in spot.columns:
            row = spot[spot["代码"].astype(str) == ticker]
            if not row.empty:
                r = row.iloc[0]
                out["quote"] = {
                    "name": r.get("名称"),
                    "price": _safe_float(r.get("最新价")),
                    "change_pct": _safe_float(r.get("涨跌幅")),
                    "volume_cny_mn": _safe_float(r.get("成交额")),
                    "pe_ttm": _safe_float(r.get("市盈率-动态")),
                    "pb": _safe_float(r.get("市净率")),
                }
    except Exception as exc:
        out["limitations"].append(f"A 股行情抓取失败: {exc}")
    out["official_filings"] = _fetch_cn_official_filings(ticker)
    return out


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


def _fetch_sec_filings(ticker: str) -> dict:
    """Fetch latest 10-K/10-Q metadata and text snippets from official SEC EDGAR."""
    out = {
        "source": "SEC EDGAR",
        "status": "not_found",
        "company_name": None,
        "cik": None,
        "filings": [],
        "notes": [],
    }
    try:
        mapping = _http_get_json("https://www.sec.gov/files/company_tickers.json")
        target = ticker.upper().replace("-", ".")
        match = None
        for item in mapping.values():
            if str(item.get("ticker", "")).upper() == target:
                match = item
                break
        if not match:
            out["notes"].append("SEC company_tickers.json 未匹配到该 ticker。")
            return out

        cik = str(match["cik_str"]).zfill(10)
        out["cik"] = cik
        out["company_name"] = match.get("title")
        submissions = _http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])

        filings = []
        for form, accession, doc, filing_date in zip(forms, accessions, docs, dates):
            if form not in {"10-K", "10-Q", "20-F", "40-F"}:
                continue
            accession_nodash = accession.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{doc}"
            snippet = _extract_html_snippet(url)
            filings.append(
                {
                    "form": form,
                    "filing_date": filing_date,
                    "accession": accession,
                    "url": url,
                    "text_snippet": snippet,
                }
            )
            if len(filings) >= 3:
                break
        out["filings"] = filings
        out["status"] = "ok" if filings else "empty"
    except Exception as exc:
        out["status"] = "error"
        out["notes"].append(str(exc))
    return out


def _extract_html_snippet(url: str, max_chars: int = 5000) -> str | None:
    try:
        html = _http_get_text(url)
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "ix:header", "ix:hidden"]):
            tag.decompose()
        text = soup.get_text("\n")
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        clean = "\n".join(line for line in lines if len(line) >= 20)
        return clean[:max_chars] if clean else None
    except Exception:
        return None


def _fetch_hk_official_filings(ticker: str) -> dict:
    """Best-effort HKEX official filing locator.

    HKEX annual reports are usually PDFs behind search pages. The backend
    provides official search URLs and supplements with Eastmoney financial
    statements, while avoiding fake parsed values when a PDF cannot be read.
    """
    out = {
        "source": "HKEXnews",
        "status": "search_link_only",
        "company_code": ticker,
        "official_search_url": (
            "https://www1.hkexnews.hk/search/titlesearch.xhtml"
            f"?lang=zh&market=SEHK&stockId={ticker.lstrip('0')}"
        ),
        "financial_statement_snapshots": {},
        "notes": ["HKEX PDF 正文暂未自动下载/解析；请以 official_search_url 人工核验最新年报/中报。"],
    }
    if ak is None:
        out["notes"].append("akshare 不可用，无法补充东方财富港股三大报表。")
        return out
    try:
        for statement in ["资产负债表", "利润表", "现金流量表"]:
            df = ak.stock_financial_hk_report_em(stock=ticker, symbol=statement, indicator="年度")
            if df is None or df.empty:
                continue
            out["financial_statement_snapshots"][statement] = df.head(5).to_dict(orient="records")
        if out["financial_statement_snapshots"]:
            out["status"] = "supplemented"
            out["notes"].append("已补充东方财富港股财务报表快照，非官方源，仅用于辅助。")
    except Exception as exc:
        out["notes"].append(f"东方财富港股财报快照抓取失败: {exc}")
    return out


def _fetch_cn_official_filings(ticker: str) -> dict:
    out = {
        "source": "巨潮资讯 CNINFO",
        "status": "empty",
        "company_code": ticker,
        "filings": [],
        "official_search_url": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "notes": [],
    }
    if ak is None:
        out["notes"].append("akshare 不可用，无法查询巨潮资讯公告。")
        return out
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * 3)
    filings = []
    for category in ["年报", "半年报", "一季报", "三季报"]:
        try:
            df = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=ticker,
                market="沪深京",
                category=category,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            if df is None or df.empty:
                continue
            for _, row in df.head(3).iterrows():
                filings.append({k: str(v) for k, v in row.to_dict().items()})
        except Exception as exc:
            out["notes"].append(f"{category} 查询失败: {exc}")
    out["filings"] = filings[:8]
    out["status"] = "ok" if filings else "empty"
    return out


def _safe_float(value) -> float | None:
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _build_analysis_prompt(
    doc_id: int,
    message: str,
    symbols: list[str],
    market_data: dict,
    provider_name: str,
) -> str:
    symbol_text = ", ".join(symbols) if symbols else "用户未单独填写，请从请求中识别"
    skill_context = _read_skill_context()
    data_json = json.dumps(market_data, ensure_ascii=False, indent=2)
    return f"""
你是 AlphaLens 后端的 {provider_name} 投资分析执行器。你必须严格按照下方 value-stock-decider skill 内容做个股价值投资决策分析。

任务类型：个股价值投资决策分析。
文档 ID：{doc_id}
标的代码：{symbol_text}

用户请求：
{message}

value-stock-decider skill 内容：
{skill_context}

后端已联网采集的最新结构化数据（必须优先使用）：
```json
{data_json}
```

执行要求：
1. 必须使用 value-stock-decider 的工作流和 Shawn 价值投资框架。
2. 必须优先基于“后端已联网采集的最新结构化数据”生成报告，并引用其中的 sources。
3. 对后端 limitations 和缺失字段，必须在“数据来源与待补充”中列出；严禁编造未采集到的实时股价、财报、目标价、13F、南向/北向持仓等数据。
4. 必须在“最新数据快照”或“数据来源与待补充”中单独说明 official_filings：
   - SEC / 巨潮获取到的公告可视为官方源；
   - HKEX 如果只有 official_search_url 而没有正文片段，必须说明“已定位官方入口但未解析 PDF 正文”；
   - 东方财富/Yahoo/Futu 只能作为第三方补充源。
5. 对关键估值指标，如果只有单一来源，必须标注“单源，需二次交叉验证”。
6. 不下单、不提交表单、不上传数据，不替用户做最终决定。
7. 如果缺少持仓成本、投资期限或输出深度，就在报告中列为“待用户补充”，不要中断任务。
8. 直接输出最终中文 Markdown 报告，不要输出“我将开始”“Step 1”“读取文件”等过程说明，不要输出 `$line_file` 或任何模板占位符。
9. 报告必须包含这些标题：
   # 结论摘要
   # 投资决策
   # 最新数据快照
   # 质量筛选
   # 估值筛选
   # 执行筛选
   # 三档场景
   # 关键风险
   # 数据来源与待补充
10. “投资决策”里必须明确：买入/持有/卖出/等待，买入价区间，安全边际，仓位建议，止盈止损或复盘触发条件。
11. 如果因为缺少实时数据无法给出可靠买入价，必须给出估值方法和待补数据清单，而不是假装精确。
""".strip()


def _sanitize_report(markdown: str) -> str:
    lines = [line for line in markdown.splitlines() if "$line_file" not in line]
    text = "\n".join(lines).strip()
    report_match = re.search(r"(?m)^#\s+.+报告\s*$", text)
    if report_match:
        text = text[report_match.start():].strip()
    else:
        section_match = re.search(r"(?m)^#{1,6}\s+(?:\d+[.、]\s*)?结论摘要\s*$", text)
        if section_match:
            text = text[section_match.start():].strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_section(markdown: str, title: str) -> str | None:
    heading_re = re.compile(r"^(#{1,6})\s+(?:\d+[.、]\s*)?(.+?)\s*$")
    lines = markdown.splitlines()
    start_idx: int | None = None
    start_level = 0

    for idx, line in enumerate(lines):
        match = heading_re.match(line.strip())
        if not match:
            continue
        heading_text = re.sub(r"[*_`#]+", "", match.group(2)).strip()
        if heading_text == title:
            start_idx = idx + 1
            start_level = len(match.group(1))
            break

    if start_idx is None:
        return None

    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        match = heading_re.match(lines[idx].strip())
        if match and len(match.group(1)) <= start_level:
            end_idx = idx
            break

    body = "\n".join(lines[start_idx:end_idx]).strip()
    return body[:2000] if body else None
