"use client";

import { useState } from "react";
import { Overview, ValuationWindow } from "@/lib/api";

const VALUATION_WINDOWS: { key: ValuationWindow; label: string }[] = [
  { key: "1y", label: "1年" },
  { key: "3y", label: "3年" },
  { key: "5y", label: "5年" },
  { key: "10y", label: "10年" },
  { key: "all", label: "全部" },
];

function fmt(n: number | null | undefined, digits = 2, suffix = "") {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits) + suffix;
}

function trendClass(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-slate-600";
  if (v > 0) return "text-rose-600";
  if (v < 0) return "text-emerald-600";
  return "text-slate-600";
}

function percentileLabel(p: number | null | undefined, inverted = false) {
  // inverted: higher = cheaper (for dividend yield, higher yield = cheap)
  if (p === null || p === undefined) return { text: "—", cls: "bg-slate-100 text-slate-500" };
  const cheapSide = inverted ? p >= 70 : p <= 30;
  const pricySide = inverted ? p <= 30 : p >= 70;
  if (cheapSide) return { text: `低估 ${p.toFixed(0)}%`, cls: "bg-emerald-100 text-emerald-700" };
  if (pricySide) return { text: `高估 ${p.toFixed(0)}%`, cls: "bg-rose-100 text-rose-700" };
  return { text: `中性 ${p.toFixed(0)}%`, cls: "bg-amber-100 text-amber-700" };
}

function WindowButtons({
  window: activeWindow,
  onSelect,
  available,
}: {
  window: ValuationWindow;
  onSelect: (w: ValuationWindow) => void;
  available: Record<ValuationWindow, number | null>;
}) {
  return (
    <div className="flex gap-0.5 mt-1">
      {VALUATION_WINDOWS.map((w) => {
        const active = w.key === activeWindow;
        const disabled = available?.[w.key] == null;
        return (
          <button
            key={w.key}
            onClick={() => !disabled && onSelect(w.key)}
            disabled={disabled}
            className={`px-1.5 py-0.5 text-[10px] rounded border transition ${
              active
                ? "bg-slate-900 text-white border-slate-900"
                : disabled
                ? "bg-slate-50 text-slate-300 border-slate-100 cursor-not-allowed"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
            }`}
          >
            {w.label}
          </button>
        );
      })}
    </div>
  );
}

export function OverviewCards({ data }: { data: Overview }) {
  const [peWindow, setPeWindow] = useState<ValuationWindow>("10y");
  const [dyWindow, setDyWindow] = useState<ValuationWindow>("10y");
  const pePct = data.pe_percentile?.[peWindow] ?? null;
  const dyPct = data.dividend_yield_percentile?.[dyWindow] ?? null;

  const cards = [
    {
      label: "最新收盘",
      main: fmt(data.close, 2),
      sub: (
        <span className={trendClass(data.change_pct)}>
          {data.change_pct && data.change_pct > 0 ? "+" : ""}
          {fmt(data.change_pct, 2, "%")}
        </span>
      ),
      as_of: data.as_of,
    },
    {
      label: "股息率 (TTM)",
      main: fmt(data.dividend_yield, 2, "%"),
      sub: (() => {
        const p = percentileLabel(dyPct, true);
        return (
          <div className="space-y-1.5">
            <span className={`inline-block px-2 py-0.5 text-xs rounded ${p.cls}`}>
              {VALUATION_WINDOWS.find((w) => w.key === dyWindow)?.label}分位 {p.text}
            </span>
            <WindowButtons
              window={dyWindow}
              onSelect={setDyWindow}
              available={data.dividend_yield_percentile}
            />
          </div>
        );
      })(),
    },
    {
      label: "市盈率 (TTM)",
      main: fmt(data.pe_ttm, 2),
      sub: (() => {
        const p = percentileLabel(pePct, false);
        return (
          <div className="space-y-1.5">
            <span className={`inline-block px-2 py-0.5 text-xs rounded ${p.cls}`}>
              {VALUATION_WINDOWS.find((w) => w.key === peWindow)?.label}分位 {p.text}
            </span>
            <WindowButtons
              window={peWindow}
              onSelect={setPeWindow}
              available={data.pe_percentile}
            />
          </div>
        );
      })(),
    },
    {
      label: "股息率 - 10Y国债",
      main: fmt(data.yield_spread_bps, 2, "%"),
      sub: (
        <span className="text-xs text-slate-500">
          利差 &gt; 2% 视为有吸引力
        </span>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm"
        >
          <div className="text-xs text-slate-500 mb-2">{c.label}</div>
          <div className="text-3xl font-semibold tracking-tight text-slate-900">
            {c.main}
          </div>
          <div className="mt-2 text-sm">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}
