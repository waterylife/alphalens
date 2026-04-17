"use client";

import useSWR from "swr";
import { api, fetcher, Constituents } from "@/lib/api";

export function ConstituentsTable({ code, limit = 20 }: { code: string; limit?: number }) {
  const { data, isLoading } = useSWR<Constituents>(
    api.constituents(code, limit),
    fetcher
  );

  if (isLoading || !data) {
    return <div className="h-40 flex items-center justify-center text-slate-400">加载中…</div>;
  }

  return (
    <div className="overflow-x-auto">
      <div className="text-xs text-slate-500 mb-2 px-2">
        数据日期: {data.as_of} · 共 {data.total} 只，展示前 {data.items.length} 只
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 border-b border-slate-200">
            <th className="py-2 px-2 font-medium">#</th>
            <th className="py-2 px-2 font-medium">代码</th>
            <th className="py-2 px-2 font-medium">名称</th>
            <th className="py-2 px-2 font-medium">交易所</th>
            <th className="py-2 px-2 font-medium text-right">权重</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((it, i) => (
            <tr key={it.stock_code} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="py-2 px-2 text-slate-400">{i + 1}</td>
              <td className="py-2 px-2 font-mono text-xs">{it.stock_code}</td>
              <td className="py-2 px-2 font-medium">{it.stock_name}</td>
              <td className="py-2 px-2 text-slate-500 text-xs">{it.exchange}</td>
              <td className="py-2 px-2 text-right font-mono">
                {it.weight !== null ? it.weight.toFixed(3) + "%" : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
