"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  api,
  fetcher,
  HKStockSnapshot,
  HKStockReturn,
  HKStockTechnical,
  HKStockFundamental,
} from "@/lib/api";
import { HKAddStockInput } from "./HKAddStockInput";
import { MatrixNotes } from "@/components/MatrixNotes";

interface Props {
  tickers: string[];
  onTickersChange: (tickers: string[]) => void;
}

type SectionKey = "fundamental" | "sentiment" | "liquidity";

const SECTIONS: {
  key: SectionKey;
  label: string;
  sub: string;
  // Tailwind color tokens — used for active tab + section header accent
  accent: {
    // active tab pill
    pill: string;
    // section border (left bar)
    bar: string;
    // header row bg
    headerBg: string;
    // header text
    headerText: string;
    // dot
    dot: string;
  };
}[] = [
  {
    key: "fundamental",
    label: "基本面",
    sub: "估值 · 市值",
    accent: {
      pill: "bg-blue-600 text-white",
      bar: "border-l-4 border-blue-500",
      headerBg: "bg-blue-50",
      headerText: "text-blue-700",
      dot: "bg-blue-500",
    },
  },
  {
    key: "sentiment",
    label: "情绪面",
    sub: "涨跌 · 技术",
    accent: {
      pill: "bg-amber-600 text-white",
      bar: "border-l-4 border-amber-500",
      headerBg: "bg-amber-50",
      headerText: "text-amber-700",
      dot: "bg-amber-500",
    },
  },
  {
    key: "liquidity",
    label: "流动性",
    sub: "成交 · ADTV",
    accent: {
      pill: "bg-emerald-600 text-white",
      bar: "border-l-4 border-emerald-500",
      headerBg: "bg-emerald-50",
      headerText: "text-emerald-700",
      dot: "bg-emerald-500",
    },
  },
];

function ChangeCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const pos = value >= 0;
  return (
    <span
      className={`text-xs font-medium tabular-nums ${
        pos ? "text-green-600" : "text-red-500"
      }`}
    >
      {pos ? "+" : ""}
      {value.toFixed(1)}%
    </span>
  );
}

function Num({
  value,
  digits = 2,
  suffix = "",
}: {
  value: number | null | undefined;
  digits?: number;
  suffix?: string;
}) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  return (
    <span className="text-xs tabular-nums text-slate-700">
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
}

function VolCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const display =
    value >= 1000 ? `${(value / 1000).toFixed(1)}B` : `${value.toFixed(0)}M`;
  return <span className="text-xs tabular-nums text-slate-600">{display}</span>;
}

function FlowCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const pos = value >= 0;
  const abs = Math.abs(value);
  const display =
    abs >= 1000 ? `${(abs / 1000).toFixed(2)}B` : `${abs.toFixed(0)}M`;
  return (
    <span
      className={`text-xs font-medium tabular-nums ${
        pos ? "text-green-600" : "text-red-500"
      }`}
    >
      {pos ? "+" : "-"}
      {display}
    </span>
  );
}

function VolRatioCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const color =
    value >= 2 ? "text-red-500" : value >= 1 ? "text-amber-600" : "text-slate-500";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {value.toFixed(2)}
    </span>
  );
}

function Pos52wCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const color =
    value >= 80 ? "text-red-500" : value <= 20 ? "text-green-600" : "text-slate-700";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {value.toFixed(0)}
    </span>
  );
}

function SpreadCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const color =
    value >= 20 ? "text-red-500" : value >= 10 ? "text-amber-600" : "text-slate-600";
  return (
    <span className={`text-xs tabular-nums ${color}`}>
      {value.toFixed(1)}
    </span>
  );
}

function DepthCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const color =
    value >= 1.2 ? "text-green-600" : value <= 0.8 ? "text-red-500" : "text-slate-600";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {value.toFixed(2)}
    </span>
  );
}

function RsiCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const color =
    value >= 70 ? "text-red-500" : value <= 30 ? "text-green-600" : "text-slate-700";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {value.toFixed(0)}
    </span>
  );
}

