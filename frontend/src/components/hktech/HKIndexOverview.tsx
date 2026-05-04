"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher, BenchmarkCompare } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { StatsBar } from "@/components/StatsBar";
import { YearlyBreakdownTable } from "@/components/YearlyBreakdownTable";

const RANGES = [
  { label: "1年", value: 1 },
  { label: "3年", value: 3 },
  { label: "5年", value: 5 },
];

function fmt(value: number | null | undefined, digits = 2, suffix = "") {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}${suffix}`;
}

function signed(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function colorSigned(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "text-slate-500";
  return value >= 0 ? "text-red-600" : "text-green-600";
}

function returnFromDays(data: BenchmarkCompare | undefined, days: number) {
  const points = data?.index.points ?? [];
  const latest = points.at(-1);
  if (!latest) return null;

  const cutoff = new Date(latest.date);
  cutoff.setDate(cutoff.getDate() - days);
  const cutStr = cutoff.toISOString().slice(0, 10);
  const base = [...points].reverse().find((p) => p.date <= cutStr);
  if (!base || base.close === 0) return null;
  return (latest.close / base.close - 1) * 100;
}

function MetricCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
      <div className="text-xs text-slate-500 mb-2">{label}</div>
      <div className={`text-3xl font-semibold text-slate-900 ${tone ?? ""}`}>
        {value}
      </div>
      <div className="mt-2 text-sm text-slate-500">{sub}</div>
    </div>
  );
}

export function HKIndexOverview() {
  const [years, setYears] = useState(3);
  const { data, isLoading } = useSWR<BenchmarkCompare>(
    api.hkIndexCompare(years),
    fetcher,
    { refreshInterval: 10 * 60_000 }
  );

  const points = data?.index.points ?? [];
  const latest = points.at(-1);
  const previous = points.at(-2);
  const latestClose = latest?.close ?? null;
  const change1d =
    latest && previous && previous.close !== 0
      ? (latest.close / previous.close - 1) * 100
      : null;
  const ret1m = returnFromDays(data, 30);
  const indexRet = data?.index.stats.return_pct ?? null;
  const benchmarkRet = data?.benchmark.stats.return_pct ?? null;
  const excess =
    indexRet != null && benchmarkRet != null ? indexRet - benchmarkRet : null;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">恒生科技指数</h2>
          <p className="text-sm text-slate-500 mt-1">
            与恒生指数基准对比 · 收益、回撤、波动与年度拆解
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">时间范围:</span>
          {RANGES.map((range) => (
            <button
              key={range.value}
              onClick={() => setYears(range.value)}
              className={`px-3 py-1 rounded-md border text-xs transition ${
                years === range.value
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="最新收盘"
          value={fmt(latestClose, 2)}
          sub={`今日 ${signed(change1d)} · ${latest?.date ?? "—"}`}
          tone={colorSigned(change1d)}
        />
        <MetricCard
          label="近 1 月"
          value={signed(ret1m)}
          sub="短期动量"
          tone={colorSigned(ret1m)}
        />
        <MetricCard
          label={`${years} 年累计收益`}
          value={signed(indexRet)}
          sub={`恒生指数 ${signed(benchmarkRet)}`}
          tone={colorSigned(indexRet)}
        />
        <MetricCard
          label="相对恒生指数"
          value={signed(excess)}
          sub={`年化 ${signed(data?.index.stats.annualized_pct)} · 波动 ${fmt(data?.index.stats.volatility, 2, "%")}`}
          tone={colorSigned(excess)}
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
        <div className="px-5 pt-5 pb-3 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              指数走势 · 基准对比
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              恒生科技指数 vs 恒生指数，按共同交易日对齐
            </p>
          </div>
          <div className="text-xs text-slate-400">
            数据源: Sina · 后端历史缓存 4 小时
          </div>
        </div>

        {data && data.index.points.length > 0 ? (
          <>
            <PriceChart data={data} />
            <StatsBar index={data.index} benchmark={data.benchmark} />
            <YearlyBreakdownTable
              rows={data.yearly}
              indexName={data.index.name}
              benchmarkName={data.benchmark.name}
            />
          </>
        ) : (
          <div className="h-80 flex items-center justify-center text-slate-400 text-sm">
            {isLoading ? "加载中…" : "暂无指数对比数据"}
          </div>
        )}
      </div>
    </section>
  );
}
