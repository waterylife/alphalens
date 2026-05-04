"use client";

import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  AgentConversationResult,
  api,
  fetcher,
  StrategyDocument,
  StrategyDocumentList,
} from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  running: "分析中",
  completed: "已完成",
  error: "失败",
  archived: "归档",
};

const STATUS_CLASS: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  running: "bg-amber-100 text-amber-700",
  completed: "bg-emerald-100 text-emerald-700",
  error: "bg-red-100 text-red-700",
  archived: "bg-slate-100 text-slate-500",
};

function fmtDate(value: string | null | undefined) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function docPreview(doc: StrategyDocument | null | undefined) {
  if (!doc) return "";
  return doc.summary || doc.conclusion || doc.thesis || doc.content;
}

function conclusionPreview(doc: StrategyDocument | null | undefined) {
  if (!doc) return "";
  return doc.conclusion || doc.summary || doc.content;
}

function cleanInline(text: string) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function isTableSeparator(line: string) {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line.trim());
}

function parseTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cleanInline(cell));
}

function MarkdownText({ text }: { text: string }) {
  const lines = text.split("\n");
  const nodes = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed === "---") {
      nodes.push(<div key={index} className="h-1" />);
      index += 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      nodes.push(
        <div key={index} className="pt-2 text-sm font-semibold text-slate-950">
          {cleanInline(heading[2])}
        </div>
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      const tableStart = index;
      const tableLines: string[] = [];
      while (index < lines.length) {
        const candidate = lines[index].trim();
        if (!(candidate.startsWith("|") && candidate.endsWith("|"))) break;
        tableLines.push(candidate);
        index += 1;
      }

      const header = parseTableRow(tableLines[0]);
      const bodyLines = isTableSeparator(tableLines[1])
        ? tableLines.slice(2)
        : tableLines.slice(1);
      const rows = bodyLines.filter((row) => !isTableSeparator(row)).map(parseTableRow);

      nodes.push(
        <div key={tableStart} className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="min-w-full table-auto border-collapse text-left text-xs leading-5">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {header.map((cell, cellIndex) => (
                  <th
                    key={`${tableStart}-h-${cellIndex}`}
                    className="whitespace-nowrap border-b border-slate-200 px-3 py-2 font-semibold"
                  >
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-800">
              {rows.map((row, rowIndex) => (
                <tr key={`${tableStart}-r-${rowIndex}`}>
                  {header.map((_, cellIndex) => (
                    <td
                      key={`${tableStart}-r-${rowIndex}-${cellIndex}`}
                      className="whitespace-nowrap px-3 py-2 align-top"
                    >
                      {row[cellIndex] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      nodes.push(
        <div key={index} className="flex gap-2">
          <span className="text-slate-300">•</span>
          <span>{cleanInline(trimmed.replace(/^[-*]\s+/, ""))}</span>
        </div>
      );
      index += 1;
      continue;
    }

    nodes.push(<p key={index}>{cleanInline(trimmed)}</p>);
    index += 1;
  }

  return (
    <div className="space-y-2 text-sm leading-7 text-slate-700">
      {nodes}
    </div>
  );
}

function DocumentCard({
  doc,
  active,
  onSelect,
}: {
  doc: StrategyDocument;
  active: boolean;
  onSelect: (doc: StrategyDocument) => void;
}) {
  return (
    <button
      onClick={() => onSelect(doc)}
      className={`w-full text-left rounded-lg border p-4 transition ${
        active
          ? "border-slate-900 bg-slate-50"
          : "border-slate-200 bg-white hover:border-slate-400"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900">{doc.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
            <span>{doc.category}</span>
            <span className="text-slate-300">/</span>
            <span className={`rounded px-1.5 py-0.5 ${STATUS_CLASS[doc.status] ?? STATUS_CLASS.draft}`}>
              {STATUS_LABEL[doc.status] ?? doc.status}
            </span>
            <span className="text-slate-300">/</span>
            <span>{fmtDate(doc.updated_at)}</span>
          </div>
        </div>
        {doc.symbols.length > 0 && (
          <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            {doc.symbols.slice(0, 2).join(", ")}
          </span>
        )}
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">
        {docPreview(doc) || "暂无摘要"}
      </p>
    </button>
  );
}

export default function AgentPage() {
  const { mutate } = useSWRConfig();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [message, setMessage] = useState("");
  const [symbolsText, setSymbolsText] = useState("");
  const [reply, setReply] = useState("");
  const [submittingProvider, setSubmittingProvider] = useState<"gemini" | "minimax" | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [selected, setSelected] = useState<StrategyDocument | null>(null);

  const { data: recent } = useSWR<StrategyDocument | null>(
    api.agentRecentDocument(),
    fetcher,
    { refreshInterval: 5000 }
  );
  const { data: categories } = useSWR<string[]>(api.agentCategories(), fetcher);
  const docsUrl = useMemo(() => api.agentDocuments(query, category), [query, category]);
  const { data: docs } = useSWR<StrategyDocumentList>(docsUrl, fetcher, {
    refreshInterval: (latest) =>
      latest?.items.some((doc) => doc.status === "running") ? 5000 : 0,
  });

  const activeDoc =
    (selected ? docs?.items.find((doc) => doc.id === selected.id) : null) ??
    selected ??
    docs?.items[0] ??
    recent ??
    null;
  const allCategories = ["全部", ...(categories ?? [])];

  const submit = async (event: { preventDefault: () => void }, provider: "gemini" | "minimax") => {
    event.preventDefault();
    if (!message.trim()) return;
    setSubmittingProvider(provider);
    setReply("");
    try {
      const symbols = symbolsText
        .split(/[,\s，、]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      const res = await fetch(api.agentChat(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, category: "个股投资决策", symbols, provider }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as AgentConversationResult;
      setReply(data.reply);
      setSelected(data.document);
      setMessage("");
      setSymbolsText("");
      await Promise.all([
        mutate(api.agentRecentDocument()),
        mutate(api.agentCategories()),
        mutate(docsUrl),
      ]);
    } finally {
      setSubmittingProvider(null);
    }
  };

  const deleteReport = async (doc: StrategyDocument) => {
    const confirmed = window.confirm(`确认删除这篇报告吗？\n\n${doc.title}`);
    if (!confirmed) return;
    setDeletingId(doc.id);
    setDeleteError("");
    try {
      const res = await fetch(api.agentDocument(doc.id), { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      if (selected?.id === doc.id) setSelected(null);
      await Promise.all([
        mutate(api.agentRecentDocument()),
        mutate(api.agentCategories()),
        mutate(docsUrl),
      ]);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="min-h-[calc(100vh-3rem)] bg-slate-50">
      <section className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">投资 Agent</h1>
            <p className="mt-2 text-sm text-slate-500">
              策略分析对话入口 · 文档沉淀 · 结论检索
            </p>
          </div>
          <div className="text-xs text-slate-400">
            文档库: 本地 SQLite · 数据仅供研究参考
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-5">
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4">
              <h2 className="text-base font-semibold text-slate-900">个股投资决策分析</h2>
              <p className="mt-1 text-xs text-slate-500">
                输入一只具体股票和你的问题，后端会先联网取数，再调用 Gemini 或 MiniMax + value-stock-decider 生成分析文档。
              </p>
            </div>

            <form onSubmit={(event) => submit(event, "gemini")} className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
                <label className="block">
                  <span className="text-xs text-slate-500">标的代码</span>
                  <input
                    value={symbolsText}
                    onChange={(e) => setSymbolsText(e.target.value)}
                    placeholder="AAPL, 00700, 011961"
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  />
                </label>
                <div className="flex items-end">
                  <span className="mb-0.5 rounded-md bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700">
                    个股投资决策
                  </span>
                </div>
              </div>

              <label className="block">
                <span className="text-xs text-slate-500">分析请求</span>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={8}
                  placeholder="例如：分析腾讯当前估值、增长质量、主要风险和未来 12 个月的买入区间。"
                  className="mt-1 w-full resize-none rounded-md border border-slate-200 px-3 py-3 text-sm leading-6 outline-none focus:border-slate-500"
                />
              </label>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-slate-400">
                  分析任务会异步运行；行情、估值、技术和宏观数据会先联网采集。
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="submit"
                    disabled={submittingProvider !== null || !message.trim()}
                    className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    {submittingProvider === "gemini" ? "Gemini 启动中…" : "调用 Gemini 分析"}
                  </button>
                  <button
                    type="button"
                    onClick={(event) => submit(event, "minimax")}
                    disabled={submittingProvider !== null || !message.trim()}
                    className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    {submittingProvider === "minimax" ? "MiniMax 启动中…" : "调用 MiniMax 分析"}
                  </button>
                </div>
              </div>
            </form>

            {reply && (
              <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                {reply}
              </div>
            )}
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">最近分析结论</h2>
                <p className="mt-1 text-xs text-slate-500">
                  展示最近一篇分析文档中的结论或摘要。
                </p>
              </div>
              {recent && (
                <span className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-500">
                  {fmtDate(recent.updated_at)}
                </span>
              )}
            </div>

            {recent ? (
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xl font-semibold text-slate-950">{recent.title}</h3>
                  <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                    {recent.category}
                  </span>
                </div>
                {recent.symbols.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {recent.symbols.map((symbol) => (
                      <span
                        key={symbol}
                        className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600"
                      >
                        {symbol}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-4">
                  <MarkdownText text={docPreview(recent) || "这篇文档还没有摘要。"} />
                </div>
              </div>
            ) : (
              <div className="flex h-56 items-center justify-center rounded-md border border-dashed border-slate-200 text-sm text-slate-400">
                暂无分析文档
              </div>
            )}
          </section>
        </div>

        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">策略文档库</h2>
                <p className="mt-1 text-xs text-slate-500">
                  支持按关键词、分类、标的和标签检索历史分析。
                </p>
              </div>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索标题、结论、标的、标签"
                className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-500 sm:w-80"
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {allCategories.map((item) => (
                <button
                  key={item}
                  onClick={() => setCategory(item)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    category === item
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr]">
            <div className="max-h-[680px] space-y-3 overflow-y-auto border-b border-slate-100 p-5 lg:border-b-0 lg:border-r">
              <div className="text-xs text-slate-400">
                共 {docs?.total ?? 0} 篇文档
              </div>
              {(docs?.items ?? []).map((doc) => (
                <DocumentCard
                  key={doc.id}
                  doc={doc}
                  active={activeDoc?.id === doc.id}
                  onSelect={setSelected}
                />
              ))}
              {docs?.items.length === 0 && (
                <div className="rounded-md border border-dashed border-slate-200 py-12 text-center text-sm text-slate-400">
                  没有匹配的文档
                </div>
              )}
            </div>

            <div className="min-h-[520px] p-5">
              {activeDoc ? (
                <article>
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-semibold text-slate-950">{activeDoc.title}</h3>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <span>{activeDoc.category}</span>
                        <span>{STATUS_LABEL[activeDoc.status] ?? activeDoc.status}</span>
                        <span>更新 {fmtDate(activeDoc.updated_at)}</span>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-1.5">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {activeDoc.tags.map((tag) => (
                          <span key={tag} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                            {tag}
                          </span>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => deleteReport(activeDoc)}
                        disabled={deletingId === activeDoc.id}
                        className="ml-2 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition hover:border-red-300 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {deletingId === activeDoc.id ? "删除中..." : "删除报告"}
                      </button>
                    </div>
                  </div>

                  {deleteError && (
                    <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      {deleteError}
                    </div>
                  )}

                  {activeDoc.symbols.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {activeDoc.symbols.map((symbol) => (
                        <span
                          key={symbol}
                          className="rounded bg-blue-50 px-2 py-0.5 font-mono text-xs text-blue-700"
                        >
                          {symbol}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-6 grid gap-4">
                    <section>
                      <h4 className="text-sm font-semibold text-slate-900">结论摘要</h4>
                      <div className="mt-2 rounded-md bg-slate-50 p-4">
                        <MarkdownText text={docPreview(activeDoc) || "暂无摘要"} />
                      </div>
                    </section>
                    {activeDoc.conclusion && (
                      <section>
                        <h4 className="text-sm font-semibold text-slate-900">投资决策</h4>
                        <div className="mt-2 rounded-md border border-slate-100 bg-white p-4">
                          <MarkdownText text={conclusionPreview(activeDoc)} />
                        </div>
                      </section>
                    )}
                    {activeDoc.thesis && (
                      <section>
                        <h4 className="text-sm font-semibold text-slate-900">分析输入</h4>
                        <div className="mt-2 text-slate-600">
                          <MarkdownText text={activeDoc.thesis} />
                        </div>
                      </section>
                    )}
                    {activeDoc.content && activeDoc.content !== activeDoc.thesis && (
                      <section>
                        <h4 className="text-sm font-semibold text-slate-900">正文</h4>
                        <div className="mt-2 text-slate-600">
                          <MarkdownText text={activeDoc.content} />
                        </div>
                      </section>
                    )}
                  </div>
                </article>
              ) : (
                <div className="flex h-full min-h-[420px] items-center justify-center text-sm text-slate-400">
                  选择一篇文档查看详情
                </div>
              )}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
