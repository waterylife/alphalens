"""Configurable portfolio targets and Gemini-based allocation review."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from backend.portfolio import db
from backend.strategy.llm import call_gemini


DEFAULT_TARGETS: list[dict[str, Any]] = [
    {
        "category_l1": "现金",
        "category_l2": "现金-国内",
        "target_weight_pct": 2.0,
        "target_market_value_cny": 32619.41,
        "role_positioning": "日常流动性 + 终极备胎",
    },
    {
        "category_l1": "现金",
        "category_l2": "现金-海外",
        "target_weight_pct": 12.0,
        "target_market_value_cny": 195716.46,
        "role_positioning": "日常流动性 + 终极备胎",
        "expected_asset_return_pct": 1.0,
        "expected_total_return_pct": 0.12,
        "optimistic_asset_return_pct": 1.0,
        "optimistic_total_return_pct": 0.12,
        "pessimistic_asset_return_pct": 1.0,
        "pessimistic_total_return_pct": 0.12,
    },
    {
        "category_l1": "债券",
        "category_l2": "纯债-中国（中短债）",
        "target_weight_pct": 30.0,
        "target_market_value_cny": 489291.15,
        "role_positioning": "核心弹药库（随时可调用）",
        "expected_asset_return_pct": 2.5,
        "expected_total_return_pct": 0.75,
        "optimistic_asset_return_pct": 2.5,
        "optimistic_total_return_pct": 0.75,
        "pessimistic_asset_return_pct": -1.0,
        "pessimistic_total_return_pct": -0.3,
    },
    {
        "category_l1": "债券",
        "category_l2": "纯债-美国国债",
        "target_weight_pct": 8.0,
        "target_market_value_cny": 130477.64,
        "role_positioning": "美元防御 + 海外弹药",
        "expected_asset_return_pct": 4.0,
        "expected_total_return_pct": 0.32,
        "optimistic_asset_return_pct": 4.0,
        "optimistic_total_return_pct": 0.32,
        "pessimistic_asset_return_pct": 0.0,
        "pessimistic_total_return_pct": 0.0,
    },
    {
        "category_l1": "债券",
        "category_l2": "混合债券",
        "target_weight_pct": 8.0,
        "target_market_value_cny": 130477.64,
        "role_positioning": "战术观察哨（市场灵敏度）",
        "expected_asset_return_pct": 4.0,
        "expected_total_return_pct": 0.32,
        "optimistic_asset_return_pct": 5.0,
        "optimistic_total_return_pct": 0.4,
        "pessimistic_asset_return_pct": -6.0,
        "pessimistic_total_return_pct": -0.48,
    },
    {
        "category_l1": "权益",
        "category_l2": "沪深红利",
        "target_weight_pct": 25.0,
        "target_market_value_cny": 407742.62,
        "role_positioning": "核心价值仓（压舱石）",
        "expected_asset_return_pct": 6.0,
        "expected_total_return_pct": 1.5,
        "optimistic_asset_return_pct": 15.0,
        "optimistic_total_return_pct": 3.75,
        "pessimistic_asset_return_pct": -20.0,
        "pessimistic_total_return_pct": -5.0,
    },
    {
        "category_l1": "权益",
        "category_l2": "美股 XLU 红利",
        "target_weight_pct": 9.0,
        "target_market_value_cny": 146787.34,
        "role_positioning": "核心价值仓（压舱石）",
        "expected_asset_return_pct": 7.0,
        "expected_total_return_pct": 0.63,
        "optimistic_asset_return_pct": 20.0,
        "optimistic_total_return_pct": 1.8,
        "pessimistic_asset_return_pct": -8.0,
        "pessimistic_total_return_pct": -0.72,
    },
    {
        "category_l1": "权益",
        "category_l2": "沪深观察仓（宽基+消费）",
        "target_weight_pct": 3.0,
        "target_market_value_cny": 48929.11,
        "role_positioning": "A股信标（等待加仓信号）",
        "expected_asset_return_pct": 7.0,
        "expected_total_return_pct": 0.21,
        "optimistic_asset_return_pct": 10.0,
        "optimistic_total_return_pct": 0.3,
        "pessimistic_asset_return_pct": -25.0,
        "pessimistic_total_return_pct": -0.75,
    },
    {
        "category_l1": "权益",
        "category_l2": "美股宽基",
        "target_weight_pct": 0.0,
        "target_market_value_cny": 0.0,
        "role_positioning": "等待建仓信号",
        "expected_total_return_pct": 0.0,
        "optimistic_total_return_pct": 0.0,
        "pessimistic_total_return_pct": 0.0,
    },
    {
        "category_l1": "权益",
        "category_l2": "港股科技",
        "target_weight_pct": 3.0,
        "target_market_value_cny": 48929.11,
        "role_positioning": "弹性卫星（博取超额收益）",
        "expected_asset_return_pct": 10.0,
        "expected_total_return_pct": 0.3,
        "optimistic_asset_return_pct": 15.0,
        "optimistic_total_return_pct": 0.45,
        "pessimistic_asset_return_pct": -30.0,
        "pessimistic_total_return_pct": -0.9,
    },
    {
        "category_l1": "权益",
        "category_l2": "美股科技",
        "target_weight_pct": 0.0,
        "target_market_value_cny": 0.0,
        "role_positioning": "等待建仓信号",
        "expected_total_return_pct": 0.0,
        "optimistic_total_return_pct": 0.0,
        "pessimistic_total_return_pct": 0.0,
    },
    {
        "category_l1": "黄金",
        "category_l2": "上海金",
        "target_weight_pct": 2.0,
        "target_market_value_cny": 32619.41,
        "role_positioning": "尾部风险对冲",
        "expected_asset_return_pct": 5.0,
        "expected_total_return_pct": 0.1,
        "optimistic_asset_return_pct": 15.0,
        "optimistic_total_return_pct": 0.3,
        "pessimistic_asset_return_pct": -40.0,
        "pessimistic_total_return_pct": -0.8,
    },
]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_default_targets() -> None:
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM portfolio_targets").fetchone()[0]
        if count:
            return
        now = _now()
        for idx, row in enumerate(DEFAULT_TARGETS):
            conn.execute(
                """
                INSERT INTO portfolio_targets(
                    category_l1, category_l2, target_weight_pct, target_market_value_cny,
                    role_positioning, expected_asset_return_pct, expected_total_return_pct,
                    optimistic_asset_return_pct, optimistic_total_return_pct,
                    pessimistic_asset_return_pct, pessimistic_total_return_pct,
                    sort_order, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["category_l1"],
                    row["category_l2"],
                    row["target_weight_pct"],
                    row.get("target_market_value_cny"),
                    row.get("role_positioning"),
                    row.get("expected_asset_return_pct"),
                    row.get("expected_total_return_pct"),
                    row.get("optimistic_asset_return_pct"),
                    row.get("optimistic_total_return_pct"),
                    row.get("pessimistic_asset_return_pct"),
                    row.get("pessimistic_total_return_pct"),
                    idx,
                    now,
                ),
            )


