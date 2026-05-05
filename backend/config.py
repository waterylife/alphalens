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
    tr_csindex_symbol: str | None  # csindex total-return counterpart (for deriving long-history DY)
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
        tr_csindex_symbol="H00922",
        lg_symbol=None,
        description="沪深两市股息率最高、分红最稳定的100只股票，股息率加权",
    ),
    "930955": IndexConfig(
        code="930955",
        name="红利低波100",
        full_name="中证红利低波动100指数",
        exchange="sh",
        tx_symbol="sh930955",
        csindex_symbol="930955",
        tr_csindex_symbol="H20955",
        lg_symbol=None,
        description="流动性好、连续分红、股息率高、波动较低的100只股票",
    ),
    "931233": IndexConfig(
        code="931233",
        name="港股通央企红利",
        full_name="中证港股通央企红利指数",
        exchange="sh",
        tx_symbol="sh931233",
        csindex_symbol="931233",
        tr_csindex_symbol=None,  # no csindex total-return counterpart published
        lg_symbol=None,
        description="港股通范围内央企背景、股息率较高的股票，反映央企红利资产表现",
    ),
    "SCHD": IndexConfig(
        code="SCHD",
        name="SCHD",
        full_name="Schwab U.S. Dividend Equity ETF",
        exchange="us",
        tx_symbol="SCHD",
        csindex_symbol="",
        tr_csindex_symbol=None,
        lg_symbol=None,
        description="美国高股息 ETF，跟踪 Dow Jones U.S. Dividend 100 Index，覆盖具备持续分红能力的美股公司",
    ),
}


def get_index(code: str) -> IndexConfig:
    if code not in DIVIDEND_INDICES:
        raise KeyError(f"Index {code} is not supported. Available: {list(DIVIDEND_INDICES)}")
    return DIVIDEND_INDICES[code]


# ------------------------------ Benchmarks ------------------------------


@dataclass(frozen=True)
class BenchmarkConfig:
    code: str
    name: str
    tx_symbol: str


BENCHMARKS: dict[str, BenchmarkConfig] = {
    "000300": BenchmarkConfig(code="000300", name="沪深300", tx_symbol="sh000300"),
    "000985": BenchmarkConfig(code="000985", name="中证全指", tx_symbol="sh000985"),
    "000016": BenchmarkConfig(code="000016", name="上证50", tx_symbol="sh000016"),
    "SPY": BenchmarkConfig(code="SPY", name="SPY 标普500ETF", tx_symbol="SPY"),
}


def get_benchmark(code: str) -> BenchmarkConfig:
    if code not in BENCHMARKS:
        raise KeyError(f"Benchmark {code} is not supported. Available: {list(BENCHMARKS)}")
    return BENCHMARKS[code]
