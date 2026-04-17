"use client";

import ReactECharts from "echarts-for-react";
import useSWR from "swr";
import { api, fetcher, PricePoint } from "@/lib/api";

export function PriceChart({ code, years = 10 }: { code: string; years?: number }) {
  const { data, isLoading } = useSWR<{ code: string; points: PricePoint[] }>(
    api.priceHistory(code, years),
    fetcher
  );

  if (isLoading || !data) {
    return <div className="h-80 flex items-center justify-center text-slate-400">加载中…</div>;
  }

  const dates = data.points.map((p) => p.date);
  const closes = data.points.map((p) => p.close);

  const option = {
    grid: { left: 50, right: 30, top: 30, bottom: 50 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => v?.toFixed(2),
    },
    xAxis: {
      type: "category",
      data: dates,
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
        name: "收盘价",
        type: "line",
        data: closes,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#dc2626", width: 1.5 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(220,38,38,0.18)" },
              { offset: 1, color: "rgba(220,38,38,0.01)" },
            ],
          },
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 340 }} notMerge />;
}
