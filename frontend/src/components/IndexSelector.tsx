"use client";

import { IndexMeta } from "@/lib/api";

interface Props {
  indices: IndexMeta[];
  selected: string;
  onSelect: (code: string) => void;
}

export function IndexSelector({ indices, selected, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {indices.map((idx) => {
        const active = idx.code === selected;
        return (
          <button
            key={idx.code}
            onClick={() => onSelect(idx.code)}
            className={`px-4 py-2 rounded-lg border text-sm font-medium transition ${
              active
                ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
            }`}
          >
            <span className="font-semibold">{idx.name}</span>
            <span className="ml-1.5 text-xs opacity-70">{idx.code}</span>
          </button>
        );
      })}
    </div>
  );
}
