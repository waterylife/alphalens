"""Screenshot → structured holdings via a Vision LLM.

Default backend is MiniMax's chatcompletion_v2 with a vision model. The
adapter is intentionally narrow:

    parse(image_bytes, broker) -> ParsedScreenshot

so swapping in another vision model later (Claude, Qwen-VL, etc.) only means
implementing a new VisionParser class.

The prompt forces the model to emit a strict JSON schema; we still validate
it on the way back and return ``warnings`` for anything fishy. The UI layer
then shows the rows in an editable confirm modal — no row hits the DB until
the user clicks confirm.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ParsedRow:
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


@dataclass
class ParsedScreenshot:
    rows: list[ParsedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""           # raw LLM response, for debugging / audit


class VisionParser(Protocol):
    name: str
    def parse(self, image_bytes: bytes, broker: str, mime: str) -> ParsedScreenshot: ...


# ---- prompt -----------------------------------------------------------

_BROKER_HINTS = {
    "tiantian": (
        "这是天天基金 App 的持仓页截图。每一行通常包含：基金名称、6位基金代码、"
        "持有份额（数量）、成本价、最新净值（current_price）、持仓金额（market_value）、"
        "持仓收益（unrealized_pnl）、收益率。基金代码可能不完整可见，识别不出请置 null。"
    ),
    "eastmoney": (
        "这是东方财富 App/网页的持仓页截图。可能包含 A 股、港股通、ETF、基金。"
        "每行通常有：股票代码（6位）、名称、持仓数量、成本价、现价、市值、浮动盈亏、收益率。"
        "如果是港股通,代码可能是 5 位港股代码。"
    ),
}


_PROMPT_TEMPLATE = """\
你是持仓数据提取助手。请分析截图中的持仓信息，并仅以严格 JSON 格式输出。
不要输出任何解释、Markdown 代码围栏或其它文字——只输出一个 JSON 对象。

上下文：{hint}

输出 JSON Schema：
{{
  "rows": [
    {{
      "name": "<标的中文名或代码>",
      "code": "<代码,识别不到则 null>",
      "quantity": <数字或 null,持有份额或股数,无千分位>,
      "cost_price": <数字或 null,成本价>,
      "current_price": <数字或 null,现价或最新净值>,
      "market_value": <数字,持仓金额或市值,单位元>,
      "cost_value": <数字或 null,持仓成本>,
      "unrealized_pnl": <数字或 null,浮动盈亏,亏损为负>,
      "return_pct": <数字或 null,收益率百分数,如 3.5 表示 3.5%,亏损为负>,
      "currency": "CNY|HKD|USD"
    }}
  ],
  "warnings": ["遇到不确定字段时在此简要说明,无则空数组"]
}}

约束：
- 数字必须是裸数字,不要带 ¥/¥/% 或千分位逗号
- 识别不出的字段填 null,严禁瞎猜
- 一张图里所有可见持仓行都要输出,被遮挡看不全的行不要输出
- 货币默认 CNY,除非明显是港股或美股
"""


# ---- MiniMax implementation -------------------------------------------

class MiniMaxVisionParser:
    name = "minimax"

    """Calls MiniMax chatcompletion_v2 with a vision-capable model.

    Image is sent inline as base64 data URL — keeps the image local and
    avoids needing a public URL. MiniMax accepts up to 20 MB; we soft-cap
    at 10 MB to stay well under and reduce latency.
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model or os.environ.get("MINIMAX_VISION_MODEL", "MiniMax-VL-01")
        self.host = (host or os.environ.get("MINIMAX_API_HOST", "https://api.minimaxi.com")).rstrip("/")
        self.timeout = timeout

    def parse(self, image_bytes: bytes, broker: str, mime: str) -> ParsedScreenshot:
        if len(image_bytes) > 10 * 1024 * 1024:
            raise ValueError(f"图片过大 ({len(image_bytes)/1e6:.1f}MB),请压缩到 10MB 以下")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"

        hint = _BROKER_HINTS.get(broker, "这是一张证券或基金持仓截图。")
        prompt = _PROMPT_TEMPLATE.format(hint=hint)

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0.1,
        }

        url = f"{self.host}/v1/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise RuntimeError(
                f"MiniMax API 返回 {resp.status_code}: {resp.text[:300]}"
            )

        payload = resp.json()
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"MiniMax 响应格式异常: {payload}") from e

        return _parse_llm_text(text)


# ---- Gemini implementation --------------------------------------------

# JSON schema enforced via Gemini's responseSchema. Mirrors ParsedRow.
# Gemini's schema uses uppercase OpenAPI types (STRING/NUMBER/...).
_GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "rows": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name":           {"type": "STRING"},
                    "code":           {"type": "STRING", "nullable": True},
                    "quantity":       {"type": "NUMBER", "nullable": True},
                    "cost_price":     {"type": "NUMBER", "nullable": True},
                    "current_price":  {"type": "NUMBER", "nullable": True},
                    "market_value":   {"type": "NUMBER", "nullable": True},
                    "cost_value":     {"type": "NUMBER", "nullable": True},
                    "unrealized_pnl": {"type": "NUMBER", "nullable": True},
                    "return_pct":     {"type": "NUMBER", "nullable": True},
                    "currency":       {"type": "STRING"},
                },
                "required": ["name", "currency"],
            },
        },
        "warnings": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["rows", "warnings"],
}


