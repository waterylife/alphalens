"""US equity buy/hold/sell signal engine.

Pure numeric rules on 4 dimensions → score 0-100 → action.
LLM rationale via backend.strategy.llm (MiniMax M2) with template fallback.
"""

from __future__ import annotations

from typing import Any

from backend.data import us_client
from backend.data.cache import cache
from backend.strategy.llm import cached_rationale

TTL_SIGNAL = 60 * 30       # 30 min for numeric signal (intraday-ish)


# ─────────────────────────── Scoring ───────────────────────────


def _valuation_score(f: dict[str, Any]) -> tuple[float, list[str]]:
    """0-35. Lower PE / PEG < 1 / reasonable P/S → higher score."""
    triggers: list[str] = []
    score = 0.0
    pe = f.get("pe_ttm")
    fwd = f.get("forward_pe")
    peg = f.get("peg")
    ps = f.get("ps_ttm")

    # PE TTM absolute ranges (rough): <20 cheap / 20-35 fair / >35 rich
    if pe is not None:
        if pe < 20:
            score += 12; triggers.append(f"PE {pe:.1f} 低位")
        elif pe < 35:
            score += 7
        elif pe < 60:
            score += 3
        else:
            triggers.append(f"PE {pe:.1f} 偏高")

    # Forward PE — similar but a bit more forgiving
    if fwd is not None:
        if fwd < 18:
            score += 10; triggers.append(f"Fwd PE {fwd:.1f} 便宜")
        elif fwd < 30:
            score += 6
        elif fwd < 50:
            score += 2

    # PEG < 1 classic
    if peg is not None:
        if peg < 1:
            score += 8; triggers.append(f"PEG {peg:.2f} < 1")
        elif peg < 2:
            score += 4
        else:
            triggers.append(f"PEG {peg:.2f} 偏高")

    # P/S
    if ps is not None:
        if ps < 5:
            score += 5
        elif ps < 15:
            score += 2

    return min(score, 35), triggers


def _momentum_score(t: dict[str, Any]) -> tuple[float, list[str]]:
    """0-30. RSI neutral, trend above MA200, strong 52w position."""
    triggers: list[str] = []
    score = 0.0
    rsi = t.get("rsi14")
    dma = t.get("dist_ma200_pct")
    pos = t.get("pos_52w_pct")

    # RSI — reward oversold, penalize extreme overbought
    if rsi is not None:
        if rsi <= 30:
            score += 12; triggers.append(f"RSI {rsi:.0f} 超卖")
        elif rsi <= 45:
            score += 10
        elif rsi <= 65:
            score += 7
        elif rsi <= 75:
            score += 3
        else:
            triggers.append(f"RSI {rsi:.0f} 超买")

    # Above MA200 is healthy; way above is late-cycle
    if dma is not None:
        if 0 <= dma <= 15:
            score += 10; triggers.append(f"价格位于 MA200 上方 {dma:.1f}%")
        elif 15 < dma <= 30:
            score += 5
        elif dma > 30:
            triggers.append(f"距 MA200 +{dma:.0f}% 乖离过大")
        elif -10 <= dma < 0:
            score += 7; triggers.append(f"距 MA200 {dma:.1f}% 回调机会")
        else:
            score += 2

    # 52w position — middle is best; extremes penalized
    if pos is not None:
        if pos <= 30:
            score += 8; triggers.append(f"52w 位置 {pos:.0f} 低位")
        elif pos <= 70:
            score += 5
        elif pos <= 90:
            score += 2
        else:
            triggers.append(f"52w 位置 {pos:.0f} 接近高点")

    return min(score, 30), triggers


def _quality_score(f: dict[str, Any]) -> tuple[float, list[str]]:
    """0-25. ROE, gross margin, revenue growth."""
    triggers: list[str] = []
    score = 0.0
    roe = f.get("roe_pct")
    gm = f.get("gross_margin_pct")
    rev = f.get("revenue_growth_pct")

    if roe is not None:
        if roe >= 25:
            score += 10; triggers.append(f"ROE {roe:.0f}% 优秀")
        elif roe >= 15:
            score += 7
        elif roe >= 8:
            score += 4
        else:
            triggers.append(f"ROE {roe:.0f}% 偏弱")

    if gm is not None:
        if gm >= 50:
            score += 8; triggers.append(f"毛利率 {gm:.0f}%")
        elif gm >= 35:
            score += 5
        elif gm >= 20:
            score += 2

    if rev is not None:
        if rev >= 20:
            score += 7; triggers.append(f"营收增长 +{rev:.0f}%")
        elif rev >= 10:
            score += 5
        elif rev >= 0:
            score += 2
        else:
            triggers.append(f"营收下滑 {rev:.0f}%")

    return min(score, 25), triggers


