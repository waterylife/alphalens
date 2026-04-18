"use client";

import ReactECharts from "echarts-for-react";
import { BenchmarkCompare } from "@/lib/api";

export function PriceChart({ data }: { data: BenchmarkCompare }) {
  const dates = data.index.points.map((p) => p.date);
  const idxCloses = data.index.points.map((p) => p.close);
  const bmCloses = data.benchmark.points.map((p) => p.close);

  // Mean of index series
  const idxMean = idxCloses.reduce((a, b) => a + b, 0) / (idxCloses.length || 1);

  // Find max / min / latest points for index
  const idxMaxIdx = idxCloses.indexOf(Math.max(...idxCloses));
  const idxMinIdx = idxCloses.indexOf(Math.min(...idxCloses));

  const option = {
    grid: { left: 55, right: 55, top: 40, bottom: 60 },
    legend: {
      top: 5,
      data: [data.index.name, data.benchmark.name],
      textStyle: { fontSize: 12 },
    },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => v?.toFixed(2),
    },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { fontSize: 10 },
    },
    yAxis: [
      {
        type: "value",
        scale: true,
        position: "left",
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { fontSize: 10, color: "#dc2626" },
      },
      {
        type: "value",
        scale: true,
        position: "right",
        splitLine: { show: false },
        axisLabel: { fontSize: 10, color: "#2563eb" },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start: 0, end: 100 },
      { type: "slider", xAxisIndex: 0, height: 18, bottom: 15, start: 0, end: 100 },
    ],
    series: [
      {
        name: data.index.name,
        type: "line",
        yAxisIndex: 0,
        data: idxCloses,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#dc2626", width: 1.8 },
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
        markPoint: {
          symbolSize: 44,
          label: { fontSize: 10 },
          data: [
            { name: "最高", value: idxCloses[idxMaxIdx].toFixed(2), coord: [idxMaxIdx, idxCloses[idxMaxIdx]], itemStyle: { color: "#dc2626" } },
            { name: "最低", value: idxCloses[idxMinIdx].toFixed(2), coord: [idxMinIdx, idxCloses[idxMinIdx]], itemStyle: { color: "#16a34a" } },
            { name: "最新", value: idxCloses[idxCloses.length - 1].toFixed(2), coord: [idxCloses.length - 1, idxCloses[idxCloses.length - 1]], itemStyle: { color: "#f59e0b" } },
          ],
        },
        markLine: {
          symbol: "none",
          lineStyle: { color: "#94a3b8", type: "dashed", width: 1 },
          label: { formatter: `均线 ${idxMean.toFixed(2)}`, fontSize: 10, color: "#64748b" },
          data: [{ yAxis: idxMean }],
        },
      },
      {
        name: data.benchmark.name,
        type: "line",
        yAxisIndex: 1,
        data: bmCloses,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#2563eb", width: 1.2 },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 380 }} notMerge />;
}
