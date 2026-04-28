"use client";

import { PortfolioSummary } from "@/lib/api";

function fmtCny(n: number, signed = false): string {
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}¥${n.toLocaleString("zh-CN", {
    maximumFractionDigits: 0,
  })}`;
}

function pnlClass(n: number): string {
  if (n > 0) return "text-rose-600";
  if (n < 0) return "text-emerald-600";
  return "text-slate-600";
}

export function SummaryBar({ data }: { data: PortfolioSummary }) {
  const cards = [
    {
      label: "总市值 (CNY)",
      main: fmtCny(data.total_market_value_cny),
      sub: `${data.n_positions} 个持仓`,
      cls: "text-slate-900",
    },
    {
      label: "总成本 (CNY)",
      main: fmtCny(data.total_cost_value_cny),
      sub: data.last_updated
        ? `最后更新 ${data.last_updated.slice(0, 10)}`
        : "—",
      cls: "text-slate-900",
    },
    {
      label: "浮动盈亏 (CNY)",
      main: fmtCny(data.total_unrealized_pnl_cny, true),
      sub:
        data.total_return_pct !== null
          ? `${data.total_return_pct > 0 ? "+" : ""}${data.total_return_pct.toFixed(2)}%`
          : "—",
      cls: pnlClass(data.total_unrealized_pnl_cny),
    },
    {
      label: "汇率快照",
      main: (
        <div className="text-base font-medium leading-relaxed">
          {data.fx_rates.map((fx) => (
            <div key={fx.pair} className="flex items-baseline gap-2">
              <span className="text-slate-500 text-xs">{fx.pair}</span>
              <span>{fx.rate.toFixed(4)}</span>
            </div>
          ))}
        </div>
      ),
      sub: data.fx_rates[0]?.as_of?.slice(0, 10) ?? "—",
      cls: "text-slate-900",
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
          <div
            className={`text-2xl font-semibold tracking-tight ${c.cls}`}
          >
            {c.main}
          </div>
          <div className="mt-2 text-xs text-slate-500">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}
