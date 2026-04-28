"use client";

import { useState } from "react";
import { HKIndexOverview } from "./HKIndexOverview";
import { HKStocksMatrix } from "./HKStocksMatrix";
import { HKMarketPanel } from "./HKMarketPanel";
import { HKFlowsPanel } from "./HKFlowsPanel";
import { HKSentimentHeatmap } from "./HKSentimentHeatmap";
import { SignalBoard } from "@/components/SignalBoard";

const DEFAULT_TICKERS = ["00700", "09988", "03690", "09961", "00100", "02513"];
const LS_KEY = "alphalens_hktech_tickers";

function loadTickers(): string[] {
  if (typeof window === "undefined") return DEFAULT_TICKERS;
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return DEFAULT_TICKERS;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) return parsed;
  } catch {
    // ignore
  }
  return DEFAULT_TICKERS;
}

export function HKTechDashboard() {
  const [tickers, setTickers] = useState<string[]>(() => loadTickers());

  const handleTickersChange = (next: string[]) => {
    setTickers(next);
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(next));
    } catch {
      // ignore
    }
  };

  return (
    <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
      <HKIndexOverview />
      <SignalBoard market="hk" tickers={tickers} />
      <HKSentimentHeatmap tickers={tickers} />
      <HKStocksMatrix tickers={tickers} onTickersChange={handleTickersChange} />
      <HKFlowsPanel tickers={tickers} />
      <HKMarketPanel />
    </main>
  );
}
