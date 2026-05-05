# AlphaLens Data Platform OpenAPI

本文档定义 AlphaLens 数据平台的 HTTP 访问协议。目标是让金融市场看板、持仓管理、投资 Agent 和未来外部客户都通过同一套底层取数逻辑访问资产数据。

## 基本约定

- Base URL: `http://127.0.0.1:8000`
- API prefix: `/api/data`
- 协议: HTTP GET + JSON response
- 读写边界: 数据平台接口只读，不执行交易、下单、调仓、赎回、申购等操作。

所有接口统一返回：

```json
{
  "asset": {
    "asset_type": "stock",
    "market": "HK",
    "code": "00700",
    "currency": "HKD",
    "exchange": null,
    "name": null
  },
  "data": {},
  "meta": {
    "source": "yahoo_hk",
    "as_of": "2026-05-05T09:30:00+08:00",
    "fetched_at": "2026-05-05T09:31:00+08:00",
    "freshness": "delayed",
    "confidence": "high",
    "verified_by": [],
    "warnings": []
  }
}
```

## 请求参数

通用参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `market` | 是 | `CN` / `HK` / `US` / `FUND` / `GLOBAL` |
| `code` | 是 | 资产代码，例如 `600519`、`00700`、`AAPL`、`011961` |
| `asset_type` | 否 | `stock` / `fund` / `etf` / `index` / `bond` / `cash` / `unknown` |
| `currency` | 否 | `CNY` / `HKD` / `USD` 等 |
| `freshness` | 部分接口 | `realtime` / `intraday` / `delayed` / `eod` |
| `strategy` | 否 | 逗号分隔的数据源名称，用于显式覆盖默认 provider 链 |
| `verify` | 否 | `true` 时尽量使用备用数据源做交叉验证 |

代码标准化规则：

- 港股数字代码补齐为 5 位：`700` -> `00700`
- A 股和基金数字代码补齐为 6 位：`11961` -> `011961`
- 美股点号转横线：`BRK.B` -> `BRK-B`

## 数据源策略

服务层使用 provider chain 实现主备切换。链路中第一个可用 provider 作为主数据源；主数据源失败、返回空数据或不支持该资产时，自动尝试下一个 provider。

行情默认链：

| 市场 | freshness | 默认 provider 链 |
| --- | --- | --- |
| HK | `realtime` | `futu_hk`, `yahoo_hk` |
| HK | 其他 | `yahoo_hk`, `futu_hk` |
| US | 任意 | `yahoo_us` |
| CN | 任意 | `akshare_cn_bid_ask` |
| FUND / fund / bond | 任意 | `akshare_fund_nav` |

指标默认链：

| 数据类型 | 市场 | 默认 provider 链 |
| --- | --- | --- |
| 收益率 | HK | `hk_history` |
| 收益率 | US | `us_history` |
| 收益率 | CN | `akshare_cn_history` |
| 收益率 | FUND / fund / bond | `akshare_fund_nav_history` |
| 技术指标 | HK | `hk_history_futu` |
| 技术指标 | US | `us_history` |
| 技术指标 | CN | `akshare_cn_history` |
| 基本面 | HK | `yahoo_hk_fundamentals` |
| 基本面 | US | `yahoo_us_fundamentals` |
| 基本面 | CN | `akshare_cn_individual_fundamentals`, `akshare_cn_spot_fundamentals` |
| 官方披露 | HK | `hkexnews` |
| 官方披露 | US | `sec_edgar` |
| 官方披露 | CN | `cninfo` |
| 基金画像 | FUND / fund / bond | `akshare_fund_profile` |

A 股基本面默认使用单票接口，速度更快但 PE/PB 可能为空；如需要 PE/PB 可通过 `strategy=akshare_cn_spot_fundamentals` 或 `verify=true` 触发全市场 spot 表兜底，但冷启动可能较慢。

## 交叉验证

当 `verify=true` 时，服务会在主数据源之外选择链路中的下一个可用 provider 做验证。

- 行情价格偏离超过 `ALPHALENS_QUOTE_VERIFY_WARN_PCT` 时，`meta.warnings` 会提示差异，默认阈值为 `1.0`。
- 指标字段偏离超过 `ALPHALENS_METRIC_VERIFY_WARN_PCT` 时，`meta.warnings` 会提示差异，默认阈值为 `5.0`。
- 验证成功的数据源写入 `meta.verified_by`。
- 交叉验证只能提高可解释性，不代表数据一定正确；关键投资决策仍应核对交易所公告和公司正式披露。

## Endpoint

### GET `/api/data/quote`

获取资产当前价格、涨跌幅、成交量、币种和名称。

示例：

```bash
curl "http://127.0.0.1:8000/api/data/quote?market=HK&code=00700&asset_type=stock&currency=HKD&freshness=delayed&verify=true"
```

### GET `/api/data/returns`

获取 1/3/6/12 月收益率。

```bash
curl "http://127.0.0.1:8000/api/data/returns?market=US&code=AAPL&asset_type=stock&currency=USD"
```

### GET `/api/data/technicals`

获取 RSI、200 日均线距离、成交活跃度、52 周位置等技术和流动性指标。

```bash
curl "http://127.0.0.1:8000/api/data/technicals?market=CN&code=600519&asset_type=stock&currency=CNY"
```

### GET `/api/data/fundamentals`

获取 PE、Forward PE、PB、PEG、PS、市值、收入增长、ROE、毛利率、Beta 等基本面指标。

```bash
curl "http://127.0.0.1:8000/api/data/fundamentals?market=HK&code=00700&asset_type=stock&currency=HKD"
```

### GET `/api/data/official-filings`

获取官方披露入口和最近公告摘要。该接口不保证完整解析所有财报字段，Agent 生成报告时必须展示数据来源和限制。

```bash
curl "http://127.0.0.1:8000/api/data/official-filings?market=US&code=AAPL&asset_type=stock&currency=USD"
```

### GET `/api/data/fund-profile`

获取基金名称、基金类型、资产类别和一级/二级标签。

```bash
curl "http://127.0.0.1:8000/api/data/fund-profile?code=011961&currency=CNY"
```

### GET `/api/data/research-context`

获取投资 Agent 使用的综合上下文，包括 quote、returns、technicals、fundamentals、official_filings、fund_profile、macro_liquidity 等字段。基金类资产不会请求股票基本面、技术指标和官方披露，以避免无意义告警。

```bash
curl "http://127.0.0.1:8000/api/data/research-context?market=HK&code=00700&asset_type=stock&currency=HKD&verify=true"
```

## 缓存和时效

外部数据抓取会经过本地 SQLite 缓存。缓存 key 按 namespace、provider 和资产参数隔离。为避免 akshare / py_mini_racer 在并发冷启动时崩溃，缓存未命中时的 producer 调用会串行执行；缓存命中后仍可并发读取。

`freshness` 语义：

- `realtime`: 优先实时源，例如 HK + Futu OpenD。
- `intraday`: 日内可更新指标。
- `delayed`: 延迟行情，适合看板默认展示。
- `eod`: 日终或低频指标。

## 扩展 provider

新增数据源时建议：

1. 在 `backend/data_platform/providers.py` 实现对应 provider 接口。
2. 在默认 provider 字典中注册稳定名称。
3. 在 `MarketDataService` 的 provider chain 中加入默认顺序。
4. 为 fallback、strategy override 和 verify 行为补充单元测试。
5. 在本文档中更新 provider 表。
