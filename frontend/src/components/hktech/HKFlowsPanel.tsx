"use client";

import useSWR from "swr";
import { api, fetcher, HKSectorFlow, HKETFPanel } from "@/lib/api";

function signedMn(v: number | null | undefined): string {
  if (v == null) return "—";
  const pos = v >= 0;
  const abs = Math.abs(v);
  const s = abs >= 1000 ? `${(abs / 1000).toFixed(2)}B` : `${abs.toFixed(0)}M`;
  return `${pos ? "+" : "-"}${s}`;
}

function signedPct(v: number | null | undefined, d = 2): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`;
}

function colorSigned(v: number | null | undefined): string {
  if (v == null) return "text-slate-300";
  return v >= 0 ? "text-green-600" : "text-red-500";
}

interface Props {
  tickers: string[];
}

export function HKFlowsPanel({ tickers }: Props) {
  const { data: flow } = useSWR<HKSectorFlow>(
    tickers.length ? api.hkSectorFlow(tickers) : null,
    fetcher,
    { refreshInterval: 5 * 60_000 }
  );
  const { data: etf } = useSWR<HKETFPanel>(api.hkETFPanel(), fetcher, {
    refreshInterval: 5 * 60_000,
  });

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Sector aggregated flow */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-sky-500 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-500" />
            <h3 className="text-base font-semibold text-slate-900">
              板块资金流 · <span className="text-sky-700">主力净流入</span>
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">观察清单汇总 · Futu OpenD</span>
        </div>
        <div className="flex items-baseline gap-8 mb-4">
          <div>
            <div className="text-[11px] text-slate-500">今日合计</div>
            <div className={`text-2xl font-semibold tabular-nums ${colorSigned(flow?.total_today_hkd_mn)}`}>
              {signedMn(flow?.total_today_hkd_mn)}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-slate-500">5日合计</div>
            <div className={`text-xl font-semibold tabular-nums ${colorSigned(flow?.total_5d_hkd_mn)}`}>
              {signedMn(flow?.total_5d_hkd_mn)}
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          {flow?.breakdown.map((r) => {
            const max = Math.max(
              ...(flow?.breakdown.map((x) => Math.abs(x.today_hkd_mn ?? 0)) ?? [1])
            );
            const pct = r.today_hkd_mn == null || max === 0 ? 0 : (Math.abs(r.today_hkd_mn) / max) * 100;
            const pos = (r.today_hkd_mn ?? 0) >= 0;
            return (
              <div key={r.ticker} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-500 w-12">{r.ticker}</span>
                <span className="text-slate-700 w-28 truncate">{r.name ?? "—"}</span>
                <div className="flex-1 h-2 bg-slate-100 rounded relative overflow-hidden">
                  <div
                    className={`absolute top-0 h-2 rounded ${pos ? "bg-green-400 left-1/2" : "bg-red-400 right-1/2"}`}
                    style={{ width: `${pct / 2}%` }}
                  />
                </div>
                <span className={`w-16 text-right tabular-nums ${colorSigned(r.today_hkd_mn)}`}>
                  {signedMn(r.today_hkd_mn)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ETF Panel */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-fuchsia-500 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-fuchsia-500" />
            <h3 className="text-base font-semibold text-slate-900">
              HSTECH ETF · <span className="text-fuchsia-700">跟踪与成交</span>
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">
            指数: <span className={colorSigned(etf?.index_change_pct)}>{signedPct(etf?.index_change_pct)}</span>
          </span>
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 text-[10px] uppercase">
              <th className="text-left font-medium py-1">代码</th>
              <th className="text-left font-medium py-1">名称</th>
              <th className="text-right font-medium py-1">现价</th>
              <th className="text-right font-medium py-1">涨跌</th>
              <th className="text-right font-medium py-1">跟踪差</th>
              <th className="text-right font-medium py-1">成交额</th>
            </tr>
          </thead>
          <tbody>
            {etf?.items.map((r) => {
              const volStr =
                r.volume_hkd_mn == null
                  ? "—"
                  : r.volume_hkd_mn >= 1000
                    ? `${(r.volume_hkd_mn / 1000).toFixed(2)}B`
                    : `${r.volume_hkd_mn.toFixed(0)}M`;
              return (
                <tr key={r.ticker} className="border-t border-slate-100">
                  <td className="py-2 font-mono text-slate-500">{r.ticker}</td>
                  <td className="py-2 text-slate-700 truncate max-w-[160px]">{r.name ?? "—"}</td>
                  <td className="py-2 text-right tabular-nums text-slate-800">
                    {r.price == null ? "—" : r.price.toFixed(3)}
                  </td>
                  <td className={`py-2 text-right tabular-nums ${colorSigned(r.change_pct)}`}>
                    {signedPct(r.change_pct)}
                  </td>
                  <td className={`py-2 text-right tabular-nums ${colorSigned(r.tracking_gap_pct)}`}>
                    {r.tracking_gap_pct == null ? "—" : signedPct(r.tracking_gap_pct)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-slate-600">{volStr}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="mt-3 text-[10px] text-slate-400">
          跟踪差 = ETF 当日涨跌 − HSTECH 当日涨跌 · 正值=溢价 / 负值=折价信号
        </div>
      </div>
    </div>
  );
}
