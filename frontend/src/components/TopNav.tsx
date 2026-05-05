"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "主页" },
  { href: "/market", label: "金融市场看板" },
  { href: "/portfolio", label: "持仓管理" },
  { href: "/agent", label: "投资 Agent" },
];

export function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="bg-white border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-6 flex items-center gap-1 h-12">
        <span className="font-semibold text-sm mr-6">AlphaLens</span>
        {TABS.map((t) => {
          const active = pathname === t.href;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`px-3 py-1.5 text-sm rounded-md transition ${
                active
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
