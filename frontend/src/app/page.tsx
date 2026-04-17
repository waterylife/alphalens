"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { api, fetcher, IndexMeta, Overview } from "@/lib/api";
import { IndexSelector } from "@/components/IndexSelector";
import { OverviewCards } from "@/components/OverviewCards";
import { ChartCard } from "@/components/ChartCard";
import { PriceChart } from "@/components/PriceChart";
import { ValuationChart } from "@/components/ValuationChart";
import { YieldSpreadChart } from "@/components/YieldSpreadChart";
import { ConstituentsTable } from "@/components/ConstituentsTable";

const RANGE_OPTIONS = [
  { label: "1年", value: 1 },
  { label: "3年", value: 3 },
  { label: "5年", value: 5 },
  { label: "10年", value: 10 },
];

export default function Home() {
  const { data: indices } = useSWR<IndexMeta[]>(api.indices(), fetcher);
  const [selected, setSelected] = useState<string | null>(null);
  const [years, setYears] = useState(10);

  useEffect(() => {
    if (indices && indices.length > 0 && !selected) {
      setSelected(indices[0].code);
    }
  }, [indices, selected]);

  const { data: overview } = useSWR<Overview>(
    selected ? api.overview(selected) : null,
    fetcher
  );

  const current = indices?.find((i) => i.code === selected);

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">AlphaLens · 红利指数看板</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              价值投资视角 · 估值分位 · 股息率利差 · 成分股透视
            </p>
          </div>
          <div className="text-xs text-slate-500">
            数据源: akshare (T+1) · 中证指数 / 乐咕乐股 / 腾讯财经
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <section>
          <div className="text-xs text-slate-500 mb-2">选择指数</div>
          {indices ? (
            <IndexSelector
              indices={indices}
              selected={selected || ""}
              onSelect={setSelected}
            />
          ) : (
            <div className="text-slate-400 text-sm">加载指数列表…</div>
          )}
          {current && (
            <p className="text-sm text-slate-600 mt-3">{current.description}</p>
          )}
        </section>

        {selected && overview && (
          <section>
            <OverviewCards data={overview} />
          </section>
        )}

        <section className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">时间范围:</span>
          {RANGE_OPTIONS.map((r) => (
            <button
              key={r.value}
              onClick={() => setYears(r.value)}
              className={`px-3 py-1 rounded-md border text-xs transition ${
                years === r.value
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
              }`}
            >
              {r.label}
            </button>
          ))}
        </section>

        {selected && (
          <>
            <ChartCard title="指数走势" description={`过去 ${years} 年收盘价曲线`}>
              <PriceChart code={selected} years={years} />
            </ChartCard>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ChartCard
                title="市盈率 (PE TTM)"
                description="含历史分位参考线，越低越便宜"
              >
                <ValuationChart code={selected} years={years} metric="pe_ttm" />
              </ChartCard>
              <ChartCard
                title="股息率"
                description="含历史分位参考线，越高越便宜"
              >
                <ValuationChart
                  code={selected}
                  years={years}
                  metric="dividend_yield"
                />
              </ChartCard>
            </div>

            <ChartCard
              title="股息率 vs 10Y 国债收益率"
              description="利差反映红利资产相对债券的吸引力，>2% 通常较有吸引力"
            >
              <YieldSpreadChart code={selected} years={years} />
            </ChartCard>

            <ChartCard
              title="成分股权重"
              description="按权重排序，展示前 20 大成分股"
            >
              <ConstituentsTable code={selected} limit={20} />
            </ChartCard>
          </>
        )}
      </main>

      <footer className="py-8 text-center text-xs text-slate-400">
        AlphaLens v0.1 · 数据仅供参考，不构成投资建议
      </footer>
    </div>
  );
}
