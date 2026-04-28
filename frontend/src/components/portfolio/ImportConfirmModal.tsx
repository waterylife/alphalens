"use client";

import { useState } from "react";
import { ImportRow, ScreenshotRow } from "@/lib/api";

interface BrokerProfile {
  label: string;          // 持仓页"交易平台"列要写什么
  defaultMarket: string;  // 默认市场
  defaultAssetClass: string;
}

const BROKER_PROFILES: Record<string, BrokerProfile> = {
  tiantian: {
    label: "天天基金",
    defaultMarket: "中国",
    defaultAssetClass: "债券",
  },
  eastmoney: {
    label: "东方财富",
    defaultMarket: "中国",
    defaultAssetClass: "股票",
  },
  ant: {
    label: "蚂蚁财富",
    defaultMarket: "中国",
    defaultAssetClass: "债券",
  },
};

const MARKETS = ["中国", "香港", "美国"];
const ASSET_CLASSES = ["股票", "债券", "现金", "黄金"];

interface DraftRow extends ImportRow {
  include: boolean;
  // unconverted native amounts; user edits these and we recompute *_cny on submit
  market_value_native: number;
  cost_value_native: number | null;
  unrealized_pnl_native: number | null;
}

interface Props {
  brokerKey: string;
  parsed: ScreenshotRow[];
  warnings: string[];
  fxRates: Record<string, number>;     // {HKDCNY: 0.87, USDCNY: 6.86}
  onClose: () => void;
  onConfirm: (broker: string, rows: ImportRow[]) => Promise<void>;
}

