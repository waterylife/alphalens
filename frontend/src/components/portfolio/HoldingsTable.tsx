"use client";

import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher, Holding, TagsConfig } from "@/lib/api";

const ALL = "全部";
const NONE = "—";   // sentinel for "clear this tag" in selects
type SortKey = "market_value_cny" | "return_pct";
type SortDir = "desc" | "asc";

// Order of asset-class sections; rows with any other class fall into "其他"
const ASSET_SECTIONS = ["股票", "债券", "现金"] as const;

function fmtCny(n: number | null, signed = false) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}¥${n.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
}

function fmtNum(n: number | null, digits = 4) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 2,
  });
}

function fmtPct(n: number | null) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function pnlClass(n: number | null | undefined) {
  if (n === null || n === undefined) return "text-slate-500";
  if (n > 0) return "text-rose-600";
  if (n < 0) return "text-emerald-600";
  return "text-slate-600";
}

function uniq(values: (string | null)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => !!v))).sort();
}

export function HoldingsTable({ rows }: { rows: Holding[] }) {
  const { data: tagsCfg } = useSWR<TagsConfig>(api.portfolioTags(), fetcher);
  const { mutate } = useSWRConfig();

  const [market, setMarket] = useState(ALL);
  const [broker, setBroker] = useState(ALL);
  const [tagL1, setTagL1] = useState(ALL);
  const [sortKey, setSortKey] = useState<SortKey>("market_value_cny");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());

  const markets = useMemo(() => [ALL, ...uniq(rows.map((r) => r.market))], [rows]);
  const brokers = useMemo(() => [ALL, ...uniq(rows.map((r) => r.broker))], [rows]);
  const tagL1Filter = useMemo(
    () => [
      ALL,
      ...uniq([...(tagsCfg?.tag_l1 ?? []), ...rows.map((r) => r.tag_l1)]),
    ],
    [rows, tagsCfg]
  );

  const filtered = rows.filter(
    (r) =>
      (market === ALL || r.market === market) &&
      (broker === ALL || r.broker === broker) &&
      (tagL1 === ALL || r.tag_l1 === tagL1)
  );

  function toggleSort(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(nextKey);
      setSortDir("desc");
    }
  }

  // Group filtered rows by asset class in declared order; everything else
  // (e.g. 黄金) lands in 其他 so it never silently disappears.
  const sections = useMemo(() => {
    const sortRows = (items: Holding[]) =>
      [...items].sort((a, b) => {
        const av = a[sortKey] ?? Number.NEGATIVE_INFINITY;
        const bv = b[sortKey] ?? Number.NEGATIVE_INFINITY;
        const diff = av - bv;
        if (diff === 0) return b.market_value_cny - a.market_value_cny;
        return sortDir === "asc" ? diff : -diff;
      });

    const buckets = new Map<string, Holding[]>();
    for (const sec of ASSET_SECTIONS) buckets.set(sec, []);
    const other: Holding[] = [];
    for (const r of filtered) {
      const target = ASSET_SECTIONS.includes(
        r.asset_class as (typeof ASSET_SECTIONS)[number]
      )
        ? buckets.get(r.asset_class)!
        : other;
      target.push(r);
    }
    const list: { name: string; rows: Holding[] }[] = ASSET_SECTIONS.map(
      (n) => ({ name: n, rows: sortRows(buckets.get(n) || []) })
    );
    if (other.length) list.push({ name: "其他", rows: sortRows(other) });
    return list;
  }, [filtered, sortDir, sortKey]);

  const totalMv = filtered.reduce((s, r) => s + r.market_value_cny, 0);
  const totalCv = filtered.reduce((s, r) => s + r.cost_value_cny, 0);
  const totalPnl = filtered.reduce(
    (s, r) => s + (r.unrealized_pnl_cny ?? 0),
    0
  );

  async function patchTag(
    id: number,
    field: "tag_l1" | "tag_l2",
    value: string | null
  ) {
    setSavingIds((s) => new Set(s).add(id));
    mutate(
      api.portfolioHoldings(),
      (curr: Holding[] | undefined) =>
        curr?.map((r) => (r.id === id ? { ...r, [field]: value } : r)),
      { revalidate: false }
    );
    try {
      const res = await fetch(api.portfolioPatchHolding(id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value ?? "" }),
      });
      if (!res.ok) throw new Error(await res.text());
      mutate(api.portfolioHoldings());
      mutate(api.portfolioSummary());
    } catch (e) {
      console.error(`保存标签失败 (id=${id}, ${field}):`, e);
      mutate(api.portfolioHoldings());
    } finally {
      setSavingIds((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
    }
  }

  return (
    <div className="space-y-4">
      {/* Shared filter bar across all sections */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-wrap gap-2 items-center px-4 py-3 text-sm">
        <Filter label="市场" value={market} options={markets} onChange={setMarket} />
        <Filter label="平台" value={broker} options={brokers} onChange={setBroker} />
        <Filter label="标签" value={tagL1} options={tagL1Filter} onChange={setTagL1} />
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-500">排序</span>
          <SortButton
            active={sortKey === "market_value_cny"}
            dir={sortDir}
            onClick={() => toggleSort("market_value_cny")}
          >
            市值
          </SortButton>
          <SortButton
            active={sortKey === "return_pct"}
            dir={sortDir}
            onClick={() => toggleSort("return_pct")}
          >
            收益率
          </SortButton>
        </div>
        <div className="ml-auto text-xs text-slate-500">
          全部 {filtered.length} 行 · 市值 {fmtCny(totalMv)} · 浮盈{" "}
          <span className={pnlClass(totalPnl)}>{fmtCny(totalPnl, true)}</span>
          {totalCv > 0 && (
            <>
              {" · 收益率 "}
              <span className={pnlClass(totalPnl)}>
                {fmtPct((totalPnl / totalCv) * 100)}
              </span>
            </>
          )}
        </div>
      </div>

      {sections.map((sec) =>
        sec.rows.length === 0 ? null : (
          <Section
            key={sec.name}
            name={sec.name}
            rows={sec.rows}
            tagsCfg={tagsCfg}
            savingIds={savingIds}
            onPatchTag={patchTag}
          />
        )
      )}

      <div className="text-xs text-slate-400 px-1">
        标签元数据可在「持仓标签配置」页直接维护，持仓明细和 Portfolio 目标配置共用同一套一级/二级标签。
      </div>
    </div>
  );
}

// ---- Section card -----------------------------------------------------

function Section({
  name,
  rows,
  tagsCfg,
  savingIds,
  onPatchTag,
}: {
  name: string;
  rows: Holding[];
  tagsCfg: TagsConfig | undefined;
  savingIds: Set<number>;
  onPatchTag: (id: number, field: "tag_l1" | "tag_l2", v: string | null) => void;
}) {
  const totalMv = rows.reduce((s, r) => s + r.market_value_cny, 0);
  const totalCv = rows.reduce((s, r) => s + r.cost_value_cny, 0);
  const totalPnl = rows.reduce((s, r) => s + (r.unrealized_pnl_cny ?? 0), 0);
  const ret = totalCv > 0 ? (totalPnl / totalCv) * 100 : null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
      <div className="flex flex-wrap items-baseline gap-2 px-4 py-3 border-b border-slate-100">
        <h3 className="text-base font-semibold text-slate-900">{name}</h3>
        <span className="text-xs text-slate-500">{rows.length} 行</span>
        <div className="ml-auto text-sm flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span>
            <span className="text-slate-500 text-xs mr-1">市值</span>
            <span className="font-medium tabular-nums">{fmtCny(totalMv)}</span>
          </span>
          <span>
            <span className="text-slate-500 text-xs mr-1">浮盈</span>
            <span className={`font-medium tabular-nums ${pnlClass(totalPnl)}`}>
              {fmtCny(totalPnl, true)}
            </span>
          </span>
          {ret !== null && (
            <span>
              <span className="text-slate-500 text-xs mr-1">收益率</span>
              <span className={`font-medium tabular-nums ${pnlClass(totalPnl)}`}>
                {fmtPct(ret)}
              </span>
            </span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <Th>标的</Th>
              <Th>市场</Th>
              <Th>标签 (一级 / 二级)</Th>
              <Th right>币种</Th>
              <Th right>现价</Th>
              <Th right>成本价</Th>
              <Th right>数量</Th>
              <Th right>市值 (¥)</Th>
              <Th right>占比</Th>
              <Th right>浮盈 (¥)</Th>
              <Th right>收益率</Th>
              <Th>平台</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-900">
                  {r.name}
                  {r.code && (
                    <span className="text-slate-400 text-xs ml-1.5 font-mono">
                      {r.code}
                    </span>
                  )}
                  {r.broker === "东方财富" && r.market === "香港" && (
                    <span
                      className="ml-2 px-1.5 py-0.5 text-[10px] rounded bg-amber-100 text-amber-700 align-middle"
                      title="港股通持仓 · 人民币计价 · 不参与「刷新价格」批量行情更新,通过重新上传东方财富截图来更新"
                    >
                      港股通
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-600">{r.market}</td>
                <td className="px-3 py-2">
                  <TagSelect
                    value={r.tag_l1}
                    options={tagsCfg?.tag_l1 ?? []}
                    placeholder="一级标签"
                    saving={savingIds.has(r.id)}
                    onChange={(v) => onPatchTag(r.id, "tag_l1", v)}
                  />
                  <TagSelect
                    value={r.tag_l2}
                    options={tagsCfg?.tag_l2 ?? []}
                    placeholder="二级标签"
                    saving={savingIds.has(r.id)}
                    onChange={(v) => onPatchTag(r.id, "tag_l2", v)}
                  />
                </td>
                <td className="px-3 py-2 text-right text-slate-500 text-xs">
                  {r.currency}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {fmtNum(r.current_price)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {fmtNum(r.cost_price)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {fmtNum(r.quantity, 2)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">
                  {fmtCny(r.market_value_cny)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                  {(r.weight * 100).toFixed(2)}%
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${pnlClass(r.unrealized_pnl_cny)}`}
                >
                  {fmtCny(r.unrealized_pnl_cny, true)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${pnlClass(r.return_pct)}`}
                >
                  {fmtPct(r.return_pct)}
                </td>
                <td className="px-3 py-2 text-slate-600 text-xs">{r.broker}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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
      className={`px-3 py-2.5 text-xs font-medium ${right ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-slate-200 rounded-md px-2 py-1 text-xs bg-white hover:border-slate-400 transition"
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}

function SortButton({
  active,
  dir,
  onClick,
  children,
}: {
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-7 rounded-md border px-2 text-xs transition ${
        active
          ? "border-slate-900 bg-slate-900 text-white"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
      }`}
      title={active ? `当前按${children}${dir === "desc" ? "降序" : "升序"}` : undefined}
    >
      <span>{children}</span>
      {active && <span className="ml-1">{dir === "desc" ? "↓" : "↑"}</span>}
    </button>
  );
}

function TagSelect({
  value,
  options,
  placeholder,
  saving,
  onChange,
}: {
  value: string | null;
  options: string[];
  placeholder: string;
  saving: boolean;
  onChange: (v: string | null) => void;
}) {
  const opts = useMemo(() => {
    const set = new Set(options);
    if (value) set.add(value);
    return [...set].sort();
  }, [options, value]);

  return (
    <select
      value={value ?? NONE}
      disabled={saving}
      onChange={(e) => {
        const v = e.target.value;
        onChange(v === NONE ? null : v);
      }}
      title={placeholder}
      className={`block w-full px-1.5 py-0.5 my-0.5 text-xs border rounded bg-white transition ${
        value
          ? "border-slate-200 text-slate-700"
          : "border-slate-100 text-slate-400 italic"
      } ${saving ? "opacity-50" : "hover:border-slate-400"}`}
    >
      <option value={NONE}>{placeholder}</option>
      {opts.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
