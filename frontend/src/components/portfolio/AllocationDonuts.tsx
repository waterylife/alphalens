"use client";

import ReactECharts from "echarts-for-react";
import { AllocationBucket, PortfolioSummary } from "@/lib/api";

const PALETTE = [
  "#0f172a",
  "#475569",
  "#94a3b8",
  "#0ea5e9",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#14b8a6",
  "#eab308",
];

function donutOption(title: string, buckets: AllocationBucket[]) {
  return {
    tooltip: {
      trigger: "item",
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/>¥${p.value.toLocaleString("zh-CN", {
          maximumFractionDigits: 0,
        })} (${p.percent.toFixed(2)}%)`,
    },
    title: {
      text: title,
      left: "center",
      top: 6,
      textStyle: { fontSize: 13, fontWeight: 600, color: "#0f172a" },
    },
    legend: {
      type: "scroll",
      orient: "horizontal",
      bottom: 0,
      textStyle: { fontSize: 11, color: "#475569" },
    },
    color: PALETTE,
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        center: ["50%", "52%"],
        avoidLabelOverlap: true,
        label: {
          show: true,
          formatter: "{b}\n{d}%",
          fontSize: 11,
          color: "#334155",
        },
        labelLine: { length: 8, length2: 8 },
        data: buckets.map((b) => ({ name: b.key, value: b.market_value_cny })),
      },
    ],
  };
}

export function AllocationDonuts({ data }: { data: PortfolioSummary }) {
  const charts: { title: string; buckets: AllocationBucket[] }[] = [
    { title: "市场分布", buckets: data.by_market },
    { title: "资产类型分布", buckets: data.by_asset_class },
    { title: "一级标签分布", buckets: data.by_tag_l1 },
    { title: "交易平台分布", buckets: data.by_broker },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {charts.map((c) => (
        <div
          key={c.title}
          className="bg-white border border-slate-200 rounded-xl shadow-sm"
        >
          <ReactECharts
            option={donutOption(c.title, c.buckets)}
            style={{ height: 280 }}
            notMerge
          />
        </div>
      ))}
    </div>
  );
}
