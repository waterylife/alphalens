"""Supported dividend indices registry.

Each entry declares the akshare symbols needed across the different data
sources we use (Tencent for prices, csindex for valuation + constituents,
legulegu for long-history PE/PB).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexConfig:
    code: str               # 6-digit code, e.g. "000922"
    name: str               # 中文简称
    full_name: str
    exchange: str           # "sh" or "sz"
    tx_symbol: str          # for stock_zh_index_daily_tx, e.g. "sh000922"
    csindex_symbol: str     # for csindex APIs (usually == code)
    lg_symbol: str | None   # legulegu name, None if not supported
    description: str

    @property
    def tradingview_symbol(self) -> str:
        return f"{self.exchange.upper()}:{self.code}"


DIVIDEND_INDICES: dict[str, IndexConfig] = {
    "000922": IndexConfig(
        code="000922",
        name="中证红利",
        full_name="中证红利指数",
        exchange="sh",
        tx_symbol="sh000922",
        csindex_symbol="000922",
        lg_symbol=None,
        description="沪深两市股息率最高、分红最稳定的100只股票，股息率加权",
    ),
    "000015": IndexConfig(
        code="000015",
        name="上证红利",
        full_name="上证红利指数",
        exchange="sh",
        tx_symbol="sh000015",
        csindex_symbol="000015",
        lg_symbol="上证红利",
        description="上海市场现金股息率高、分红稳定的50只股票",
    ),
    "399324": IndexConfig(
        code="399324",
        name="深证红利",
        full_name="深证红利指数",
        exchange="sz",
        tx_symbol="sz399324",
        csindex_symbol="399324",
        lg_symbol="深证红利",
        description="深圳市场分红能力强、分红水平稳定的40只股票",
    ),
    "000825": IndexConfig(
        code="000825",
        name="红利低波",
        full_name="中证红利低波动指数",
        exchange="sh",
        tx_symbol="sh000825",
        csindex_symbol="000825",
        lg_symbol=None,
        description="高股息、低波动50只股票，防御性更强",
    ),
    "930955": IndexConfig(
        code="930955",
        name="红利低波100",
        full_name="中证红利低波动100指数",
        exchange="sh",
        tx_symbol="sh930955",
        csindex_symbol="930955",
        lg_symbol=None,
        description="流动性好、连续分红、股息率高、波动较低的100只股票",
    ),
}


def get_index(code: str) -> IndexConfig:
    if code not in DIVIDEND_INDICES:
        raise KeyError(f"Index {code} is not supported. Available: {list(DIVIDEND_INDICES)}")
    return DIVIDEND_INDICES[code]