function MarketCapCell({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="text-slate-300 text-xs">—</span>;
  const display =
    value >= 1000 ? `${(value / 1000).toFixed(2)}T` : `${value.toFixed(0)}B`;
  return <span className="text-xs tabular-nums text-slate-700">{display}</span>;
}

export function HKStocksMatrix({ tickers, onTickersChange }: Props) {
  const [section, setSection] = useState<SectionKey>("sentiment");

  const { data: snapshots, isLoading: snapLoading } = useSWR<HKStockSnapshot[]>(
    tickers.length ? api.hkSnapshot(tickers) : null,
    fetcher,
    { refreshInterval: 60_000 }
  );

  const { data: returns, isLoading: retLoading } = useSWR<HKStockReturn[]>(
    tickers.length ? api.hkReturns(tickers) : null,
    fetcher,
    { refreshInterval: 5 * 60_000 }
  );

  const { data: technicals, isLoading: techLoading } = useSWR<HKStockTechnical[]>(
    tickers.length && (section === "sentiment" || section === "liquidity")
      ? api.hkTechnicals(tickers)
      : null,
    fetcher,
    { refreshInterval: 10 * 60_000 }
  );

  const { data: fundamentals, isLoading: fundLoading } = useSWR<HKStockFundamental[]>(
    tickers.length && section === "fundamental" ? api.hkFundamentals(tickers) : null,
    fetcher,
    { refreshInterval: 60 * 60_000 }
  );

  const snapMap = new Map(snapshots?.map((s) => [s.ticker, s]) ?? []);
  const retMap = new Map(returns?.map((r) => [r.ticker, r]) ?? []);
  const techMap = new Map(technicals?.map((t) => [t.ticker, t]) ?? []);
  const fundMap = new Map(fundamentals?.map((f) => [f.ticker, f]) ?? []);

  const removeTicker = (ticker: string) =>
    onTickersChange(tickers.filter((t) => t !== ticker));

  const addTicker = (ticker: string) => {
    if (!tickers.includes(ticker)) onTickersChange([...tickers, ticker]);
  };

  const current = SECTIONS.find((s) => s.key === section)!;

  // Columns per section (excluding 代码/名称/现价 + ✕ which are always shown)
  const renderHead = () => {
    if (section === "fundamental") {
      return ["PE (TTM)", "PB", "PS (TTM)", "市值 (HKD)"];
    }
    if (section === "sentiment") {
      return ["今日", "1M", "3M", "6M", "12M", "RSI14", "距MA200", "52w位置", "主力净流入", "5日主力", "量比"];
    }
    return ["换手率", "今日成交额", "ADTV 20d", "价差 (bps)", "盘口比"];
  };

  const renderRow = (ticker: string) => {
    const snap = snapMap.get(ticker);
    const ret = retMap.get(ticker);
    const tech = techMap.get(ticker);
    const fund = fundMap.get(ticker);

    if (section === "fundamental") {
      const loading = !fundamentals && fundLoading;
      return (
        <>
          <td className="px-4 py-3">
            {loading ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <Num value={fund?.pe_ttm} />}
          </td>
          <td className="px-4 py-3">
            {loading ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <Num value={fund?.pb} />}
          </td>
          <td className="px-4 py-3">
            {loading ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <Num value={fund?.ps_ttm} />}
          </td>
          <td className="px-4 py-3">
            {loading ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <MarketCapCell value={fund?.market_cap_hkd_bn} />}
          </td>
        </>
      );
    }
    if (section === "sentiment") {
      const retLoadingCell = !returns && retLoading;
      const techLoadingCell = !technicals && techLoading;
      return (
        <>
          <td className="px-4 py-3"><ChangeCell value={snap?.change_pct} /></td>
          <td className="px-4 py-3">{retLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <ChangeCell value={ret?.ret_1m} />}</td>
          <td className="px-4 py-3">{retLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <ChangeCell value={ret?.ret_3m} />}</td>
          <td className="px-4 py-3">{retLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <ChangeCell value={ret?.ret_6m} />}</td>
          <td className="px-4 py-3">{retLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <ChangeCell value={ret?.ret_12m} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <RsiCell value={tech?.rsi14} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <ChangeCell value={tech?.dist_ma200_pct} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <Pos52wCell value={tech?.pos_52w_pct} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <FlowCell value={tech?.net_inflow_today_hkd_mn} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <FlowCell value={tech?.net_inflow_5d_hkd_mn} />}</td>
          <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <VolRatioCell value={tech?.volume_ratio} />}</td>
        </>
      );
    }
    // liquidity
    const techLoadingCell = !technicals && techLoading;
    return (
      <>
        <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <Num value={tech?.turnover_rate} digits={2} suffix="%" />}</td>
        <td className="px-4 py-3"><VolCell value={snap?.volume_hkd_mn} /></td>
        <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <VolCell value={tech?.adtv_20d_hkd_mn} />}</td>
        <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <SpreadCell value={tech?.bid_ask_spread_bps} />}</td>
        <td className="px-4 py-3">{techLoadingCell ? <span className="text-slate-200 text-xs animate-pulse">…</span> : <DepthCell value={tech?.depth_ratio_5} />}</td>
      </>
    );
  };

  return (
    <div className={`bg-white border border-slate-200 rounded-xl shadow-sm ${current.accent.bar}`}>
      <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
        <div className="min-w-0 shrink-0">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${current.accent.dot}`} />
            <h3 className="text-base font-semibold text-slate-900">
              个股矩阵 · <span className={current.accent.headerText}>{current.label}</span>
            </h3>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">{current.sub}</p>
        </div>
        <HKAddStockInput existingTickers={tickers} onAdd={addTicker} />
      </div>

      {/* Section tabs */}
      <div className="px-5 pb-3 flex items-center gap-2">
        {SECTIONS.map((s) => {
          const active = s.key === section;
          return (
            <button
              key={s.key}
              onClick={() => setSection(s.key)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                active
                  ? s.accent.pill
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {s.label}
              <span className={`ml-1.5 text-[10px] ${active ? "opacity-80" : "text-slate-400"}`}>
                {s.sub}
              </span>
            </button>
          );
        })}
      </div>

      {/* Sub-header explaining the section */}
      <div className={`px-5 py-2 text-xs ${current.accent.headerBg} ${current.accent.headerText} border-t border-b border-slate-100`}>
        {section === "fundamental" && "估值 & 市值指标 · 数据来源: Yahoo Finance (yfinance)"}
        {section === "sentiment" && "价格动量 · 超买超卖 · 主力资金 · 量比 (数据源: Futu OpenD)"}
        {section === "liquidity" && "换手率 · 今日成交额 · 20日日均成交额 (ADTV)"}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50">
              {["代码", "名称", "现价 (HKD)", ...renderHead(), ""].map((h, i) => (
                <th
                  key={`${h}-${i}`}
                  className="px-4 py-2 text-left text-xs font-medium text-slate-500 whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {tickers.map((ticker) => {
              const snap = snapMap.get(ticker);
              const isNew = !snapshots && snapLoading;

              return (
                <tr
                  key={ticker}
                  className="border-t border-slate-100 hover:bg-slate-50 transition-colors"
                >
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="font-mono text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                      {ticker}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {snap?.name ? (
                      <span className="text-xs text-slate-800">{snap.name}</span>
                    ) : (
                      <span className="text-xs text-slate-300">{isNew ? "加载中…" : "—"}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {snap?.price != null ? (
                      <span className="text-sm font-semibold text-slate-900 tabular-nums">
                        {snap.price.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-slate-300 text-xs">{isNew ? "…" : "—"}</span>
                    )}
                  </td>

                  {renderRow(ticker)}

                  <td className="px-3 py-3">
                    <button
                      onClick={() => removeTicker(ticker)}
                      className="text-slate-300 hover:text-red-400 transition-colors text-sm leading-none"
                      title="移除"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}

            {tickers.length === 0 && (
              <tr>
                <td colSpan={12} className="px-4 py-8 text-center text-sm text-slate-400">
                  暂无股票，点击右上角添加
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <MatrixNotes market="hk" />

      <div className="px-5 py-3 border-t border-slate-100 text-xs text-slate-400">
        报价: 新浪财经 · 基本面: Yahoo Finance + Futu · 主力资金/换手率/量比: Futu OpenD
      </div>
    </div>
  );
}
