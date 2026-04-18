"use client";

import useSWR from "swr";
import { api, fetcher, BenchmarkMeta } from "@/lib/api";

interface Props {
  value: string;
  onChange: (code: string) => void;
}

export function BenchmarkSelector({ value, onChange }: Props) {
  const { data } = useSWR<BenchmarkMeta[]>(api.benchmarks(), fetcher);

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-500">业绩比较基准:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-2.5 py-1 rounded-md border border-slate-200 text-slate-700 bg-white hover:border-slate-400"
      >
        {(data ?? []).map((b) => (
          <option key={b.code} value={b.code}>
            {b.name} ({b.code})
          </option>
        ))}
      </select>
    </div>
  );
}
