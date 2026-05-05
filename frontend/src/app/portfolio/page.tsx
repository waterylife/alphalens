"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher, Holding, PortfolioSummary } from "@/lib/api";
import { SummaryBar } from "@/components/portfolio/SummaryBar";
import { AllocationDonuts } from "@/components/portfolio/AllocationDonuts";
import { HoldingsTable } from "@/components/portfolio/HoldingsTable";
import { SyncControls } from "@/components/portfolio/SyncControls";
import { PortfolioTargetsPanel } from "@/components/portfolio/PortfolioTargetsPanel";
import { PortfolioTagConfigPanel } from "@/components/portfolio/PortfolioTagConfigPanel";

type PortfolioTab = "dashboard" | "tags";

export default function PortfolioPage() {
  const [tab, setTab] = useState<PortfolioTab>("dashboard");
  const { data: summary, error: summaryErr } = useSWR<PortfolioSummary>(
    api.portfolioSummary(),
    fetcher
  );
  const { data: holdings, error: holdingsErr } = useSWR<Holding[]>(
    api.portfolioHoldings(),
    fetcher
  );

  const error = summaryErr || holdingsErr;

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">持仓管理</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              本地持仓快照 · 多币种已折算 CNY · 后续接入富途 / 截图导入
            </p>
            <div className="mt-4 flex items-center gap-2">
              <TabButton active={tab === "dashboard"} onClick={() => setTab("dashboard")}>
                持仓看板
              </TabButton>
              <TabButton active={tab === "tags"} onClick={() => setTab("tags")}>
                持仓标签配置
              </TabButton>
            </div>
          </div>
          <div className="text-xs text-slate-500">
            数据源: 本地 SQLite · 由 Google Sheet CSV 种子数据导入
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {tab === "dashboard" && error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4 text-sm">
            数据加载失败：{String(error)}
          </div>
        )}

        {tab === "dashboard" ? (
          <>
            <SyncControls />

            {summary ? (
              <SummaryBar data={summary} />
            ) : (
              <div className="h-28 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-400">
                加载汇总…
              </div>
            )}

            {summary ? (
              <AllocationDonuts data={summary} />
            ) : (
              <div className="h-72 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-400">
                加载分布…
              </div>
            )}

            {holdings ? (
              <HoldingsTable rows={holdings} />
            ) : (
              <div className="h-96 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-400">
                加载持仓表…
              </div>
            )}

            <PortfolioTargetsPanel />
          </>
        ) : (
          <PortfolioTagConfigPanel />
        )}
      </main>

      <footer className="py-8 text-center text-xs text-slate-400">
        AlphaLens · 持仓页 v0.1 · 数据仅供参考，不构成投资建议
      </footer>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-9 rounded-md px-3 text-sm transition ${
        active
          ? "bg-slate-900 text-white"
          : "border border-slate-200 bg-white text-slate-600 hover:border-slate-400"
      }`}
    >
      {children}
    </button>
  );
}
