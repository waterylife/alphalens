"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { api, fetcher, IndexMeta, Overview, BenchmarkCompare } from "@/lib/api";
import { IndexSelector } from "@/components/IndexSelector";
import { OverviewCards } from "@/components/OverviewCards";
import { ChartCard } from "@/components/ChartCard";
import { PriceChart } from "@/components/PriceChart";
import { ValuationChart } from "@/components/ValuationChart";
import { YieldSpreadChart } from "@/components/YieldSpreadChart";
import { ConstituentsTable } from "@/components/ConstituentsTable";
import { BenchmarkSelector } from "@/components/BenchmarkSelector";
import { StatsBar } from "@/components/StatsBar";
import { YearlyBreakdownTable } from "@/components/YearlyBreakdownTable";
import {
  TimeRangePicker,
  RangeKey,
  rangeToDates,
} from "@/components/TimeRangePicker";
import { HKTechDashboard } from "@/components/hktech/HKTechDashboard";
import { USDashboard } from "@/components/ustech/USDashboard";

type Tab = "dividend" | "hktech" | "ustech";

const VALUATION_RANGES = [
  { label: "1年", value: 1 },
  { label: "3年", value: 3 },
  { label: "5年", value: 5 },
  { label: "10年", value: 10 },
];

const UPDATE_POLICIES: Record<Tab, { title: string; detail: string }> = {
  dividend: {
    title: "更新策略: 页面触发请求",
    detail:
      "红利指数数据在进入、刷新或切回页面时请求；后端估值概览缓存 10 分钟，日线/估值历史缓存 4 小时。",
  },
  hktech: {
    title: "更新策略: 前端轮询 + 后端缓存",
    detail:
      "港股个股报价/指数每 60 秒请求一次；ETF/收益/资金 5 分钟，技术面 10 分钟，流动性 15 分钟，基本面 60 分钟。后端报价缓存约 10 分钟，Futu 资金缓存约 5 分钟，历史/基本面缓存 4 小时。",
  },
  ustech: {
    title: "更新策略: 前端轮询 + 后端缓存",
    detail:
      "美股个股报价每 60 秒请求一次，指数 10 分钟；板块/宏观/收益 5 分钟，技术面 10 分钟，综合信号 15 分钟，基本面 60 分钟。后端个股报价缓存约 5 分钟，历史/基本面缓存 4 小时。",
  },
};

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("dividend");

  const { data: indices } = useSWR<IndexMeta[]>(api.indices(), fetcher);
  const [selected, setSelected] = useState<string | null>(null);

  // Main chart state
  const [benchmark, setBenchmark] = useState("000300");
  const [rangeKey, setRangeKey] = useState<RangeKey>("10y");
  const defaultStart = useMemo(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 10);
    return d.toISOString().substring(0, 10);
  }, []);
  const today = useMemo(() => new Date().toISOString().substring(0, 10), []);
  const [customStart, setCustomStart] = useState(defaultStart);
  const [customEnd, setCustomEnd] = useState(today);

  // Valuation/yield charts use a separate simpler range
  const [valuationYears, setValuationYears] = useState(10);

  const selectedCode = selected ?? indices?.[0]?.code ?? null;

  const { data: overview } = useSWR<Overview>(
    selectedCode ? api.overview(selectedCode) : null,
    fetcher
  );

  const { start: rangeStart, end: rangeEnd } =
    rangeKey === "custom"
      ? { start: customStart, end: customEnd }
      : rangeToDates(rangeKey);

  const { data: compare } = useSWR<BenchmarkCompare>(
    selectedCode
      ? api.benchmarkCompare(selectedCode, benchmark, rangeStart, rangeEnd)
      : null,
    fetcher
  );

  const current = indices?.find((i) => i.code === selectedCode);

  const handleRangeChange = (k: RangeKey, s?: string, e?: string) => {
    setRangeKey(k);
    if (k === "custom" && s && e) {
      setCustomStart(s);
      setCustomEnd(e);
    }
  };

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">AlphaLens</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              价值投资视角 · 数据看板
            </p>
          </div>
          <div className="text-xs text-slate-500">
            数据源: akshare (T+1) · 中证指数 / 乐咕乐股 / 腾讯财经
          </div>
        </div>

        {/* Tab nav */}
        <div className="max-w-7xl mx-auto px-6 flex gap-0">
          {(
            [
              { key: "dividend", label: "红利指数" },
              { key: "hktech", label: "港股科技" },
              { key: "ustech", label: "美股科技" },
            ] as { key: Tab; label: string }[]
          ).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="max-w-7xl mx-auto px-6 pb-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <span className="font-medium text-slate-700">
              {UPDATE_POLICIES[activeTab].title}
            </span>
            <span className="mx-1.5 text-slate-300">/</span>
            <span>{UPDATE_POLICIES[activeTab].detail}</span>
          </div>
        </div>
      </header>

      {activeTab === "ustech" ? (
        <USDashboard />
      ) : activeTab === "hktech" ? (
        <HKTechDashboard />
      ) : (
        <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
          <section>
            <div className="text-xs text-slate-500 mb-2">选择指数</div>
            {indices ? (
              <IndexSelector
                indices={indices}
                selected={selectedCode || ""}
                onSelect={setSelected}
              />
            ) : (
              <div className="text-slate-400 text-sm">加载指数列表…</div>
            )}
            {current && (
              <p className="text-sm text-slate-600 mt-3">{current.description}</p>
            )}
          </section>

          {selectedCode && overview && (
            <section>
              <OverviewCards data={overview} />
            </section>
          )}

          {selectedCode && (
            <>
              <ChartCard
                title="指数走势 · 基准对比"
                description="与基准指数同期走势、收益、回撤、波动率对比"
                action={
                  <BenchmarkSelector value={benchmark} onChange={setBenchmark} />
                }
              >
                <div className="px-2 pb-2">
                  <TimeRangePicker
                    value={rangeKey}
                    customStart={customStart}
                    customEnd={customEnd}
                    onChange={handleRangeChange}
                  />
                </div>

                {compare ? (
                  <>
                    <PriceChart data={compare} />
                    <StatsBar index={compare.index} benchmark={compare.benchmark} />
                    <YearlyBreakdownTable
                      rows={compare.yearly}
                      indexName={compare.index.name}
                      benchmarkName={compare.benchmark.name}
                    />
                  </>
                ) : (
                  <div className="h-80 flex items-center justify-center text-slate-400">
                    加载中…
                  </div>
                )}
              </ChartCard>

              <section className="flex items-center gap-2 text-sm">
                <span className="text-slate-500">估值时间范围:</span>
                {VALUATION_RANGES.map((r) => (
                  <button
                    key={r.value}
                    onClick={() => setValuationYears(r.value)}
                    className={`px-3 py-1 rounded-md border text-xs transition ${
                      valuationYears === r.value
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </section>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard
                  title="市盈率 (PE TTM)"
                  description="含历史分位参考线，越低越便宜"
                >
                  <ValuationChart code={selectedCode} years={valuationYears} metric="pe_ttm" />
                </ChartCard>
                <ChartCard
                  title="股息率"
                  description="含历史分位参考线，越高越便宜"
                >
                  <ValuationChart
                    code={selectedCode}
                    years={valuationYears}
                    metric="dividend_yield"
                  />
                </ChartCard>
              </div>

              <ChartCard
                title="股息率 vs 10Y 国债收益率"
                description="利差反映红利资产相对债券的吸引力，>2% 通常较有吸引力"
              >
              <YieldSpreadChart code={selectedCode} years={valuationYears} />
              </ChartCard>

              <ChartCard
                title="成分股权重"
                description="按权重排序，展示前 20 大成分股"
              >
              <ConstituentsTable code={selectedCode} limit={20} />
              </ChartCard>
            </>
          )}
        </main>
      )}

      <footer className="py-8 text-center text-xs text-slate-400">
        AlphaLens v0.1 · 数据仅供参考，不构成投资建议
      </footer>
    </div>
  );
}