export function ImportConfirmModal({
  brokerKey,
  parsed,
  warnings,
  fxRates,
  onClose,
  onConfirm,
}: Props) {
  const profile = BROKER_PROFILES[brokerKey];
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [drafts, setDrafts] = useState<DraftRow[]>(() =>
    parsed.map((r) => seedDraft(r, profile))
  );

  function update(idx: number, patch: Partial<DraftRow>) {
    setDrafts((prev) =>
      prev.map((d, i) => (i === idx ? { ...d, ...patch } : d))
    );
  }

  async function handleConfirm() {
    setError(null);
    const selected = drafts.filter((d) => d.include);
    if (selected.length === 0) {
      setError("没有勾选任何行");
      return;
    }
    const rows: ImportRow[] = selected.map((d) => toImportRow(d, fxRates));

    // Sanity: any row missing market_value_cny? bail.
    const bad = rows.find((r) => !Number.isFinite(r.market_value_cny));
    if (bad) {
      setError(`市值无效: ${bad.name}`);
      return;
    }

    setSubmitting(true);
    try {
      await onConfirm(profile.label, rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[90vh] flex flex-col">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">
              确认导入 · {profile.label}（{drafts.length} 行候选）
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              核对识别结果后导入。系统会按 (平台·市场·代码) 匹配现有持仓做更新,匹配不到则新增。
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-slate-400 hover:text-slate-700 text-xl leading-none px-2"
          >
            ×
          </button>
        </div>

        {profile.label === "东方财富" && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs">
            提示：东方财富的港股资产视为<b>港股通</b>,统一采用人民币计价 (CNY)。
          </div>
        )}

        {warnings.length > 0 && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs">
            ⚠️ 解析提示：{warnings.join("； ")}
          </div>
        )}

        <div className="flex-1 overflow-auto px-5 py-3">
          <table className="w-full text-xs">
            <thead className="text-slate-500 sticky top-0 bg-white">
              <tr className="border-b border-slate-200">
                <Th>导入</Th>
                <Th>名称</Th>
                <Th>代码</Th>
                <Th>市场</Th>
                <Th>资产类型</Th>
                <Th>一级标签</Th>
                <Th>币种</Th>
                <Th right>数量</Th>
                <Th right>成本价</Th>
                <Th right>现价</Th>
                <Th right>市值（原币）</Th>
                <Th right>浮盈（原币）</Th>
                <Th right>收益率%</Th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1.5">
                    <input
                      type="checkbox"
                      checked={d.include}
                      onChange={(e) => update(i, { include: e.target.checked })}
                    />
                  </td>
                  <Td>
                    <Input
                      value={d.name}
                      onChange={(v) => update(i, { name: v })}
                    />
                  </Td>
                  <Td>
                    <Input
                      value={d.code ?? ""}
                      onChange={(v) =>
                        update(i, { code: v.trim() || null })
                      }
                      mono
                    />
                  </Td>
                  <Td>
                    <Select
                      value={d.market}
                      options={MARKETS}
                      onChange={(v) =>
                        update(i, {
                          market: v,
                          currency: defaultCurrencyForMarket(v),
                        })
                      }
                    />
                  </Td>
                  <Td>
                    <Select
                      value={d.asset_class}
                      options={ASSET_CLASSES}
                      onChange={(v) => update(i, { asset_class: v })}
                    />
                  </Td>
                  <Td>
                    <Input
                      value={d.tag_l1 ?? ""}
                      onChange={(v) =>
                        update(i, { tag_l1: v.trim() || null })
                      }
                    />
                  </Td>
                  <Td>
                    <Input
                      value={d.currency}
                      onChange={(v) => update(i, { currency: v.toUpperCase() })}
                      width={56}
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.quantity}
                      onChange={(v) => update(i, { quantity: v })}
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.cost_price}
                      onChange={(v) => update(i, { cost_price: v })}
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.current_price}
                      onChange={(v) => update(i, { current_price: v })}
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.market_value_native}
                      onChange={(v) =>
                        update(i, { market_value_native: v ?? 0 })
                      }
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.unrealized_pnl_native}
                      onChange={(v) =>
                        update(i, { unrealized_pnl_native: v })
                      }
                    />
                  </Td>
                  <Td right>
                    <NumberInput
                      value={d.return_pct}
                      onChange={(v) => update(i, { return_pct: v })}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-5 py-3 border-t border-slate-200 flex items-center gap-3">
          {error && (
            <span className="text-rose-600 text-xs">{error}</span>
          )}
          <span className="text-xs text-slate-500 ml-auto">
            将导入 {drafts.filter((d) => d.include).length} / {drafts.length} 行 · FX:
            {Object.entries(fxRates).map(([k, v]) => ` ${k}=${v.toFixed(4)}`)}
          </span>
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 text-sm rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="px-3 py-1.5 text-sm rounded-md bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400"
          >
            {submitting ? "导入中…" : "确认导入"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- helpers ---------------------------------------------------------

function defaultCurrencyForMarket(m: string): string {
  return m === "香港" ? "HKD" : m === "美国" ? "USD" : "CNY";
}

function inferMarketFromCode(code: string | null, fallback: string): string {
  // Code shape is more reliable than the broker hint: a 5-digit numeric is
  // a Hong Kong ticker no matter where the screenshot came from.
  if (!code) return fallback;
  const c = code.trim().toUpperCase();
  if (/^[A-Z][A-Z0-9]{0,5}$/.test(c)) return "美国";
  if (/^\d{4,5}$/.test(c)) return "香港";
  return fallback;
}

function seedDraft(r: ScreenshotRow, profile: BrokerProfile): DraftRow {
  const market = inferMarketFromCode(r.code, profile.defaultMarket);
  // 东方财富 = 港股通 + A股 + 基金 — all bought through a mainland broker
  // and settled in CNY, so override Gemini's currency guess.
  const currency =
    profile.label === "东方财富"
      ? "CNY"
      : r.currency || defaultCurrencyForMarket(market);
  return {
    include: true,
    name: r.name,
    code: r.code,
    market,
    asset_class: profile.defaultAssetClass,
    tag_l1: null,
    tag_l2: null,
    currency,
    quantity: r.quantity,
    cost_price: r.cost_price,
    current_price: r.current_price,
    market_value_cny: r.market_value ?? 0,    // overridden on submit
    cost_value_cny: r.cost_value,
    unrealized_pnl_cny: r.unrealized_pnl,
    return_pct: r.return_pct,
    market_value_native: r.market_value ?? 0,
    cost_value_native: r.cost_value,
    unrealized_pnl_native: r.unrealized_pnl,
  };
}

function toImportRow(d: DraftRow, fx: Record<string, number>): ImportRow {
  const rate =
    d.currency === "CNY" ? 1 : fx[d.currency + "CNY"] ?? 1;
  const mv = (d.market_value_native ?? 0) * rate;
  const cv =
    d.cost_value_native != null ? d.cost_value_native * rate : null;
  const pnl =
    d.unrealized_pnl_native != null ? d.unrealized_pnl_native * rate : null;

  return {
    market: d.market,
    asset_class: d.asset_class,
    tag_l1: d.tag_l1,
    tag_l2: d.tag_l2,
    name: d.name,
    code: d.code,
    currency: d.currency,
    quantity: d.quantity,
    cost_price: d.cost_price,
    current_price: d.current_price,
    market_value_cny: round2(mv),
    cost_value_cny: cv != null ? round2(cv) : null,
    unrealized_pnl_cny: pnl != null ? round2(pnl) : null,
    return_pct: d.return_pct,
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

// ---- tiny inputs -----------------------------------------------------

function Th({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <th
      className={`px-2 py-2 font-medium ${right ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <td className={`px-2 py-1 ${right ? "text-right" : "text-left"}`}>
      {children}
    </td>
  );
}

function Input({
  value,
  onChange,
  mono,
  width,
}: {
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
  width?: number;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={width ? { width } : undefined}
      className={`w-full px-1.5 py-0.5 text-xs border border-slate-200 rounded ${
        mono ? "font-mono" : ""
      } focus:border-slate-400 focus:outline-none`}
    />
  );
}

function NumberInput({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <input
      type="text"
      inputMode="decimal"
      value={value ?? ""}
      onChange={(e) => {
        const v = e.target.value.trim();
        if (!v) return onChange(null);
        const n = Number(v.replace(/,/g, ""));
        onChange(Number.isFinite(n) ? n : null);
      }}
      className="w-24 px-1.5 py-0.5 text-xs border border-slate-200 rounded text-right tabular-nums focus:border-slate-400 focus:outline-none"
    />
  );
}

function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-1 py-0.5 text-xs border border-slate-200 rounded bg-white focus:border-slate-400 focus:outline-none"
    >
      {options.map((o) => (
        <option key={o}>{o}</option>
      ))}
    </select>
  );
}
