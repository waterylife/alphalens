"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher, TagsConfig } from "@/lib/api";

type TagField = "tag_l1" | "tag_l2";

function splitLines(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinLines(values: string[]) {
  return values.join("\n");
}

export function PortfolioTagConfigPanel() {
  const { mutate } = useSWRConfig();
  const [draft, setDraft] = useState<TagsConfig>({ tag_l1: [], tag_l2: [] });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const { error, isLoading } = useSWR<TagsConfig>(api.portfolioTags(), fetcher, {
    onSuccess: setDraft,
  });

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch(api.portfolioUpdateTags(), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) throw new Error(await res.text());
      const saved = (await res.json()) as TagsConfig;
      setDraft(saved);
      mutate(api.portfolioTags(), saved, { revalidate: false });
      mutate(api.portfolioTargets());
      mutate(api.portfolioHoldings());
      mutate(api.portfolioSummary());
      setMessage("标签元数据已保存，持仓明细和 Portfolio 目标配置会共用这套标签。");
    } catch (e) {
      setMessage(`保存失败：${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  function update(field: TagField, value: string) {
    setDraft((curr) => ({ ...curr, [field]: splitLines(value) }));
  }

  return (
    <section className="bg-white border border-slate-200 rounded-xl shadow-sm">
      <div className="px-4 py-4 border-b border-slate-100 flex flex-wrap items-start gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">持仓标签配置</h2>
          <p className="text-xs text-slate-500 mt-1">
            这里维护统一的一级/二级标签元数据，持仓明细和 Portfolio 目标配置都会使用这份词表。
          </p>
        </div>
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="ml-auto h-8 rounded-md bg-slate-900 px-3 text-xs text-white disabled:opacity-50"
        >
          {saving ? "保存中…" : "保存标签"}
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          标签加载失败：{String(error)}
        </div>
      )}
      {message && (
        <div className="mx-4 mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4">
        <TagEditor
          title="一级标签"
          description="每行一个一级标签，例如：现金、债券、权益、红利低波、价值成长。"
          value={joinLines(draft.tag_l1)}
          onChange={(value) => update("tag_l1", value)}
          loading={isLoading}
        />
        <TagEditor
          title="二级标签"
          description="每行一个二级标签，例如：沪深红利、港股科技、纯债-中国、现金-海外。"
          value={joinLines(draft.tag_l2)}
          onChange={(value) => update("tag_l2", value)}
          loading={isLoading}
        />
      </div>
    </section>
  );
}

function TagEditor({
  title,
  description,
  value,
  onChange,
  loading,
}: {
  title: string;
  description: string;
  value: string;
  onChange: (value: string) => void;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <span className="text-xs text-slate-400">{splitLines(value).length} 项</span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{description}</p>
      <textarea
        value={loading ? "加载中..." : value}
        disabled={loading}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
        className="mt-3 h-[420px] w-full resize-y rounded-md border border-slate-200 bg-white p-3 font-mono text-sm leading-6 text-slate-800 outline-none focus:border-slate-500 disabled:text-slate-400"
      />
    </div>
  );
}
