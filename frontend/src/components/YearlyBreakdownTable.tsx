"use client";

import { YearlyRow } from "@/lib/api";

function fmt(v: number | null | undefined, signed = false): string {
  if (v === null || v === undefined) return "—";
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function retColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-slate-400";
  return v >= 0 ? "text-red-600" : "text-green-600";
}

export function YearlyBreakdownTable({
  rows,
  indexName,
  benchmarkName,
}: {
  rows: YearlyRow[];
  indexName: string;
  benchmarkName: string;
}) {
  if (!rows.length) return null;

  return (
    <div className="overflow-x-auto border-t border-slate-100">
      <table className="w-full text-sm border-collapse min-w-[720px]">
        <thead>
          <tr className="text-[11px] text-slate-500">
            <th rowSpan={2} className="py-2 px-3 text-left font-medium border-b border-slate-100">
              区间
            </th>
            <th colSpan={2} className="py-1.5 px-3 font-medium">收益</th>
            <th colSpan={2} className="py-1.5 px-3 font-medium">波动率</th>
            <th colSpan={2} className="py-1.5 px-3 font-medium">最大回撤</th>
            <th colSpan={2} className="py-1.5 px-3 font-medium">最大涨幅</th>
          </tr>
          <tr className="text-[10px] text-slate-400 border-b border-slate-100">
            <th className="pb-1.5 px-3 font-normal">{indexName}</th>
            <th className="pb-1.5 px-3 font-normal">{benchmarkName}</th>
            <th className="pb-1.5 px-3 font-normal">{indexName}</th>
            <th className="pb-1.5 px-3 font-normal">{benchmarkName}</th>
            <th className="pb-1.5 px-3 font-normal">{indexName}</th>
            <th className="pb-1.5 px-3 font-normal">{benchmarkName}</th>
            <th className="pb-1.5 px-3 font-normal">{indexName}</th>
            <th className="pb-1.5 px-3 font-normal">{benchmarkName}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.year}
              className="border-b border-slate-50 hover:bg-slate-50/50 transition"
            >
              <td className="py-2 px-3 font-semibold text-slate-700">{r.year}</td>
              <td className={`py-2 px-3 text-center font-medium ${retColor(r.index_return)}`}>
                {fmt(r.index_return, true)}
              </td>
              <td className={`py-2 px-3 text-center font-medium ${retColor(r.benchmark_return)}`}>
                {fmt(r.benchmark_return, true)}
              </td>
              <td className="py-2 px-3 text-center text-slate-600">
                {r.index_volatility?.toFixed(2) ?? "—"}
              </td>
              <td className="py-2 px-3 text-center text-slate-600">
                {r.benchmark_volatility?.toFixed(2) ?? "—"}
              </td>
              <td className="py-2 px-3 text-center text-green-600">
                {fmt(r.index_max_drawdown)}
              </td>
              <td className="py-2 px-3 text-center text-green-600">
                {fmt(r.benchmark_max_drawdown)}
              </td>
              <td className="py-2 px-3 text-center text-red-600">
                {fmt(r.index_max_gain)}
              </td>
              <td className="py-2 px-3 text-center text-red-600">
                {fmt(r.benchmark_max_gain)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
