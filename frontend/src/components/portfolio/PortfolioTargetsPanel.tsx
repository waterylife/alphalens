"use client";

import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  api,
  fetcher,
  PortfolioTarget,
  PortfolioTargetActual,
  PortfolioTargetAnalysis,
  PortfolioTargetInput,
  TagsConfig,
} from "@/lib/api";

const EMPTY_ROW: PortfolioTargetInput = {
  category_l1: "权益",
  category_l2: "",
  target_weight_pct: 0,
  target_market_value_cny: null,
  role_positioning: "",
  expected_asset_return_pct: null,
  expected_total_return_pct: null,
  optimistic_asset_return_pct: null,
  optimistic_total_return_pct: null,
  pessimistic_asset_return_pct: null,
  pessimistic_total_return_pct: null,
  sort_order: 0,
};

function toInput(row: PortfolioTarget): PortfolioTargetInput {
  return {
    id: row.id,
    category_l1: row.category_l1,
    category_l2: row.category_l2,
    target_weight_pct: row.target_weight_pct,
    target_market_value_cny: row.target_market_value_cny,
    role_positioning: row.role_positioning,
    expected_asset_return_pct: row.expected_asset_return_pct,
    expected_total_return_pct: row.expected_total_return_pct,
    optimistic_asset_return_pct: row.optimistic_asset_return_pct,
    optimistic_total_return_pct: row.optimistic_total_return_pct,
    pessimistic_asset_return_pct: row.pessimistic_asset_return_pct,
    pessimistic_total_return_pct: row.pessimistic_total_return_pct,
    sort_order: row.sort_order,
  };
}

function fmtCny(n: number | null) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null, signed = false) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function numValue(v: number | null | undefined) {
  return v === null || v === undefined || Number.isNaN(v) ? "" : String(v);
}

