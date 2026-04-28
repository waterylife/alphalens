"use client";

import useSWR from "swr";
import { api, fetcher, HKIndexChart } from "@/lib/api";
import ReactECharts from "echarts-for-react";

function ChangeTag({ value }: { value: number | null }) {
  if (value == null) return <span className="text-slate-400 text-xs">—</span>;
  const pos = value >= 0;
  return (
    <span
      className={`text-sm font-medium ${pos ? "text-green-600" : "text-red-500"}`}
    >
      {pos ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

export function HKIndexOverview() {
  const { data: chart } = useSWR<HKIndexChart>(
    api.hkIndexChart(1),
    fetcher,
    { refreshInterval: 60_000 }
  );

  const points = chart?.points ?? [];
  const latest = points.at(-1);
  const prev = points.at(-2);

  const latestClose = latest?.close ?? null;
  const change1d =
    latest && prev ? ((latest.close / prev.close - 1) * 100) : null;

  // Calculate returns from chart data
  function retFromDaysAgo(days: number): number | null {
    if (!latest || points.length < 2) return null;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const cutStr = cutoff.toISOString().slice(0, 10);
    const base = [...points].reverse().find((p) => p.date <= cutStr);
    if (!base) return null;
    return ((latest.close / base.close - 1) * 100);
  }

  const ret1m = retFromDaysAgo(30);

  const chartOption = {
    grid: { top: 8, bottom: 24, left: 48, right: 16 },
    xAxis: {
      type: "category",
      data: points.map((p) => p.date),
      axisLabel: {
        fontSize: 10,
        color: "#94a3b8",
        formatter: (v: string) => v.slice(0, 7),
        showMaxLabel: true,
      },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { fontSize: 10, color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    series: [
      {
        type: "line",
        data: points.map((p) => p.close),
        smooth: false,
        symbol: "none",
        lineStyle: { color: "#6366f1", width: 1.5 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(99,102,241,0.15)" },
              { offset: 1, color: "rgba(99,102,241,0)" },
            ],
          },
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown[]) => {
        const p = (params as { name: string; value: number }[])[0];
        return `${p.name}<br/><b>${p.value.toFixed(2)}</b>`;
      },
    },
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900">恒生科技指数 HSTECH</h3>
          <p className="text-xs text-slate-500 mt-0.5">板块基准 · 近 1 年走势</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-slate-900">
            {latestClose != null ? latestClose.toFixed(2) : "—"}
          </div>
          <div className="flex items-center gap-3 justify-end mt-0.5">
            <span className="text-xs text-slate-400">今日</span>
            <ChangeTag value={change1d} />
            <span className="text-xs text-slate-400 ml-2">1M</span>
            <ChangeTag value={ret1m} />
          </div>
        </div>
      </div>

      {points.length > 0 ? (
        <ReactECharts
          option={chartOption}
          style={{ height: 160 }}
          notMerge
        />
      ) : (
        <div className="h-40 flex items-center justify-center text-slate-400 text-sm">
          加载中…
        </div>
      )}
    </div>
  );
}
