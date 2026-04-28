"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  api, fetcher,
  USStockSnapshot, USStockReturn, USStockFundamental, USStockTechnical,
  USMacro, USSectorFlow, USIndexChart, USStockSearchResult,
} from "@/lib/api";
import { MatrixNotes } from "@/components/MatrixNotes";
import { SignalBoard } from "@/components/SignalBoard";

const DEFAULT_TICKERS = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ"];
const LS_KEY = "alphalens_ustech_tickers";

function loadTickers(): string[] {
  if (typeof window === "undefined") return DEFAULT_TICKERS;
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return DEFAULT_TICKERS;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) return parsed;
  } catch {}
  return DEFAULT_TICKERS;
}

// ─────────── Tiny helpers ───────────

function signedPct(v: number | null | undefined, d = 2): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`;
}

function colorSigned(v: number | null | undefined): string {
  if (v == null) return "text-slate-300";
  return v >= 0 ? "text-green-600" : "text-red-500";
}

function num(v: number | null | undefined, d = 2, suffix = ""): string {
  if (v == null) return "—";
  return `${v.toFixed(d)}${suffix}`;
}

function bigNum(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return `${(v / 1000).toFixed(2)}T`;
  if (abs >= 1) return `${v.toFixed(1)}B`;
  return `${(v * 1000).toFixed(0)}M`;
}

function volFmt(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(2)}B`;
  return `${v.toFixed(0)}M`;
}

// ─────────── Macro Panel ───────────

function MacroPanel() {
  const { data } = useSWR<USMacro>(api.usMacro(), fetcher, { refreshInterval: 5 * 60_000 });
  const stat = (label: string, v: string, sub?: string | null, color = "text-slate-900") => (
    <div className="flex flex-col min-w-[110px]">
      <span className="text-[11px] text-slate-500">{label}</span>
      <span className={`text-lg font-semibold tabular-nums ${color}`}>{v}</span>
      {sub && <span className="text-[10px] text-slate-400 tabular-nums">{sub}</span>}
    </div>
  );
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-violet-500 p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full bg-violet-500" />
        <h3 className="text-base font-semibold text-slate-900">
          宏观流动性 · <span className="text-violet-700">美股风险信号</span>
        </h3>
        <span className="text-[11px] text-slate-400 ml-2">VIX · 10Y · 2Y · DXY</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-5">
        {stat("VIX 恐慌指数", num(data?.vix, 2),
          data?.vix_change_pct != null ? signedPct(data.vix_change_pct) : null,
          (data?.vix ?? 0) >= 25 ? "text-red-600" : (data?.vix ?? 30) <= 13 ? "text-amber-600" : "text-slate-900")}
        {stat("US 10Y", num(data?.us_10y, 2, "%"))}
        {stat("US 2Y", num(data?.us_2y, 2, "%"))}
        {stat("2s10s 利差", num(data?.curve_2s10s_bps, 0, " bps"),
          (data?.curve_2s10s_bps ?? 0) < 0 ? "倒挂⚠" : null,
          (data?.curve_2s10s_bps ?? 0) < 0 ? "text-red-600" : "text-slate-900")}
        {stat("美元指数 DXY", num(data?.dxy, 2))}
        {stat("13W 短债", num(data?.fed_funds_13w, 2, "%"))}
      </div>
      <div className="mt-3 text-[10px] text-slate-400">数据源: Yahoo Finance · 15 分钟延迟</div>
    </div>
  );
}

// ─────────── Index Overview (4 cards) ───────────

function IndexCard({ symbol, label }: { symbol: string; label: string }) {
  const { data } = useSWR<USIndexChart>(
    api.usIndexChart(symbol, 1), fetcher, { refreshInterval: 10 * 60_000 }
  );
  const pts = data?.points ?? [];
  const last = pts.length ? pts[pts.length - 1].close : null;
  const prev = pts.length >= 2 ? pts[pts.length - 2].close : null;
  const d1 = last != null && prev ? ((last / prev - 1) * 100) : null;
  const yStart = pts.length ? pts[0].close : null;
  const y1 = last != null && yStart ? ((last / yStart - 1) * 100) : null;
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4 flex flex-col gap-1">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums text-slate-900">
        {last != null ? last.toFixed(2) : "—"}
      </div>
      <div className="flex items-baseline gap-3 text-xs tabular-nums">
        <span className={colorSigned(d1)}>今日 {signedPct(d1)}</span>
        <span className={colorSigned(y1)}>近1年 {signedPct(y1)}</span>
      </div>
    </div>
  );
}