function parseNum(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function sumNullable(values: (number | null | undefined)[]) {
  let hasValue = false;
  let total = 0;
  for (const value of values) {
    if (value === null || value === undefined || Number.isNaN(value)) continue;
    hasValue = true;
    total += value;
  }
  return hasValue ? total : null;
}

function gapClass(n: number) {
  if (n > 1) return "text-rose-600";
  if (n < -1) return "text-sky-600";
  return "text-slate-500";
}

export function PortfolioTargetsPanel() {
  const { mutate } = useSWRConfig();
  const { data: tagsCfg } = useSWR<TagsConfig>(api.portfolioTags(), fetcher);
  const { error, isLoading } = useSWR<PortfolioTarget[]>(
    api.portfolioTargets(),
    fetcher,
    {
      onSuccess: (next) => setRows(next.map(toInput)),
    }
  );
  const [rows, setRows] = useState<PortfolioTargetInput[]>([]);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<PortfolioTargetAnalysis | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const totalWeight = useMemo(
    () => rows.reduce((sum, row) => sum + (row.target_weight_pct || 0), 0),
    [rows]
  );
  const totals = useMemo(
    () => ({
      targetMarketValueCny: sumNullable(rows.map((row) => row.target_market_value_cny)),
      expectedTotalReturnPct: sumNullable(rows.map((row) => row.expected_total_return_pct)),
      optimisticTotalReturnPct: sumNullable(rows.map((row) => row.optimistic_total_return_pct)),
      pessimisticTotalReturnPct: sumNullable(rows.map((row) => row.pessimistic_total_return_pct)),
    }),
    [rows]
  );

  function updateRow(index: number, patch: Partial<PortfolioTargetInput>) {
    setRows((curr) =>
      curr.map((row, i) => (i === index ? { ...row, ...patch } : row))
    );
  }

  function addRow() {
    setRows((curr) => [
      ...curr,
      { ...EMPTY_ROW, sort_order: curr.length, category_l2: "新分类" },
    ]);
  }

  function removeRow(index: number) {
    setRows((curr) =>
      curr.filter((_, i) => i !== index).map((row, i) => ({ ...row, sort_order: i }))
    );
  }

  async function save(): Promise<boolean> {
    setSaving(true);
    setMessage(null);
    try {
      const payload = rows.map((row, index) => ({
        ...row,
        sort_order: index,
        role_positioning: row.role_positioning?.trim() || null,
      }));
      const res = await fetch(api.portfolioTargets(), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: payload }),
      });
      if (!res.ok) throw new Error(await res.text());
      const saved = (await res.json()) as PortfolioTarget[];
      setRows(saved.map(toInput));
      mutate(api.portfolioTargets(), saved, { revalidate: false });
      setMessage("目标配置已保存。");
      return true;
    } catch (e) {
      setMessage(`保存失败：${String(e)}`);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function analyze() {
    setAnalyzing(true);
    setMessage(null);
    try {
      const saved = await save();
      if (!saved) return;
      const res = await fetch(api.portfolioTargetsAnalyze(), { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      setAnalysis((await res.json()) as PortfolioTargetAnalysis);
    } catch (e) {
      setMessage(`分析失败：${String(e)}`);
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <section className="bg-white border border-slate-200 rounded-xl shadow-sm">
      <div className="px-4 py-4 border-b border-slate-100 flex flex-wrap items-start gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Portfolio 目标配置</h2>
          <p className="text-xs text-slate-500 mt-1">
            按价值投资框架维护目标仓位，保存后可调用 Gemini 对当前持仓做偏离分析。
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span
            className={`text-xs tabular-nums ${
              Math.abs(totalWeight - 100) <= 0.5 ? "text-slate-500" : "text-rose-600"
            }`}
          >
            目标合计 {totalWeight.toFixed(2)}%
          </span>
          <button
            type="button"
            onClick={addRow}
            className="h-8 rounded-md border border-slate-200 px-3 text-xs text-slate-700 hover:border-slate-400"
          >
            + 分类
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="h-8 rounded-md bg-slate-900 px-3 text-xs text-white disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存目标"}
          </button>
          <button
            type="button"
            onClick={analyze}
            disabled={analyzing || saving}
            className="h-8 rounded-md bg-blue-600 px-3 text-xs text-white disabled:opacity-50"
          >
            {analyzing ? "Gemini 分析中…" : "Gemini 分析"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          目标配置加载失败：{String(error)}
        </div>
      )}
      {message && (
        <div className="mx-4 mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {message}
        </div>
      )}

      <div className="overflow-x-auto px-4 py-4">
        <table className="min-w-[1560px] w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <Th>一级分类</Th>
              <Th>二级分类</Th>
              <Th right>Portfolio %</Th>
              <Th right>Market Cap</Th>
              <Th>角色定位</Th>
              <Th right>预期资产收益率</Th>
              <Th right>预期归总收益率</Th>
              <Th right>乐观资产收益率</Th>
              <Th right>乐观归总收益率</Th>
              <Th right>悲观资产收益率</Th>
              <Th right>悲观归总收益率</Th>
              <Th right>操作</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={12} className="px-3 py-10 text-center text-slate-400">
                  加载目标配置…
                </td>
              </tr>
            )}
            {rows.map((row, index) => (
              <tr key={`${row.id ?? "new"}-${index}`} className="border-t border-slate-100">
                <Td>
                  <TagInput
                    value={row.category_l1}
                    options={tagsCfg?.tag_l1 ?? []}
                    onChange={(v) => updateRow(index, { category_l1: v })}
                  />
                </Td>
                <Td>
                  <TagInput
                    value={row.category_l2}
                    options={tagsCfg?.tag_l2 ?? []}
                    onChange={(v) => updateRow(index, { category_l2: v })}
                  />
                </Td>
                <Td right>
                  <NumInput
                    value={row.target_weight_pct}
                    onChange={(v) => updateRow(index, { target_weight_pct: v ?? 0 })}
                  />
                </Td>
                <Td right>
                  <NumInput
                    value={row.target_market_value_cny}
                    onChange={(v) => updateRow(index, { target_market_value_cny: v })}
                  />
                </Td>
                <Td>
                  <TextInput
                    value={row.role_positioning ?? ""}
                    onChange={(v) => updateRow(index, { role_positioning: v })}
                    wide
                  />
                </Td>
                <PctCell row={row} index={index} field="expected_asset_return_pct" updateRow={updateRow} />
                <PctCell row={row} index={index} field="expected_total_return_pct" updateRow={updateRow} />
                <PctCell row={row} index={index} field="optimistic_asset_return_pct" updateRow={updateRow} />
                <PctCell row={row} index={index} field="optimistic_total_return_pct" updateRow={updateRow} />
                <PctCell row={row} index={index} field="pessimistic_asset_return_pct" updateRow={updateRow} />
                <PctCell row={row} index={index} field="pessimistic_total_return_pct" updateRow={updateRow} />
                <Td right>
                  <button
                    type="button"
                    onClick={() => removeRow(index)}
                    className="text-xs text-slate-400 hover:text-rose-600"
                  >
                    删除
                  </button>
                </Td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-slate-50 border-t border-slate-200 text-slate-900">
            <tr>
              <td className="px-3 py-3 font-semibold whitespace-nowrap">合计</td>
              <td className="px-3 py-3 text-slate-400">—</td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">
                {fmtPct(totalWeight)}
              </td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">
                {fmtCny(totals.targetMarketValueCny)}
              </td>
              <td className="px-3 py-3 text-slate-400">—</td>
              <td className="px-3 py-3 text-right text-slate-400">—</td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">
                {fmtPct(totals.expectedTotalReturnPct)}
              </td>
              <td className="px-3 py-3 text-right text-slate-400">—</td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">
                {fmtPct(totals.optimisticTotalReturnPct)}
              </td>
              <td className="px-3 py-3 text-right text-slate-400">—</td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">
                {fmtPct(totals.pessimisticTotalReturnPct)}
              </td>
              <td className="px-3 py-3 text-right text-slate-400">—</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {analysis && (
        <div className="border-t border-slate-100 px-4 py-4 grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Gemini 优化建议</h3>
            <div className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-50 border border-slate-200 p-4 text-sm leading-6 text-slate-700">
              {analysis.conclusion}
            </div>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">目标偏离</h3>
            <div className="mt-3 max-h-[360px] overflow-auto border border-slate-200 rounded-lg">
              <table className="w-full min-w-[680px] text-xs">
                <thead className="sticky top-0 bg-slate-50 text-slate-500">
                  <tr>
                    <Th>分类</Th>
                    <Th right>目标</Th>
                    <Th right>当前</Th>
                    <Th right>偏离</Th>
                    <Th right>当前市值</Th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.actuals.map((item) => (
                    <ActualRow key={item.target_id} item={item} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function PctCell({
  row,
  index,
  field,
  updateRow,
}: {
  row: PortfolioTargetInput;
  index: number;
  field: keyof Pick<
    PortfolioTargetInput,
    | "expected_asset_return_pct"
    | "expected_total_return_pct"
    | "optimistic_asset_return_pct"
    | "optimistic_total_return_pct"
    | "pessimistic_asset_return_pct"
    | "pessimistic_total_return_pct"
  >;
  updateRow: (index: number, patch: Partial<PortfolioTargetInput>) => void;
}) {
  return (
    <Td right>
      <NumInput value={row[field]} onChange={(v) => updateRow(index, { [field]: v })} />
    </Td>
  );
}

function ActualRow({ item }: { item: PortfolioTargetActual }) {
  return (
    <tr className="border-t border-slate-100">
      <td className="px-3 py-2 font-medium text-slate-700 whitespace-nowrap">
        {item.category_l2}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{fmtPct(item.target_weight_pct)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{fmtPct(item.actual_weight_pct)}</td>
      <td className={`px-3 py-2 text-right tabular-nums ${gapClass(item.gap_pct)}`}>
        {fmtPct(item.gap_pct, true)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{fmtCny(item.actual_market_value_cny)}</td>
    </tr>
  );
}

function TextInput({
  value,
  onChange,
  wide,
}: {
  value: string;
  onChange: (value: string) => void;
  wide?: boolean;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={`h-8 rounded-md border border-slate-200 bg-white px-2 text-sm outline-none focus:border-slate-500 ${
        wide ? "w-72" : "w-40"
      }`}
    />
  );
}

function TagInput({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const list = useMemo(() => {
    const set = new Set(options);
    if (value) set.add(value);
    return [...set].sort();
  }, [options, value]);

  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-8 w-44 rounded-md border border-slate-200 bg-white px-2 text-sm outline-none focus:border-slate-500"
    >
      {!value && <option value="">选择标签</option>}
      {list.map((item) => (
        <option key={item} value={item}>
          {item}
        </option>
      ))}
    </select>
  );
}

function NumInput({
  value,
  onChange,
}: {
  value: number | null | undefined;
  onChange: (value: number | null) => void;
}) {
  return (
    <input
      value={numValue(value)}
      onChange={(event) => onChange(parseNum(event.target.value))}
      inputMode="decimal"
      className="h-8 w-24 rounded-md border border-slate-200 bg-white px-2 text-right text-sm tabular-nums outline-none focus:border-slate-500"
    />
  );
}

function Th({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <th
      className={`px-3 py-2.5 text-xs font-medium whitespace-nowrap ${
        right ? "text-right" : "text-left"
      }`}
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
    <td className={`px-3 py-2 align-middle ${right ? "text-right" : "text-left"}`}>
      {children}
    </td>
  );
}