def _risk_score(t: dict[str, Any], f: dict[str, Any]) -> tuple[float, list[str]]:
    """0-10. Distance from ATH + beta."""
    triggers: list[str] = []
    score = 0.0
    ath = t.get("dist_ath_pct")  # negative when below ATH
    beta = f.get("beta")

    if ath is not None:
        # Moderate drawdown is healthy entry; shallow = expensive
        if -25 <= ath < -10:
            score += 6; triggers.append(f"距 ATH {ath:.0f}% 合理回撤")
        elif -10 <= ath < -3:
            score += 4
        elif ath >= -3:
            score += 2; triggers.append("接近历史高点")
        else:
            score += 3  # deep drawdown — add some but not too much

    if beta is not None:
        if 0.7 <= beta <= 1.3:
            score += 4
        elif beta > 1.5:
            score += 1; triggers.append(f"Beta {beta:.1f} 高波动")
        else:
            score += 2

    return min(score, 10), triggers


def _macro_overlay(score: float, macro: dict[str, Any] | None) -> tuple[float, list[str]]:
    """Shift score by +/- 5 based on market regime."""
    triggers: list[str] = []
    if not macro:
        return 0, triggers
    vix = macro.get("vix")
    ten = macro.get("us_10y")
    curve = macro.get("curve_2s10s_bps")
    delta = 0.0

    if vix is not None:
        if vix >= 25:
            delta += 4; triggers.append(f"VIX {vix:.0f} 高恐慌，逆向偏多")
        elif vix <= 13:
            delta -= 4; triggers.append(f"VIX {vix:.0f} 低波自满，警惕")

    if ten is not None and ten >= 5:
        delta -= 2; triggers.append(f"10Y {ten:.2f}% 估值承压")

    if curve is not None and curve < 0:
        triggers.append(f"2s10s 倒挂 {curve:.0f}bps")

    return delta, triggers


def _action(score: float) -> str:
    if score >= 65:
        return "buy"
    if score >= 40:
        return "hold"
    return "sell"


# ─────────────────────────── Public API ───────────────────────────


def compute_signal(ticker: str, macro: dict[str, Any] | None = None) -> dict[str, Any]:
    """Numeric buy/hold/sell signal (no LLM call)."""
    empty = {
        "ticker": ticker, "action": "hold", "score": None,
        "components": {}, "triggers": [], "explanation": None,
    }

    def _fetch() -> dict[str, Any]:
        try:
            fund = us_client.fetch_fundamentals(ticker)
            tech = us_client.compute_technicals(ticker)
        except Exception:
            return empty

        v, v_tr = _valuation_score(fund)
        m, m_tr = _momentum_score(tech)
        q, q_tr = _quality_score(fund)
        r, r_tr = _risk_score(tech, fund)
        base = v + m + q + r  # 0-100
        macro_delta, macro_tr = _macro_overlay(base, macro)
        score = max(0, min(100, base + macro_delta))

        return {
            "ticker": ticker,
            "action": _action(score),
            "score": round(score, 1),
            "components": {
                "valuation": round(v, 1),
                "momentum": round(m, 1),
                "quality": round(q, 1),
                "risk": round(r, 1),
                "macro_delta": round(macro_delta, 1),
            },
            "triggers": v_tr + m_tr + q_tr + r_tr + macro_tr,
            "explanation": None,
        }

    try:
        return cache.fetch("us_signal", ticker, TTL_SIGNAL, _fetch)
    except Exception:
        return empty


def _template_rationale(sig: dict[str, Any]) -> str:
    """Deterministic Chinese one-liner from triggers — used when LLM absent."""
    triggers = sig.get("triggers") or []
    action = sig.get("action", "hold")
    action_cn = {"buy": "买入", "hold": "持有", "sell": "卖出"}.get(action, "持有")
    head_cn = {"buy": "📈", "hold": "↔", "sell": "📉"}.get(action, "")
    core = "；".join(triggers[:3]) if triggers else "数据不足"
    return f"{head_cn} {action_cn}：{core}。"


def _llm_rationale(ticker: str, sig: dict[str, Any], fund: dict[str, Any]) -> str | None:
    """Single MiniMax call per ticker — returns Chinese 1-2 sentence rationale."""
    def _build() -> str:
        return (
            f"美股 {ticker} ({fund.get('name') or ''}) 综合评分 {sig.get('score')}/100，"
            f"建议动作: {sig.get('action')}。触发规则: {'; '.join(sig.get('triggers', [])[:8])}。"
            f"分项：估值 {sig['components'].get('valuation')}/35、"
            f"动量 {sig['components'].get('momentum')}/30、"
            f"质量 {sig['components'].get('quality')}/25、"
            f"风险 {sig['components'].get('risk')}/10、"
            f"宏观调整 {sig['components'].get('macro_delta')}。"
            f"请用中文写一句话（<=60字）解释该建议的核心理由，要像专业卖方分析师语气，"
            f"直接给出结论，不要套话、不要免责声明。"
        )

    key = f"{ticker}:{sig.get('action')}:{int((sig.get('score') or 0) // 5)}"
    return cached_rationale("us_signal_llm", key, _build)


def compute_signal_with_rationale(ticker: str, macro: dict[str, Any] | None = None) -> dict[str, Any]:
    sig = compute_signal(ticker, macro)
    try:
        fund = us_client.fetch_fundamentals(ticker)
    except Exception:
        fund = {}
    text = _llm_rationale(ticker, sig, fund)
    if text is None:
        text = _template_rationale(sig)
    out = dict(sig)
    out["explanation"] = text
    return out
