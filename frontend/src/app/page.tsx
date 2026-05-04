import Link from "next/link";

const ENTRIES = [
  {
    href: "/market",
    title: "金融市场看盘",
    description: "红利指数、港股科技、美股科技的估值、走势、信号与市场情绪。",
    meta: "指数估值 · 基准对比 · 科技股信号",
  },
  {
    href: "/portfolio",
    title: "持仓管理",
    description: "查看本地持仓快照、资产分布、盈亏表现、标签分组和导入同步状态。",
    meta: "持仓明细 · 资产配置 · 富途 / 截图导入",
  },
  {
    href: "/agent",
    title: "投资 Agent",
    description: "进入策略分析对话，沉淀分析文档，并按分类、标的和关键词检索历史结论。",
    meta: "策略对话 · 文档管理 · 结论摘要",
  },
];

export default function Home() {
  return (
    <main className="min-h-[calc(100vh-3rem)] bg-slate-50">
      <section className="max-w-7xl mx-auto px-6 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-slate-950">AlphaLens</h1>
          <p className="mt-2 text-sm text-slate-500">
            选择一个工作台开始看盘。
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {ENTRIES.map((entry) => (
            <Link
              key={entry.href}
              href={entry.href}
              className="group bg-white border border-slate-200 rounded-lg p-6 shadow-sm hover:border-slate-400 hover:shadow-md transition"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs text-slate-500">{entry.meta}</div>
                  <h2 className="mt-2 text-xl font-semibold text-slate-950">
                    {entry.title}
                  </h2>
                </div>
                <span className="mt-1 text-slate-400 group-hover:text-slate-900 transition">
                  -&gt;
                </span>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                {entry.description}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