def list_targets() -> list[dict[str, Any]]:
    ensure_default_targets()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_targets ORDER BY sort_order, id"
        ).fetchall()
    return [dict(row) for row in rows]


def replace_targets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _now()
    with db.connect() as conn:
        conn.execute("DELETE FROM portfolio_targets")
        for idx, row in enumerate(rows):
            conn.execute(
                """
                INSERT INTO portfolio_targets(
                    category_l1, category_l2, target_weight_pct, target_market_value_cny,
                    role_positioning, expected_asset_return_pct, expected_total_return_pct,
                    optimistic_asset_return_pct, optimistic_total_return_pct,
                    pessimistic_asset_return_pct, pessimistic_total_return_pct,
                    sort_order, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["category_l1"].strip(),
                    row["category_l2"].strip(),
                    row["target_weight_pct"],
                    row.get("target_market_value_cny"),
                    _blank_to_none(row.get("role_positioning")),
                    row.get("expected_asset_return_pct"),
                    row.get("expected_total_return_pct"),
                    row.get("optimistic_asset_return_pct"),
                    row.get("optimistic_total_return_pct"),
                    row.get("pessimistic_asset_return_pct"),
                    row.get("pessimistic_total_return_pct"),
                    row.get("sort_order", idx),
                    now,
                ),
            )
    return list_targets()


def analyze_targets_with_gemini() -> dict[str, Any]:
    targets = list_targets()
    holdings, total_mv = _current_holdings()
    actuals = _target_actuals(targets, holdings, total_mv)
    prompt = _build_analysis_prompt(targets, holdings, actuals, total_mv)
    conclusion = call_gemini(prompt, max_tokens=3500, temperature=0.2)
    if not conclusion:
        conclusion = (
            "Gemini 暂时不可用，已完成本地目标偏离计算。请检查 GEMINI_API_KEY / GEMINI_MODEL "
            "配置后重试模型分析。优先关注实际占比与目标占比偏离最大的分类，并避免为了贴近目标而在高估区域被动追买。"
        )
    return {
        "as_of": _now(),
        "provider": "gemini",
        "total_market_value_cny": round(total_mv, 2),
        "conclusion": conclusion,
        "actuals": actuals,
    }


def _current_holdings() -> tuple[list[dict[str, Any]], float]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, market, asset_class, tag_l1, tag_l2, name, code, broker,
                   market_value_cny, unrealized_pnl_cny, return_pct
            FROM holdings
            ORDER BY market_value_cny DESC
            """
        ).fetchall()
    holdings = [dict(row) for row in rows]
    total_mv = sum(float(row["market_value_cny"] or 0.0) for row in holdings)
    return holdings, total_mv


