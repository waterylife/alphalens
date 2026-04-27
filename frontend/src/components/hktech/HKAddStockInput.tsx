"use client";

import { useState, useEffect, useRef } from "react";
import { api, fetcher, HKStockSearchResult } from "@/lib/api";

interface Props {
  existingTickers: string[];
  onAdd: (ticker: string, name: string) => void;
}

export function HKAddStockInput({ existingTickers, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HKStockSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
        setResults([]);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const search = (q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await fetcher<HKStockSearchResult[]>(api.hkSearch(q));
        setResults(data.filter((r) => !existingTickers.includes(r.ticker)));
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  };

  const handleSelect = (r: HKStockSearchResult) => {
    onAdd(r.ticker, r.name);
    setOpen(false);
    setQuery("");
    setResults([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim()) {
      const exact = results.find(
        (r) => r.ticker === query.trim().padStart(5, "0")
      );
      if (exact) handleSelect(exact);
      else if (results[0]) handleSelect(results[0]);
    }
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      setResults([]);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-slate-300 text-xs text-slate-500 hover:border-slate-400 hover:text-slate-700 transition-colors"
      >
        <span className="text-base leading-none">+</span>
        添加股票
      </button>
    );
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-400 bg-white shadow-sm w-64">
        <input
          autoFocus
          type="text"
          placeholder="输入代码或名称，如 0700"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            search(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          className="flex-1 text-xs outline-none placeholder:text-slate-400"
        />
        {loading && (
          <span className="text-slate-300 text-xs animate-pulse">…</span>
        )}
        <button
          onClick={() => {
            setOpen(false);
            setQuery("");
            setResults([]);
          }}
          className="text-slate-400 hover:text-slate-600 text-sm leading-none"
        >
          ✕
        </button>
      </div>

      {results.length > 0 && (
        <ul className="absolute z-20 top-full mt-1 left-0 w-64 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden">
          {results.map((r) => (
            <li key={r.ticker}>
              <button
                onClick={() => handleSelect(r)}
                className="w-full text-left px-3 py-2 text-xs hover:bg-slate-50 flex items-center gap-2"
              >
                <span className="font-mono text-slate-500 w-12 shrink-0">
                  {r.ticker}
                </span>
                <span className="text-slate-800 truncate">{r.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {query.trim() && results.length === 0 && !loading && (
        <div className="absolute z-20 top-full mt-1 left-0 w-64 bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs text-slate-400">
          未找到匹配结果
        </div>
      )}
    </div>
  );
}
