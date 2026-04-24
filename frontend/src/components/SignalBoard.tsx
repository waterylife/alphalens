"use client";

// Standalone multi-dimensional signal board.
// Displays buy/hold/sell recommendations computed from a weighted score across
// valuation / momentum / quality (or flow) / risk (or liquidity) / macro.
// Deliberately placed OUTSIDE the sentiment heatmap card so users don't read
// the pill as sentiment-only.

import useSWR from "swr";
import {
  api, fetcher,
  USStockSnapshot, USStrategySignal,
  HKStockSnapshot, HKStrategySignal,
} from "@/lib/api";
import { ActionPill, StrategySignalLike } from "@/components/ActionPill";

type Market = "us" | "hk";

interface Props {
  market: Market;
  tickers: string[];
}

// Weight schema shown in the header — keep in sync with backend scoring.
const WEIGHTS: Record<Market, { label: string; weight: number; accent: string }[]> = {
  us: [
    { label: "估值",   weight: 35, accent: "bg-blue-400"    },
    { label: "动量",   weight: 30, accent: "bg-amber-400"   },
    { label: "质量",   weight: 25, accent: "bg-emerald-400" },
    { label: "风险",   weight: 10, accent: "bg-rose-400"    },
  ],
  hk: [
    { label: "估值",   weight: 30, accent: "bg-blue-400"    },
    { label: "动量",   weight: 30, accent: "bg-amber-400"   },
    { label: "资金",   weight: 30, accent: "bg-emerald-400" },
    { label: "流动性", weight: 10, accent: "bg-sky-400"     },
  ],
};

// Pull the five component scores into a uniform tuple for the stacked bar.
// Returns [valuation, momentum, quality/flow, risk/liquidity, macroDelta].
function components(market: Market, sig: USStrategySignal | HKStrategySignal): (number | null)[] {
  const c = sig.components;
  if (market === "us") {
    const u = c as USStrategySignal["components"];
    return [u.valuation ?? null, u.momentum ?? null, u.quality ?? null, u.risk ?? null, u.macro_delta ?? null];
  }
  const h = c as HKStrategySignal["components"];
  return [h.valuation ?? null, h.momentum ?? null, h.flow ?? null, h.liquidity ?? null, h.macro_delta ?? null];
}

function ScoreBar({ market, sig }: { market: Market; sig: USStrategySignal | HKStrategySignal }) {
  const parts = components(market, sig).slice(0, 4); // drop macro_delta — rendered separately
  const weights = WEIGHTS[market];
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      {parts.map((v, i) => {
        const max = weights[i].weight;
        const ratio = v == null ? 0 : Math.max(0, Math.min(1, v / max));
        return (
          <div
            key={i}
            className="h-full"
            style={{ width: `${weights[i].weight}%` }}
            title={`${weights[i].label}: ${v == null ? "—" : v.toFixed(1)} / ${max}`}
          >
            <div className={`h-full ${weights[i].accent}`} style={{ width: `${ratio * 100}%` }} />
          </div>
        );
      })}
    </div>
  );
}

export function SignalBoard({ market, tickers }: Props) {
  const snapUrl = market === "us" ? api.usSnapshot(tickers) : api.hkSnapshot(tickers);
  const sigUrl  = market === "us" ? api.usSignals(tickers) : api.hkSignals(tickers);

  const { data: snaps } = useSWR<(USStockSnapshot | HKStockSnapshot)[]>(
    tickers.length ? snapUrl : null, fetcher, { refreshInterval: 60_000 }
  );
  const { data: sigs } = useSWR<(USStrategySignal | HKStrategySignal)[]>(
    tickers.length ? sigUrl : null, fetcher, { refreshInterval: 15 * 60_000 }
  );
  const snapMap = new Map(snaps?.map((s) => [s.ticker, s]) ?? []);
  const sigMap  = new Map(sigs?.map((s) => [s.ticker, s]) ?? []);

  const weights = WEIGHTS[market];

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-violet-500 p-5">
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-violet-500" />
            <h3 className="text-base font-semibold text-slate-900">
              综合信号 · <span className="text-violet-700">多维度打分</span>
            </h3>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            基于估值 / 动量 / {market === "us" ? "质量 / 风险" : "资金 / 流动性"} / 宏观加权计算，非单一情绪读数
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {weights.map((w) => (
            <span key={w.label} className="inline-flex items-center gap-1 text-[10px] text-slate-500">
              <span className={`w-2 h-2 rounded-sm ${w.accent}`} />
              {w.label} {w.weight}
            </span>
          ))}
          <span className="inline-flex items-center gap-1 text-[10px] text-slate-400">宏观 ±5</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {tickers.map((t) => {
          const s = snapMap.get(t);
          const sig = sigMap.get(t);
          const macro = sig ? components(market, sig)[4] : null;
          return (
            <div key={t} className="border border-slate-200 rounded-lg p-3 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-mono text-[10px] text-slate-400">{t}</span>
                    <span className="text-xs font-medium text-slate-800 truncate">{s?.name ?? "—"}</span>
                  </div>
                  {sig?.score != null && (
                    <div className="text-[11px] text-slate-500 tabular-nums mt-0.5">
                      评分 <span className="font-semibold text-slate-800">{sig.score.toFixed(0)}</span>
                      <span className="text-slate-300"> / 100</span>
                      {macro != null && macro !== 0 && (
                        <span className={`ml-1.5 text-[10px] ${macro > 0 ? "text-emerald-600" : "text-rose-500"}`}>
                          宏观 {macro > 0 ? "+" : ""}{macro.toFixed(1)}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <ActionPill sig={sig as StrategySignalLike | undefined} size="sm" />
              </div>

              {sig && <ScoreBar market={market} sig={sig} />}

              {sig?.explanation && (
                <p
                  className="text-[11px] text-slate-500 leading-relaxed line-clamp-2"
                  title={sig.explanation + (sig.triggers.length ? `\n\n触发规则:\n· ${sig.triggers.join("\n· ")}` : "")}
                >
                  {sig.explanation}
                </p>
              )}
              {!sig && (
                <p className="text-[11px] text-slate-300">加载中…</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 text-[10px] text-slate-400">
        打分由规则引擎生成（非 LLM）· 中文解释由 MiniMax 生成 · 悬停解释查看触发规则
      </div>
    </div>
  );
}