def _target_actuals(
    targets: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    total_mv: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for target in targets:
        actual_mv = sum(
            float(row["market_value_cny"] or 0.0)
            for row in holdings
            if _matches_target(row, target)
        )
        actual_weight = (actual_mv / total_mv * 100) if total_mv else 0.0
        target_weight = float(target["target_weight_pct"] or 0.0)
        target_mv = target.get("target_market_value_cny")
        gap_mv = (actual_mv - float(target_mv)) if target_mv is not None else None
        out.append(
            {
                "target_id": int(target["id"]),
                "category_l1": target["category_l1"],
                "category_l2": target["category_l2"],
                "target_weight_pct": round(target_weight, 4),
                "actual_weight_pct": round(actual_weight, 4),
                "gap_pct": round(actual_weight - target_weight, 4),
                "target_market_value_cny": round(float(target_mv), 2) if target_mv is not None else None,
                "actual_market_value_cny": round(actual_mv, 2),
                "gap_market_value_cny": round(gap_mv, 2) if gap_mv is not None else None,
            }
        )
    return out


def _matches_target(holding: dict[str, Any], target: dict[str, Any]) -> bool:
    l1 = str(target["category_l1"])
    l2 = str(target["category_l2"])
    raw_values = [
        str(holding.get("asset_class") or ""),
        str(holding.get("tag_l1") or ""),
        str(holding.get("tag_l2") or ""),
        str(holding.get("market") or ""),
        str(holding.get("name") or ""),
        str(holding.get("code") or ""),
    ]
    values = set(raw_values)
    if l2 in values:
        return True
    target_norm = _match_key(l2)
    value_norms = [_match_key(value) for value in raw_values if value]
    if any(
        target_norm
        and value
        and (target_norm in value or (len(value) >= 4 and value in target_norm))
        for value in value_norms
    ):
        return True
    if any(_keyword_match(target_norm, value) for value in value_norms):
        return True
    if l1 == "现金" and holding.get("asset_class") == "现金":
        market = str(holding.get("market") or "")
        if "国内" in l2:
            return market in {"中国", "CN", "国内", "人民币"}
        if "海外" in l2:
            return market not in {"中国", "CN", "国内", "人民币"}
    if l1 == "黄金":
        return "上海金" in values or "上海金" in str(holding.get("name") or "")
    return False


def _match_key(value: str) -> str:
    value = re.sub(r"[（(].*?[）)]", "", value)
    return re.sub(r"[\s_\-+/]+", "", value).upper()


def _keyword_match(target: str, value: str) -> bool:
    if not target or not value:
        return False
    tokens = re.findall(r"[A-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", target)
    if len(tokens) < 2:
        return False
    hits = sum(1 for token in tokens if token in value)
    return hits >= 2


def _build_analysis_prompt(
    targets: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    actuals: list[dict[str, Any]],
    total_mv: float,
) -> str:
    compact_holdings = [
        {
            "name": row["name"],
            "code": row["code"],
            "market": row["market"],
            "asset_class": row["asset_class"],
            "tag_l1": row["tag_l1"],
            "tag_l2": row["tag_l2"],
            "broker": row["broker"],
            "market_value_cny": round(float(row["market_value_cny"] or 0.0), 2),
            "return_pct": row["return_pct"],
        }
        for row in holdings[:80]
    ]
    return f"""
你是一个价值投资风格的资产配置顾问。请基于用户配置的 Portfolio 目标和当前持仓现状，给出中文优化建议。

原则：
1. 坚持安全边际，不为了贴近目标仓位而追高买入。
2. 区分结构性偏离和可接受的战术偏离。
3. 优先提出可执行、低换手、分批调整的建议。
4. 不得虚构价格、估值或用户未提供的数据；如信息不足，明确说明。
5. 输出不要超过 900 字，结构为：结论摘要、主要偏离、优化建议、风险提醒。

组合总市值 CNY: {round(total_mv, 2)}

目标配置：
{json.dumps(targets, ensure_ascii=False, indent=2)}

目标与现状偏离：
{json.dumps(actuals, ensure_ascii=False, indent=2)}

当前持仓明细（按市值前 80）：
{json.dumps(compact_holdings, ensure_ascii=False, indent=2)}
""".strip()


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value