class GeminiVisionParser:
    name = "gemini"

    """Calls Google Gemini's generateContent with a vision-capable model.

    Uses ``responseMimeType: application/json`` + a strict ``responseSchema``
    so the model is forced to emit JSON conforming to the ParsedRow shape —
    no markdown fence stripping needed downstream.
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model or os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
        self.host = (
            host or os.environ.get(
                "GEMINI_API_HOST", "https://generativelanguage.googleapis.com"
            )
        ).rstrip("/")
        self.timeout = timeout

    def parse(self, image_bytes: bytes, broker: str, mime: str) -> ParsedScreenshot:
        if len(image_bytes) > 10 * 1024 * 1024:
            raise ValueError(f"图片过大 ({len(image_bytes)/1e6:.1f}MB),请压缩到 10MB 以下")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        hint = _BROKER_HINTS.get(broker, "这是一张证券或基金持仓截图。")
        prompt = _PROMPT_TEMPLATE.format(hint=hint)

        body = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": mime, "data": b64}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": _GEMINI_RESPONSE_SCHEMA,
            },
        }

        url = (
            f"{self.host}/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url, json=body, headers={"Content-Type": "application/json"}
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Gemini API 返回 {resp.status_code}: {resp.text[:300]}"
            )

        payload = resp.json()
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            # Gemini returned no candidates — surface the prompt/safety
            # feedback so the caller knows why.
            feedback = payload.get("promptFeedback") or payload
            raise RuntimeError(f"Gemini 响应缺少 candidates: {feedback}") from e

        return _parse_llm_text(text)


# ---- response parsing -------------------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_llm_text(text: str) -> ParsedScreenshot:
    """Best-effort: strip markdown fences, parse JSON, coerce types."""
    candidate = text.strip()
    m = _JSON_FENCE.search(candidate)
    if m:
        candidate = m.group(1)
    else:
        # If the model added prose, find the outermost {...}
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]

    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as e:
        return ParsedScreenshot(
            warnings=[f"无法解析 LLM 输出为 JSON: {e}"],
            raw_text=text,
        )

    rows = []
    warnings: list[str] = list(obj.get("warnings") or [])
    for r in obj.get("rows", []) or []:
        try:
            rows.append(ParsedRow(
                name=str(r.get("name", "")).strip(),
                code=_as_str(r.get("code")),
                quantity=_as_float(r.get("quantity")),
                cost_price=_as_float(r.get("cost_price")),
                current_price=_as_float(r.get("current_price")),
                market_value=_as_float(r.get("market_value")),
                cost_value=_as_float(r.get("cost_value")),
                unrealized_pnl=_as_float(r.get("unrealized_pnl")),
                return_pct=_as_float(r.get("return_pct")),
                currency=str(r.get("currency") or "CNY").upper(),
            ))
        except Exception as e:
            warnings.append(f"忽略一行,解析失败: {e}: {r}")

    if not rows:
        warnings.append("LLM 未返回任何持仓行,请确认截图清晰、内容完整")

    return ParsedScreenshot(rows=rows, warnings=warnings, raw_text=text)


def _as_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() != "null" else None


def _as_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---- factory ----------------------------------------------------------

def get_parser() -> VisionParser:
    """Pick a vision parser based on which API key is available.

    Preference order:
      1. ``VISION_PROVIDER`` env override (`gemini` / `minimax`)
      2. Gemini, if ``GEMINI_API_KEY`` is set
      3. MiniMax, if ``MINIMAX_API_KEY`` is set
    """
    forced = os.environ.get("VISION_PROVIDER", "").lower().strip()

    gemini_key = os.environ.get("GEMINI_API_KEY")
    minimax_key = os.environ.get("MINIMAX_API_KEY")

    if forced == "gemini":
        if not gemini_key:
            raise RuntimeError("VISION_PROVIDER=gemini 但 GEMINI_API_KEY 未设置")
        return GeminiVisionParser(api_key=gemini_key)
    if forced == "minimax":
        if not minimax_key:
            raise RuntimeError("VISION_PROVIDER=minimax 但 MINIMAX_API_KEY 未设置")
        return MiniMaxVisionParser(api_key=minimax_key)

    if gemini_key:
        return GeminiVisionParser(api_key=gemini_key)
    if minimax_key:
        return MiniMaxVisionParser(api_key=minimax_key)

    raise RuntimeError(
        "未配置视觉模型 API Key。请设置 GEMINI_API_KEY 或 MINIMAX_API_KEY 后重启后端。"
    )
