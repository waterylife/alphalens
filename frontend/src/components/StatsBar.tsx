"use client";

import { CompareSeries } from "@/lib/api";

function fmt(v: number | null | undefined, suffix = "%"): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}${suffix}`;
}

function plain(v: number | null | undefined, suffix = "%"): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}${suffix}`;
}

function colorFor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-slate-500";
  return v >= 0 ? "text-red-600" : "text-green-600";
}

function Row({ series, colorDot }: { series: CompareSeries; colorDot: string }) {
  const s = series.stats;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px]">
      <div className="flex items-center gap-1.5 font-semibold min-w-[88px]">
        <span className={`inline-block w-2 h-2 rounded-full ${colorDot}`} />
        <span className="text-slate-800">{series.name}</span>
      </div>
      <span className="text-slate-500">
        收益: <span className={`font-semibold ${colorFor(s.return_pct)}`}>{fmt(s.return_pct)}</span>
      </span>
      <span className="text-slate-500">
        年化: <span className={`font-semibold ${colorFor(s.annualized_pct)}`}>{fmt(s.annualized_pct)}</span>
      </span>
      <span className="text-slate-500">
        最大回撤: <span className="font-semibold text-green-600">{plain(s.max_drawdown)}</span>
      </span>
      <span className="text-slate-500">
        最大涨幅: <span className="font-semibold text-red-600">{plain(s.max_gain)}</span>
      </span>
      <span className="text-slate-500">
        波动率: <span className="font-semibold text-slate-700">{plain(s.volatility, "")}</span>
      </span>
    </div>
  );
}

export function StatsBar({ index, benchmark }: { index: CompareSeries; benchmark: CompareSeries }) {
  return (
    <div className="px-2 py-3 space-y-2 border-t border-slate-100">
      <Row series={index} colorDot="bg-red-500" />
      <Row series={benchmark} colorDot="bg-blue-500" />
    </div>
  );
}
