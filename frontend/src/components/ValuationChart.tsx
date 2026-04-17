"use client";

import ReactECharts from "echarts-for-react";
import useSWR from "swr";
import { api, fetcher, ValuationSeries } from "@/lib/api";

// Compute percentile reference lines (20, 50, 80%) across the series.
function percentiles(values: number[]) {
  const arr = values.filter((v) => v != null && !Number.isNaN(v)).sort((a, b) => a - b);
  if (arr.length === 0) return { p20: null, p50: null, p80: null };
  const q = (p: number) => arr[Math.min(arr.length - 1, Math.floor(arr.length * p))];
  return { p20: q(0.2), p50: q(0.5), p80: q(0.8) };
}

export function ValuationChart({
  code,
  years = 10,
  metric,
}: {
  code: string;
  years?: number;
  metric: "pe_ttm" | "dividend_yield" | "pb";
}) {
  const { data, isLoading } = useSWR<ValuationSeries>(
    api.valuationHistory(code, years),
    fetcher
  );

  if (isLoading || !data) {
    return <div className="h-80 flex items-center justify-center text-slate-400">加载中…</div>;
  }

  const series = data[metric] || [];
  const values = series.map((p) => p.value).filter((v): v is number => v != null);
  const { p20, p50, p80 } = percentiles(values);

  const titleMap: Record<string, { name: string; color: string; unit: string }> = {
    pe_ttm: { name: "市盈率 TTM", color: "#2563eb", unit: "" },
    dividend_yield: { name: "股息率", color: "#059669", unit: "%" },
    pb: { name: "市净率 PB", color: "#7c3aed", unit: "" },
  };
  const cfg = titleMap[metric];

  const option = {
    grid: { left: 50, right: 30, top: 30, bottom: 50 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => v?.toFixed(2) + cfg.unit,
    },
    legend: { data: [cfg.name, "20%分位", "50%分位", "80%分位"], top: 0 },
    xAxis: {
      type: "category",
      data: series.map((p) => p.date),
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start: 0, end: 100 },
      { type: "slider", xAxisIndex: 0, height: 20, bottom: 10, start: 0, end: 100 },
    ],
    series: [
      {
        name: cfg.name,
        type: "line",
        data: series.map((p) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: cfg.color, width: 1.5 },
        markLine: {
          symbol: "none",
          silent: true,
          data: [
            ...(p20 !== null
              ? [{ name: "20%", yAxis: p20, label: { formatter: "20% 低分位" }, lineStyle: { color: "#10b981", type: "dashed" } }]
              : []),
            ...(p50 !== null
              ? [{ name: "50%", yAxis: p50, label: { formatter: "中位数" }, lineStyle: { color: "#64748b", type: "dashed" } }]
              : []),
            ...(p80 !== null
              ? [{ name: "80%", yAxis: p80, label: { formatter: "80% 高分位" }, lineStyle: { color: "#ef4444", type: "dashed" } }]
              : []),
          ],
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 340 }} notMerge />;
}
