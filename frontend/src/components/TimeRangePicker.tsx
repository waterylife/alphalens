"use client";

import { useState } from "react";

export type RangeKey =
  | "5d"
  | "1m"
  | "3m"
  | "6m"
  | "ytd"
  | "1y"
  | "2y"
  | "3y"
  | "5y"
  | "10y"
  | "custom";

const PRESETS: { key: RangeKey; label: string }[] = [
  { key: "5d", label: "近5日" },
  { key: "1m", label: "近1月" },
  { key: "3m", label: "近3月" },
  { key: "6m", label: "近6月" },
  { key: "ytd", label: "今年来" },
  { key: "1y", label: "近1年" },
  { key: "2y", label: "近2年" },
  { key: "3y", label: "近3年" },
  { key: "5y", label: "近5年" },
  { key: "10y", label: "近10年" },
];

export function rangeToDates(key: RangeKey): { start?: string; end?: string } {
  const today = new Date();
  const end = today.toISOString().substring(0, 10);
  const d = new Date(today);

  switch (key) {
    case "5d":
      d.setDate(d.getDate() - 7);
      break;
    case "1m":
      d.setMonth(d.getMonth() - 1);
      break;
    case "3m":
      d.setMonth(d.getMonth() - 3);
      break;
    case "6m":
      d.setMonth(d.getMonth() - 6);
      break;
    case "ytd":
      return { start: `${today.getFullYear()}-01-01`, end };
    case "1y":
      d.setFullYear(d.getFullYear() - 1);
      break;
    case "2y":
      d.setFullYear(d.getFullYear() - 2);
      break;
    case "3y":
      d.setFullYear(d.getFullYear() - 3);
      break;
    case "5y":
      d.setFullYear(d.getFullYear() - 5);
      break;
    case "10y":
      d.setFullYear(d.getFullYear() - 10);
      break;
    default:
      return {};
  }
  return { start: d.toISOString().substring(0, 10), end };
}

interface Props {
  value: RangeKey;
  customStart: string;
  customEnd: string;
  onChange: (key: RangeKey, start?: string, end?: string) => void;
}

export function TimeRangePicker({ value, customStart, customEnd, onChange }: Props) {
  const [start, setStart] = useState(customStart);
  const [end, setEnd] = useState(customEnd);

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      {PRESETS.map((p) => (
        <button
          key={p.key}
          onClick={() => onChange(p.key)}
          className={`px-2.5 py-1 rounded-md border transition ${
            value === p.key
              ? "bg-slate-900 text-white border-slate-900"
              : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
          }`}
        >
          {p.label}
        </button>
      ))}
      <span className="mx-2 h-4 border-l border-slate-200" />
      <span className="text-slate-500">自定义:</span>
      <input
        type="date"
        value={start}
        onChange={(e) => setStart(e.target.value)}
        className="px-2 py-1 rounded-md border border-slate-200 text-slate-700 text-xs"
      />
      <span className="text-slate-400">到</span>
      <input
        type="date"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
        className="px-2 py-1 rounded-md border border-slate-200 text-slate-700 text-xs"
      />
      <button
        onClick={() => onChange("custom", start, end)}
        className={`px-2.5 py-1 rounded-md border transition ${
          value === "custom"
            ? "bg-slate-900 text-white border-slate-900"
            : "bg-white text-slate-700 border-slate-200 hover:border-slate-400"
        }`}
      >
        查看
      </button>
    </div>
  );
}
