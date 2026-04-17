"use client";

import ReactECharts from "echarts-for-react";
import useSWR from "swr";
import { api, fetcher, YieldSpreadSeries } from "@/lib/api";

export function YieldSpreadChart({ code, years = 10 }: { code: string; years?: number }) {
  const { data, isLoading } = useSWR<YieldSpreadSeries>(
    api.yieldSpread(code, years),
    fetcher
  );

  if (isLoading || !data) {
    return <div className="h-80 flex items-center justify-center text-slate-400">加载中…</div>;
  }

  const dates = data.points.map((p) => p.date);
  const div = data.points.map((p) => p.dividend_yield);
  const y10 = data.points.map((p) => p.yield_10y);
  const spread = data.points.map((p) => p.spread);

  const option = {
    grid: { left: 50, right: 60, top: 40, bottom: 50 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => (v != null ? v.toFixed(2) + "%" : "—"),
    },
    legend: { data: ["指数股息率", "10Y国债收益率", "利差"], top: 0 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
    },
    yAxis: [
      {
        type: "value",
        name: "收益率 %",
        scale: true,
        splitLine: { lineStyle: { color: "#f1f5f9" } },
      },
      {
        type: "value",
        name: "利差 %",
        scale: true,
        position: "right",
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "指数股息率",
        type: "line",
        data: div,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#059669", width: 1.5 },
      },
      {
        name: "10Y国债收益率",
        type: "line",
        data: y10,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#64748b", width: 1.5 },
      },
      {
        name: "利差",
        type: "line",
        yAxisIndex: 1,
        data: spread,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#dc2626", width: 1.5, type: "dashed" },
        areaStyle: { color: "rgba(220,38,38,0.08)" },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 340 }} notMerge />;
}
