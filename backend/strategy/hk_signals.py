"""HK equity buy/hold/sell signal engine.

Adapted for HK tech — fewer fundamental fields than US (no PEG/ROE/GM/Fwd PE),
but richer flow signals (南向资金/主力净流入/VHSI).

Scoring 0-100:
  Valuation  (0-30) – PE TTM, P/S, P/B
  Momentum   (0-30) – RSI14, dist MA200, 52w position
  Flow       (0-30) – 5d net inflow, 1m return, volume_ratio
  Liquidity  (0-10) – ADTV (absolute), bid-ask spread
  Macro overlay ±5  – VHSI level & southbound direction
Action thresholds identical to US: buy≥65 / hold 40-65 / sell<40.
"""

from __future__ import annotations

from typing import Any

from backend.data import hk_client
from backend.data.cache import cache
from backend.strategy.llm import cached_rationale

TTL_SIGNAL = 60 * 30


# ─────────────────────────── Scoring ───────────────────────────


def _valuation_score(f: dict[str, Any]) -> tuple[float, list[str]]:
    """0-30. PE TTM, PB, PS."""
    triggers: list[str] = []
    score = 0.0
    pe = f.get("pe_ttm")
    pb = f.get("pb")
    ps = f.get("ps_ttm")

    if pe is not None:
        if pe < 15:
            score += 12; triggers.append(f"PE {pe:.1f} 低位")
        elif pe < 25:
            score += 8
        elif pe < 45:
            score += 4
        else:
            triggers.append(f"PE {pe:.1f} 偏高")

    if pb is not None:
        if pb < 1.5:
            score += 10; triggers.append(f"PB {pb:.2f} 低位")
        elif pb < 3:
            score += 6
        elif pb < 6:
            score += 3
        else:
            triggers.append(f"PB {pb:.2f} 偏高")

    if ps is not None:
        if ps < 3:
            score += 8
        elif ps < 8:
            score += 4
        elif ps < 15:
            score += 1

    return min(score, 30), triggers


def _momentum_score(t: dict[str, Any]) -> tuple[float, list[str]]:
    """0-30. RSI, dist MA200, 52w position — mirrors US momentum."""
    triggers: list[str] = []
    score = 0.0
    rsi = t.get("rsi14")
    dma = t.get("dist_ma200_pct")
    pos = t.get("pos_52w_pct")

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


def _flow_score(t: dict[str, Any], r: dict[str, Any]) -> tuple[float, list[str]]:
    """0-30. 5d net inflow (HKD mn), 1m return, volume ratio."""
    triggers: list[str] = []
    score = 0.0
    inflow5 = t.get("net_inflow_5d_hkd_mn")
    today_inflow = t.get("net_inflow_today_hkd_mn")
    vol_ratio = t.get("volume_ratio")
    ret1m = r.get("ret_1m")

    # 5-day net inflow — the stronger signal
    if inflow5 is not None:
        if inflow5 >= 500:
            score += 12; triggers.append(f"5日主力净流入 +{inflow5:.0f}M HKD")
        elif inflow5 >= 100:
            score += 8
        elif inflow5 >= 0:
            score += 4
        elif inflow5 >= -500:
            score += 1
        else:
            triggers.append(f"5日主力净流出 {inflow5:.0f}M HKD")

    # Today's flow — confirmation
    if today_inflow is not None:
        if today_inflow >= 100:
            score += 4; triggers.append(f"今日主力净流入 +{today_inflow:.0f}M HKD")
        elif today_inflow >= 0:
            score += 2
        elif today_inflow < -200:
            triggers.append(f"今日主力净流出 {today_inflow:.0f}M HKD")

    # 1-month momentum (mild weight to avoid chasing)
    if ret1m is not None:
        if ret1m >= 20:
            score += 2; triggers.append(f"近1月 +{ret1m:.0f}% 强势")
        elif ret1m >= 5:
            score += 4
        elif ret1m >= -5:
            score += 3
        elif ret1m >= -15:
            score += 2
        else:
            triggers.append(f"近1月 {ret1m:.0f}% 走弱")

    # Volume ratio — spotlight attention
    if vol_ratio is not None:
        if 1.2 <= vol_ratio <= 2.5:
            score += 4; triggers.append(f"量比 {vol_ratio:.1f} 放量")
        elif vol_ratio > 2.5:
            score += 2; triggers.append(f"量比 {vol_ratio:.1f} 异动")
        elif vol_ratio >= 0.8:
            score += 2

    return min(score, 30), triggers


def _liquidity_score(t: dict[str, Any]) -> tuple[float, list[str]]:
    """0-10. ADTV size + bid-ask spread."""
    triggers: list[str] = []
    score = 0.0
    adtv = t.get("adtv_20d_hkd_mn")
    spread = t.get("bid_ask_spread_bps")

    if adtv is not None:
        if adtv >= 2000:
            score += 6
        elif adtv >= 500:
            score += 4
        elif adtv >= 100:
            score += 2
        else:
            triggers.append(f"ADTV {adtv:.0f}M HKD 流动性偏弱")

    if spread is not None:
        if spread <= 5:
            score += 4
        elif spread <= 15:
            score += 2
        else:
            triggers.append(f"买卖价差 {spread:.0f}bps 较宽")

    return min(score, 10), triggers


