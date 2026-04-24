"use client";

// Shared buy/hold/sell pill used by both US and HK dashboards.
// The underlying signal shape (US vs HK) differs only in `components`, which
// this component does not use — so a structural type is enough.

export interface StrategySignalLike {
  ticker?: string;
  action: string;
  score: number | null;
  triggers: string[];
  explanation: string | null;
}

const ACTION_META: Record<string, { label: string; emoji: string; cls: string }> = {
  buy:  { label: "买入", emoji: "📈", cls: "bg-green-600 text-white" },
  hold: { label: "持有", emoji: "↔",  cls: "bg-slate-500 text-white" },
  sell: { label: "卖出", emoji: "📉", cls: "bg-red-600 text-white" },
};

export function ActionPill({
  sig, size = "sm",
}: {
  sig?: StrategySignalLike;
  size?: "xs" | "sm";
}) {
  if (!sig) return <span className="text-slate-300 text-xs">—</span>;
  const meta = ACTION_META[sig.action] ?? ACTION_META.hold;
  const pad = size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
  const title = [
    sig.explanation ?? "",
    sig.triggers.length ? `规则: ${sig.triggers.slice(0, 6).join("; ")}` : "",
    sig.score != null ? `评分: ${sig.score}/100` : "",
  ].filter(Boolean).join("\n");
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full font-medium tabular-nums ${pad} ${meta.cls}`}
    >
      <span>{meta.emoji}</span>
      <span>{meta.label}</span>
      {sig.score != null && <span className="opacity-80">{sig.score.toFixed(0)}</span>}
    </span>
  );
}
