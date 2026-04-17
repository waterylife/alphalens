# AlphaLens · 红利指数分析看板

A value-investing oriented web dashboard for analyzing A-share dividend indices,
backed by T+1 data from [akshare](https://akshare.akfamily.xyz/).

## Features

**Dashboard** — 红利指数估值 / 股息率 / 利差 / 成分股透视

- 核心指标卡片：最新价、股息率、PE、股息率-10Y国债利差
- 指数走势：10 年历史收盘价曲线
- 估值历史：PE TTM / 股息率，叠加 20% / 50% / 80% 历史分位参考线
- 股息率利差：指数股息率 vs 10Y 国债收益率双轴联动
- 成分股：前 20 大成分股及权重
- 支持指数：中证红利 (000922)、上证红利 (000015)、深证红利 (399324)、红利低波 (000825)、红利低波100 (930955)

**Analysis library** (`alphalens/`) — 因子分析工具包

- 因子与前向收益对齐、分位数标注
- IC / 分位数收益 / alpha-beta / 换手率
- 图表与 tear sheet

## Architecture

```
backend/     FastAPI + akshare + SQLite 缓存
frontend/    Next.js 16 + TypeScript + Tailwind + ECharts
alphalens/   独立的因子分析 Python 库
```

## Quickstart

### 1. 后端（FastAPI）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 启动 API（监听 127.0.0.1:8000）
uvicorn backend.main:app --reload
```

API 文档: http://127.0.0.1:8000/docs

### 2. 前端（Next.js）

```bash
cd frontend
npm install
npm run dev
```

看板地址: http://localhost:3000

前端通过 `/api/*` 代理到后端 8000 端口（见 `next.config.ts`）。

## Data Sources (via akshare)

| 数据 | 来源 | 覆盖范围 |
|---|---|---|
| 指数日线行情 | 腾讯财经 | 20 年+ |
| PE / 股息率（官方） | 中证指数 csindex | 近 20 交易日 |
| PE / PB 历史 | 乐咕乐股 legulegu | 20 年+（上证红利 / 深证红利） |
| 成分股及权重 | 中证指数 csindex | 月度更新 |
| 10Y 国债收益率 | 中国外汇交易中心 | 日频 |

所有数据均为 T+1，接入实时行情后续可替换为 tushare pro / 新浪财经。

## License

Apache 2.0
