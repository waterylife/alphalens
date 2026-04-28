"use client";

import ReactECharts from "echarts-for-react";
import { AllocationBucket, PortfolioSummary } from "@/lib/api";

const FALLBACK_PALETTE = [
  "#2563eb",
  "#dc2626",
  "#16a34a",
  "#9333ea",
  "#ea580c",
  "#0891b2",
  "#ca8a04",
  "#db2777",
  "#4f46e5",
  "#059669",
];

const COLOR_BY_KEY: Record<string, string> = {
  中国: "#dc2626",
  香港: "#0d9488",
  美国: "#2563eb",
  股票: "#2563eb",
  债券: "#16a34a",
  现金: "#f59e0b",
  黄金: "#eab308",
  红利低波: "#dc2626",
  价值成长: "#2563eb",
  纯债: "#16a34a",
  混合债券: "#65a30d",
  黄金虚拟币: "#eab308",
  "黄金/虚拟币": "#eab308",
  待卖出: "#f97316",
  未分类: "#94a3b8",
  富途证券: "#7c3aed",
  天天基金: "#0ea5e9",
  东方财富: "#ef4444",
};

function colorFor(key: string, index: number) {
  return COLOR_BY_KEY[key] ?? FALLBACK_PALETTE[index % FALLBACK_PALETTE.length];
}

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
      itemWidth: 14,
      itemHeight: 10,
      textStyle: { fontSize: 11, color: "#475569" },
    },
    series: [
      {
        type: "pie",
        radius: ["40%", "62%"],
        center: ["50%", "52%"],
        avoidLabelOverlap: true,
        minShowLabelAngle: 12,
        label: {
          show: true,
          overflow: "break",
          width: 68,
          formatter: (p: { name: string; percent: number }) =>
            p.percent >= 5 ? `${p.name}\n${p.percent.toFixed(1)}%` : "",
          fontSize: 11,
          color: "#334155",
        },
        labelLine: {
          show: true,
          length: 8,
          length2: 10,
          minTurnAngle: 90,
          lineStyle: { color: "#94a3b8" },
        },
        labelLayout: {
          hideOverlap: true,
          moveOverlap: "shiftY",
        },
        itemStyle: {
          borderColor: "#ffffff",
          borderWidth: 2,
        },
        data: buckets.map((b, index) => ({
          name: b.key,
          value: b.market_value_cny,
          itemStyle: { color: colorFor(b.key, index) },
        })),
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
          className="bg-white border border-slate-200 rounded-lg shadow-sm"
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