function IndexOverview() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <IndexCard symbol="^GSPC" label="S&P 500" />
      <IndexCard symbol="^IXIC" label="纳斯达克" />
      <IndexCard symbol="^RUT" label="罗素 2000" />
      <IndexCard symbol="^VIX" label="VIX" />
    </div>
  );
}

// ─────────── Sentiment Heatmap ───────────

function tileColor(v: number | null | undefined): string {
  if (v == null) return "bg-slate-100 text-slate-400";
  if (v >= 3) return "bg-green-600 text-white";
  if (v >= 1) return "bg-green-500 text-white";
  if (v > 0) return "bg-green-200 text-green-900";
  if (v === 0) return "bg-slate-200 text-slate-700";
  if (v > -1) return "bg-red-200 text-red-900";
  if (v > -3) return "bg-red-400 text-white";
  return "bg-red-600 text-white";
}

function SentimentHeatmap({ tickers }: { tickers: string[] }) {
  const { data: snaps } = useSWR<USStockSnapshot[]>(
    tickers.length ? api.usSnapshot(tickers) : null, fetcher, { refreshInterval: 60_000 }
  );
  const { data: techs } = useSWR<USStockTechnical[]>(
    tickers.length ? api.usTechnicals(tickers) : null, fetcher, { refreshInterval: 10 * 60_000 }
  );
  const snapMap = new Map(snaps?.map((s) => [s.ticker, s]) ?? []);
  const techMap = new Map(techs?.map((t) => [t.ticker, t]) ?? []);

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-rose-500 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500" />
          <h3 className="text-base font-semibold text-slate-900">
            情绪热力图 · <span className="text-rose-700">当日涨跌 & 52w 位置</span>
          </h3>
        </div>
        <span className="text-[11px] text-slate-400">色块=当日涨跌 · 副标=52w 位置</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {tickers.map((t) => {
          const s = snapMap.get(t);
          const th = techMap.get(t);
          return (
            <div key={t} className={`relative rounded-lg p-3 flex flex-col gap-0.5 ${tileColor(s?.change_pct)}`}>
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-[10px] opacity-80">{t}</span>
                <span className="text-xs font-semibold tabular-nums">{signedPct(s?.change_pct, 1)}</span>
              </div>
              <div className="text-xs font-medium truncate">{s?.name ?? "—"}</div>
              <div className="mt-0.5">
                <span className="text-[10px] opacity-90 tabular-nums">
                  52w {th?.pos_52w_pct != null ? `${th.pos_52w_pct.toFixed(0)}` : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────── Stocks Matrix (3 tabs) ───────────

type Section = "fundamental" | "sentiment" | "liquidity";

const SECTIONS: { key: Section; label: string; sub: string; accent: string; barColor: string }[] = [
  { key: "fundamental", label: "基本面", sub: "估值 · 质量",  accent: "bg-blue-600 text-white",    barColor: "border-l-blue-500" },
  { key: "sentiment",   label: "情绪面", sub: "涨跌 · 动量",  accent: "bg-amber-600 text-white",   barColor: "border-l-amber-500" },
  { key: "liquidity",   label: "流动性", sub: "成交 · ADTV",  accent: "bg-emerald-600 text-white", barColor: "border-l-emerald-500" },
];

function RsiCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-slate-300 text-xs">—</span>;
  const c = v >= 70 ? "text-red-500" : v <= 30 ? "text-green-600" : "text-slate-700";
  return <span className={`text-xs font-medium tabular-nums ${c}`}>{v.toFixed(0)}</span>;
}

function Pos52wCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-slate-300 text-xs">—</span>;
  const c = v >= 80 ? "text-red-500" : v <= 20 ? "text-green-600" : "text-slate-700";
  return <span className={`text-xs font-medium tabular-nums ${c}`}>{v.toFixed(0)}</span>;
}

function StocksMatrix({ tickers, onTickersChange }: { tickers: string[]; onTickersChange: (t: string[]) => void }) {
  const [section, setSection] = useState<Section>("sentiment");
  const current = SECTIONS.find((s) => s.key === section)!;

  const { data: snaps } = useSWR<USStockSnapshot[]>(tickers.length ? api.usSnapshot(tickers) : null, fetcher, { refreshInterval: 60_000 });
  const { data: rets }  = useSWR<USStockReturn[]>(tickers.length && section === "sentiment" ? api.usReturns(tickers) : null, fetcher, { refreshInterval: 5 * 60_000 });
  const { data: techs } = useSWR<USStockTechnical[]>(tickers.length && (section === "sentiment" || section === "liquidity") ? api.usTechnicals(tickers) : null, fetcher, { refreshInterval: 10 * 60_000 });
  const { data: funds } = useSWR<USStockFundamental[]>(tickers.length && section === "fundamental" ? api.usFundamentals(tickers) : null, fetcher, { refreshInterval: 60 * 60_000 });

  const snapMap = new Map(snaps?.map((s) => [s.ticker, s]) ?? []);
  const retMap  = new Map(rets?.map((s) => [s.ticker, s]) ?? []);
  const techMap = new Map(techs?.map((s) => [s.ticker, s]) ?? []);
  const fundMap = new Map(funds?.map((s) => [s.ticker, s]) ?? []);

  const remove = (t: string) => onTickersChange(tickers.filter((x) => x !== t));

  const [query, setQuery] = useState("");
  const { data: suggestions } = useSWR<USStockSearchResult[]>(
    query.length >= 1 ? api.usSearch(query) : null, fetcher
  );
  const add = (t: string) => {
    if (!tickers.includes(t)) onTickersChange([...tickers, t]);
    setQuery("");
  };

  const head = section === "fundamental"
    ? ["PE(TTM)", "Fwd PE", "PEG", "P/S", "市值", "营收增长", "ROE", "毛利率", "Beta"]
    : section === "sentiment"
    ? ["今日", "1M", "3M", "6M", "12M", "RSI14", "距 MA200", "52w", "距 ATH"]
    : ["今日成交", "ADTV 20d", "做空占比"];

  const row = (t: string) => {
    const s = snapMap.get(t), r = retMap.get(t), th = techMap.get(t), f = fundMap.get(t);
    if (section === "fundamental") return (
      <>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.pe_ttm ?? null)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.forward_pe ?? null)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.peg ?? null)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.ps_ttm ?? null)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{bigNum(f?.market_cap_usd_bn ?? null)}</td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(f?.revenue_growth_pct)}`}>{signedPct(f?.revenue_growth_pct, 1)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.roe_pct ?? null, 1, "%")}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.gross_margin_pct ?? null, 1, "%")}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(f?.beta ?? null)}</td>
      </>
    );
    if (section === "sentiment") return (
      <>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(s?.change_pct)}`}>{signedPct(s?.change_pct, 1)}</td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(r?.ret_1m)}`}>{signedPct(r?.ret_1m, 1)}</td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(r?.ret_3m)}`}>{signedPct(r?.ret_3m, 1)}</td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(r?.ret_6m)}`}>{signedPct(r?.ret_6m, 1)}</td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(r?.ret_12m)}`}>{signedPct(r?.ret_12m, 1)}</td>
        <td className="px-3 py-3"><RsiCell v={th?.rsi14} /></td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(th?.dist_ma200_pct)}`}>{signedPct(th?.dist_ma200_pct, 1)}</td>
        <td className="px-3 py-3"><Pos52wCell v={th?.pos_52w_pct} /></td>
        <td className={`px-3 py-3 text-xs tabular-nums ${colorSigned(th?.dist_ath_pct)}`}>{signedPct(th?.dist_ath_pct, 1)}</td>
      </>
    );
    return (
      <>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{volFmt(s?.volume_usd_mn)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{volFmt(th?.adtv_20d_usd_mn)}</td>
        <td className="px-3 py-3 text-xs tabular-nums text-slate-700">{num(th?.short_pct_float ?? null, 2, "%")}</td>
      </>
    );
  };

  return (
    <div className={`bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 ${current.barColor}`}>
      <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            美股矩阵 · <span>{current.label}</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">{current.sub}</p>
        </div>
        <div className="flex items-center gap-2 relative">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value.toUpperCase())}
            placeholder="+ 添加 ticker"
            className="border border-dashed border-slate-300 rounded-md px-2 py-1.5 text-xs w-36 focus:outline-none focus:border-slate-500"
          />
          {query && (
            <div className="absolute top-full right-0 mt-1 w-48 bg-white border border-slate-200 rounded-md shadow-lg z-10">
              {(suggestions ?? []).map((s) => (
                <button key={s.ticker} onClick={() => add(s.ticker)}
                  className="block w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50">
                  <span className="font-mono font-semibold">{s.ticker}</span> <span className="text-slate-500">{s.name}</span>
                </button>
              ))}
              {suggestions?.length === 0 && (
                <button onClick={() => add(query)}
                  className="block w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50">
                  添加 <span className="font-mono">{query}</span>（直接使用）
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="px-5 pb-3 flex items-center gap-2">
        {SECTIONS.map((s) => (
          <button key={s.key} onClick={() => setSection(s.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium ${section === s.key ? s.accent : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
            {s.label}
            <span className={`ml-1.5 text-[10px] ${section === s.key ? "opacity-80" : "text-slate-400"}`}>{s.sub}</span>
          </button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50">
              {["代码", "名称", "现价 USD", ...head, ""].map((h, i) => (
                <th key={i} className="px-3 py-2 text-left text-xs font-medium text-slate-500 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tickers.map((t) => {
              const s = snapMap.get(t);
              return (
                <tr key={t} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-3">
                    <span className="font-mono text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{t}</span>
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-800 whitespace-nowrap">{s?.name ?? "—"}</td>
                  <td className="px-3 py-3 text-sm font-semibold tabular-nums text-slate-900">
                    {s?.price != null ? s.price.toFixed(2) : "—"}
                  </td>
                  {row(t)}
                  <td className="px-2 py-3">
                    <button onClick={() => remove(t)} className="text-slate-300 hover:text-red-400 text-sm">✕</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <MatrixNotes market="us" />

      <div className="px-5 py-3 border-t border-slate-100 text-[11px] text-slate-400">
        数据源: Yahoo Finance (yfinance) · 15 分钟延迟
      </div>
    </div>
  );
}

// ─────────── Sector Flow ───────────

function SectorFlow() {
  const { data } = useSWR<USSectorFlow>(api.usSectorFlow(), fetcher, { refreshInterval: 5 * 60_000 });
  const items = data?.items ?? [];
  const max = Math.max(...items.map((i) => Math.abs(i.change_pct ?? 0)), 1);
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-sky-500 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-sky-500" />
          <h3 className="text-base font-semibold text-slate-900">
            板块强弱 · <span className="text-sky-700">11 SPDR 行业 ETF</span>
          </h3>
        </div>
        <span className="text-[11px] text-slate-400">按当日涨跌排序</span>
      </div>
      <div className="space-y-1.5">
        {items.map((r) => {
          const pct = ((Math.abs(r.change_pct ?? 0)) / max) * 100;
          const pos = (r.change_pct ?? 0) >= 0;
          return (
            <div key={r.ticker} className="flex items-center gap-2 text-xs">
              <span className="font-mono text-slate-500 w-12">{r.ticker}</span>
              <span className="text-slate-700 w-28">{r.sector}</span>
              <div className="flex-1 h-2 bg-slate-100 rounded relative overflow-hidden">
                <div className={`absolute top-0 h-2 rounded ${pos ? "bg-green-400 left-1/2" : "bg-red-400 right-1/2"}`}
                  style={{ width: `${pct / 2}%` }} />
              </div>
              <span className={`w-16 text-right tabular-nums ${colorSigned(r.change_pct)}`}>{signedPct(r.change_pct, 2)}</span>
              <span className={`w-16 text-right tabular-nums ${colorSigned(r.change_5d_pct)} opacity-75`}>5d {signedPct(r.change_5d_pct, 1)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────── Dashboard root ───────────

export function USDashboard() {
  const [tickers, setTickers] = useState<string[]>(() => loadTickers());

  const handleChange = (next: string[]) => {
    setTickers(next);
    try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch {}
  };

  return (
    <main className="max-w-7xl mx-auto px-6 py-6 space-y-5">
      <IndexOverview />
      <SignalBoard market="us" tickers={tickers} />
      <SentimentHeatmap tickers={tickers} />
      <StocksMatrix tickers={tickers} onTickersChange={handleChange} />
      <SectorFlow />
      <MacroPanel />
    </main>
  );
}
