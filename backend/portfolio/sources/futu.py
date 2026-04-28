"""Futu OpenD adapter — fetches portfolio positions + cash/fund/bond aggregates.

Connects to a locally running OpenD daemon (default 127.0.0.1:11111) and
returns positions normalized into the dict shape `service.sync_futu` expects.

Two streams of data are merged:

1. ``position_list_query`` — individual stock/ETF/single-name bond positions.
   These come back per security with current price, avg cost, qty, P&L,
   currency and a venue prefix code like ``HK.09988`` or ``US.NVDA``.

2. ``accinfo_query`` — account-level aggregates. We use ``fund_assets`` (money
   market funds, e.g. 港元/美元货币基金) and ``bond_assets`` (e.g. 美国中长期国债)
   because Futu doesn't expose those as ticker-style positions but they are
   real money the user holds at this broker. We emit synthetic "positions"
   for each so the UI shows total Futu = sum of all rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Lazy imports happen inside fetch() so importing this module doesn't require
# the futu SDK to be installed (helps tests/CI on machines without OpenD).


@dataclass
class FutuPosition:
    market: str             # 香港 / 美国 / 中国
    code: str | None        # normalized (HK 5-digit, US uppercase ticker, None for synthetics)
    name: str
    currency: str           # HKD / USD / CNY
    quantity: float | None
    cost_price: float | None
    current_price: float | None
    market_value_native: float
    cost_value_native: float | None
    unrealized_pnl_native: float | None
    return_pct: float | None
    asset_class_hint: str   # 股票 / 债券 / 现金 — used only for newly-inserted rows


# ---- code normalization ------------------------------------------------

def _strip_market_prefix(code: str) -> tuple[str, str]:
    """'HK.09988' -> ('HK', '09988'). 'US.NVDA' -> ('US', 'NVDA')."""
    if "." in code:
        prefix, ticker = code.split(".", 1)
        return prefix, ticker
    return "", code


def _market_label(prefix: str) -> str:
    return {"HK": "香港", "US": "美国", "CN": "中国", "SH": "中国", "SZ": "中国"}.get(
        prefix, prefix
    )


def normalize_code(raw: str) -> tuple[str, str]:
    """Returns (market_label, normalized_code). HK keeps leading zeros (5-digit)."""
    prefix, ticker = _strip_market_prefix(raw)
    return _market_label(prefix), ticker


def codes_match(a: str | None, b: str | None) -> bool:
    """Loose match — strips leading zeros so '9988' == '09988' for HK."""
    if not a or not b:
        return False
    return a.lstrip("0").upper() == b.lstrip("0").upper()


# ---- main entrypoint ---------------------------------------------------

def fetch() -> list[FutuPosition]:
    """Connect to OpenD, return all positions + synthetic fund/bond rows.

    Raises ConnectionError if OpenD isn't reachable; ValueError if the API
    returns an error code; no special handling for empty accounts (returns []).
    """
    try:
        from futu import (
            OpenSecTradeContext,
            TrdEnv,
            TrdMarket,
            RET_OK,
            SecurityFirm,
        )
    except ImportError as e:
        raise RuntimeError(
            "futu SDK not installed. Run: pip install futu-api"
        ) from e

    host = os.environ.get("FUTU_OPEND_HOST", "127.0.0.1")
    port = int(os.environ.get("FUTU_OPEND_PORT", "11111"))

    try:
        trd = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.HK,
            host=host,
            port=port,
            security_firm=SecurityFirm.FUTUSECURITIES,
        )
    except Exception as e:
        raise ConnectionError(
            f"Cannot connect to Futu OpenD at {host}:{port}: {e}"
        ) from e

    try:
        ret, positions_df = trd.position_list_query(trd_env=TrdEnv.REAL)
        if ret != RET_OK:
            raise ValueError(f"position_list_query failed: {positions_df}")

        ret, info_df = trd.accinfo_query(trd_env=TrdEnv.REAL)
        if ret != RET_OK:
            raise ValueError(f"accinfo_query failed: {info_df}")

        out: list[FutuPosition] = []
        for _, r in positions_df.iterrows():
            out.append(_position_from_row(r))

        out.extend(_synthetics_from_accinfo(info_df.iloc[0].to_dict()))
        return out
    finally:
        try:
            trd.close()
        except Exception:
            pass


def _position_from_row(r: Any) -> FutuPosition:
    market, code = normalize_code(str(r["code"]))
    qty = float(r["qty"])
    avg_cost = float(r["average_cost"]) if r.get("cost_price_valid", True) else None
    px = float(r["nominal_price"])
    mv = float(r["market_val"])
    pl_val = float(r["pl_val"]) if r.get("pl_val_valid", True) else None
    return_pct = (
        float(r["pl_ratio_avg_cost"]) if r.get("pl_ratio_valid", True) else None
    )
    cost_value = (qty * avg_cost) if avg_cost is not None else None

    return FutuPosition(
        market=market,
        code=code,
        name=str(r["stock_name"]),
        currency=str(r["currency"]),
        quantity=qty,
        cost_price=avg_cost,
        current_price=px,
        market_value_native=mv,
        cost_value_native=cost_value,
        unrealized_pnl_native=pl_val,
        return_pct=return_pct,
        asset_class_hint="股票",
    )


def _synthetics_from_accinfo(info: dict) -> list[FutuPosition]:
    """accinfo aggregates are denominated in the account's base currency.

    For a typical Futu HK account the base is HKD. We tag the synthetic rows
    accordingly so the FX layer converts them correctly into CNY.
    """
    base_ccy = str(info.get("currency", "HKD"))
    out: list[FutuPosition] = []

    fund_assets = float(info.get("fund_assets") or 0.0)
    if fund_assets > 0:
        out.append(FutuPosition(
            market="香港" if base_ccy == "HKD" else "美国",
            code=None,
            name="港元/美元货币基金",
            currency=base_ccy,
            quantity=None,
            cost_price=None,
            current_price=None,
            market_value_native=fund_assets,
            cost_value_native=fund_assets,
            unrealized_pnl_native=0.0,
            return_pct=0.0,
            asset_class_hint="现金",
        ))

    bond_assets = float(info.get("bond_assets") or 0.0)
    if bond_assets > 0:
        out.append(FutuPosition(
            market="美国",
            code=None,
            name="美国中长期国债",
            currency=base_ccy,
            quantity=None,
            cost_price=None,
            current_price=None,
            market_value_native=bond_assets,
            cost_value_native=bond_assets,
            unrealized_pnl_native=0.0,
            return_pct=0.0,
            asset_class_hint="债券",
        ))

    return out
