"use client";

import useSWR from "swr";
import { api, fetcher, HKStockSnapshot, HKStockTechnical } from "@/lib/api";

interface Props {
  tickers: string[];
}

function tileColor(change: number | null | undefined): string {
  if (change == null) return "bg-slate-100 text-slate-400";
  if (change >= 5) return "bg-red-700 text-white";
  if (change >= 3) return "bg-red-600 text-white";
  if (change >= 1) return "bg-red-500 text-white";
  if (change > 0) return "bg-red-200 text-red-900";
  if (change === 0) return "bg-slate-200 text-slate-700";
  if (change > -1) return "bg-green-200 text-green-900";
  if (change > -3) return "bg-green-400 text-white";
  if (change > -5) return "bg-green-500 text-white";
  return "bg-green-700 text-white";
}

export function HKSentimentHeatmap({ tickers }: Props) {
  const { data: snaps } = useSWR<HKStockSnapshot[]>(
    tickers.length ? api.hkSnapshot(tickers) : null,
    fetcher,
    { refreshInterval: 60_000 }
  );
  const { data: techs } = useSWR<HKStockTechnical[]>(
    tickers.length ? api.hkTechnicals(tickers) : null,
    fetcher,
    { refreshInterval: 10 * 60_000 }
  );
  const snapMap = new Map(snaps?.map((s) => [s.ticker, s]) ?? []);
  const techMap = new Map(techs?.map((t) => [t.ticker, t]) ?? []);

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-rose-500 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500" />
          <h3 className="text-base font-semibold text-slate-900">
            情绪热力图 · <span className="text-rose-700">涨跌 & 主力</span>
          </h3>
        </div>
        <span className="text-[11px] text-slate-400">颜色=当日涨跌 · 副标=主力净流入</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {tickers.map((t) => {
          const s = snapMap.get(t);
          const th = techMap.get(t);
          const chg = s?.change_pct;
          const flow = th?.net_inflow_today_hkd_mn;
          const flowAbs = flow == null ? null : Math.abs(flow);
          const flowStr =
            flow == null
              ? "—"
              : flowAbs! >= 1000
                ? `${flow >= 0 ? "+" : "-"}${(flowAbs! / 1000).toFixed(1)}B`
                : `${flow >= 0 ? "+" : "-"}${flowAbs!.toFixed(0)}M`;
          return (
            <div
              key={t}
              className={`rounded-lg p-3 flex flex-col gap-0.5 transition-colors ${tileColor(chg)}`}
            >
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-[10px] opacity-80">{t}</span>
                <span className="text-xs font-semibold tabular-nums">
                  {chg == null ? "—" : `${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%`}
                </span>
              </div>
              <div className="text-xs font-medium truncate">{s?.name ?? "—"}</div>
              <div className="mt-0.5">
                <span className="text-[10px] opacity-90 tabular-nums">主力 {flowStr}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