def _macro_overlay(
    score: float, macro: dict[str, Any] | None, southbound: dict[str, Any] | None
) -> tuple[float, list[str]]:
    """±5 based on VHSI regime and southbound direction."""
    triggers: list[str] = []
    delta = 0.0
    if macro:
        vhsi = macro.get("vhsi")
        if vhsi is not None:
            if vhsi >= 30:
                delta += 3; triggers.append(f"VHSI {vhsi:.0f} 高恐慌，逆向偏多")
            elif vhsi <= 15:
                delta -= 2; triggers.append(f"VHSI {vhsi:.0f} 低波自满")

        us10 = macro.get("us_10y_yield")
        if us10 is not None and us10 >= 5:
            delta -= 2; triggers.append(f"美10Y {us10:.2f}% 港股估值承压")

    if southbound:
        mtd = southbound.get("net_inflow_mtd_hkd_bn")
        if mtd is not None:
            if mtd >= 30:
                delta += 2; triggers.append(f"南向 MTD +{mtd:.0f}B HKD 强流入")
            elif mtd <= -10:
                delta -= 2; triggers.append(f"南向 MTD {mtd:.0f}B HKD 流出")

    return delta, triggers


def _action(score: float) -> str:
    if score >= 65:
        return "buy"
    if score >= 40:
        return "hold"
    return "sell"


# ─────────────────────────── Public API ───────────────────────────


def compute_signal(
    ticker: str,
    macro: dict[str, Any] | None = None,
    southbound: dict[str, Any] | None = None,
) -> dict[str, Any]:
    empty = {
        "ticker": ticker, "action": "hold", "score": None,
        "components": {}, "triggers": [], "explanation": None,
    }

    def _fetch() -> dict[str, Any]:
        try:
            fund = hk_client.fetch_stock_fundamentals(ticker)
            tech = hk_client.compute_stock_technicals(ticker)
            rets = hk_client.compute_stock_returns(ticker)
        except Exception:
            return empty

        v, v_tr = _valuation_score(fund)
        m, m_tr = _momentum_score(tech)
        fl, fl_tr = _flow_score(tech, rets)
        liq, liq_tr = _liquidity_score(tech)
        base = v + m + fl + liq  # 0-100
        macro_delta, macro_tr = _macro_overlay(base, macro, southbound)
        score = max(0, min(100, base + macro_delta))

        return {
            "ticker": ticker,
            "action": _action(score),
            "score": round(score, 1),
            "components": {
                "valuation": round(v, 1),
                "momentum": round(m, 1),
                "flow": round(fl, 1),
                "liquidity": round(liq, 1),
                "macro_delta": round(macro_delta, 1),
            },
            "triggers": v_tr + m_tr + fl_tr + liq_tr + macro_tr,
            "explanation": None,
        }

    try:
        return cache.fetch("hk_signal", ticker, TTL_SIGNAL, _fetch)
    except Exception:
        return empty


def _template_rationale(sig: dict[str, Any]) -> str:
    triggers = sig.get("triggers") or []
    action = sig.get("action", "hold")
    action_cn = {"buy": "买入", "hold": "持有", "sell": "卖出"}.get(action, "持有")
    head_cn = {"buy": "📈", "hold": "↔", "sell": "📉"}.get(action, "")
    core = "；".join(triggers[:3]) if triggers else "数据不足"
    return f"{head_cn} {action_cn}：{core}。"


def _llm_rationale(ticker: str, sig: dict[str, Any], fund: dict[str, Any]) -> str | None:
    def _build() -> str:
        c = sig.get("components", {})
        return (
            f"港股 {ticker} ({fund.get('name') or ''}) 综合评分 {sig.get('score')}/100，"
            f"建议动作: {sig.get('action')}。触发规则: {'; '.join(sig.get('triggers', [])[:8])}。"
            f"分项：估值 {c.get('valuation')}/30、"
            f"动量 {c.get('momentum')}/30、"
            f"资金流 {c.get('flow')}/30、"
            f"流动性 {c.get('liquidity')}/10、"
            f"宏观调整 {c.get('macro_delta')}。"
            f"请用中文写一句话（<=60字）解释该建议的核心理由，要像专业卖方分析师语气，"
            f"直接给出结论，不要套话、不要免责声明。"
        )

    key = f"{ticker}:{sig.get('action')}:{int((sig.get('score') or 0) // 5)}"
    return cached_rationale("hk_signal_llm", key, _build)


def compute_signal_with_rationale(
    ticker: str,
    macro: dict[str, Any] | None = None,
    southbound: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sig = compute_signal(ticker, macro, southbound)
    try:
        fund = hk_client.fetch_stock_fundamentals(ticker)
    except Exception:
        fund = {}
    text = _llm_rationale(ticker, sig, fund)
    if text is None:
        text = _template_rationale(sig)
    out = dict(sig)
    out["explanation"] = text
    return out
