"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher, HKMarketLiquidity, HKSouthbound } from "@/lib/api";

function Stat({
  label,
  value,
  suffix = "",
  sub,
}: {
  label: string;
  value: string | null;
  suffix?: string;
  sub?: string | null;
}) {
  return (
    <div className="flex flex-col gap-1 min-w-[110px]">
      <span className="text-[11px] text-slate-500">{label}</span>
      <span className="text-lg font-semibold tabular-nums text-slate-900">
        {value ?? <span className="text-slate-300">—</span>}
        {value && <span className="text-xs font-normal text-slate-500 ml-0.5">{suffix}</span>}
      </span>
      {sub && <span className="text-[10px] text-slate-400 tabular-nums">{sub}</span>}
    </div>
  );
}

function fmt(n: number | null | undefined, digits = 2): string | null {
  if (n == null) return null;
  return n.toFixed(digits);
}

function fmtSigned(n: number | null | undefined, digits = 1): string | null {
  if (n == null) return null;
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

export function HKMarketPanel() {
  const [open, setOpen] = useState(false);

  const { data: liq } = useSWR<HKMarketLiquidity>(
    open ? api.hkMarketLiquidity() : null,
    fetcher,
    { refreshInterval: 15 * 60_000 }
  );
  const { data: sb } = useSWR<HKSouthbound>(
    open ? api.hkSouthbound() : null,
    fetcher,
    { refreshInterval: 60 * 60_000 }
  );

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm border-l-4 border-l-violet-500">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-violet-500" />
          <h3 className="text-base font-semibold text-slate-900">
            市场流动性 · <span className="text-violet-700">宏观</span>
          </h3>
          <span className="text-xs text-slate-500 ml-2">
            VHSI · HIBOR · USD/HKD · 南向资金
          </span>
        </div>
        <span
          className={`text-slate-400 text-sm transition-transform ${
            open ? "rotate-180" : ""
          }`}
        >
          ▼
        </span>
      </button>

      {open && (
        <div className="px-5 py-4 border-t border-slate-100">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-5">
            <Stat
              label="恒生波指 VHSI"
              value={fmt(liq?.vhsi, 2)}
              sub={liq?.vhsi_change_pct != null ? `${fmtSigned(liq.vhsi_change_pct, 2)}%` : null}
            />
            <Stat label="USD/HKD" value={fmt(liq?.usd_hkd, 4)} />
            <Stat label="1M HIBOR" value={fmt(liq?.hibor_1m, 3)} suffix="%" />
            <Stat label="3M HIBOR" value={fmt(liq?.hibor_3m, 3)} suffix="%" />
            <Stat label="US 10Y" value={fmt(liq?.us_10y_yield, 2)} suffix="%" />
            <div className="hidden lg:block" />
            <Stat
              label="南向 MTD 净流入"
              value={fmt(sb?.net_inflow_mtd_hkd_bn, 1)}
              suffix=" B"
            />
            <Stat
              label="南向 YTD 净流入"
              value={fmt(sb?.net_inflow_ytd_hkd_bn, 1)}
              suffix=" B"
            />
          </div>
          <div className="mt-3 text-[11px] text-slate-400">
            数据源: Yahoo Finance (VHSI/USDHKD/US10Y) · akshare (HIBOR / 港股通)
          </div>
        </div>
      )}
    </div>
  );
}
