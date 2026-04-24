"use client";

// Matrix notes: action pill semantics + collapsible indicator glossary.
// Used below the US and HK stock matrices. UI is intentionally muted —
// these are reference notes, not primary signals.

type Market = "us" | "hk";

const ACTION_NOTE = [
  { k: "买入", score: "≥ 65", desc: "多维度利好叠加，胜率与赔率都好" },
  { k: "持有", score: "40 – 65", desc: "利好利空打架，方向不明，观望不急动" },
  { k: "卖出", score: "< 40", desc: "多维度利空叠加，风险收益比不划算" },
];

type IndicatorDef = { name: string; en?: string; desc: string };

const COMMON_INDICATORS: IndicatorDef[] = [
  { name: "P/E (TTM)", desc: "市盈率，过去 12 个月盈利的倍数。数值越低相对越便宜；负数表示亏损，通常不展示。" },
  { name: "P/B", desc: "市净率 = 股价 / 每股净资产。银行、周期股常用，< 1 表示破净。" },
  { name: "P/S (TTM)", desc: "市销率 = 市值 / 过去 12 个月营收。成长股盈利波动大时比 PE 更稳定。" },
  { name: "RSI14", desc: "14 日相对强弱指标，0-100。> 70 超买（短期可能回调），< 30 超卖（可能反弹），30-70 中性。" },
  { name: "距 MA200", desc: "当前价相对 200 日移动平均线的偏离百分比。正数 = 位于均线上方（多头趋势），大幅正偏离提示追高风险；小幅负偏离常是多头回调买点。" },
  { name: "52w 位置", desc: "当前价在过去 52 周的 [最低, 最高] 区间中的百分位。0 = 年内最低，100 = 年内最高。接近 100 风险提高，接近 0 可能存在机会但也要警惕价值陷阱。" },
  { name: "ADTV 20d", desc: "20 日平均日成交额（美元/港币百万）。衡量流动性：太低的个股买卖容易滑点，机构难以进出。" },
];

const US_INDICATORS: IndicatorDef[] = [
  { name: "Fwd PE", desc: "前瞻市盈率 = 股价 / 未来 12 个月预期 EPS。反映分析师一致预期下的估值。" },
  { name: "PEG", desc: "PEG = PE / 盈利增速。< 1 经典便宜（增速能消化估值），> 2 通常偏贵。" },
  { name: "ROE", desc: "Return on Equity，净资产收益率。> 15% 为优秀，> 25% 通常说明强护城河（或高杠杆）。" },
  { name: "毛利率", desc: "毛利润 / 营收。> 50% 常见于软件/品牌公司，< 20% 多为资本密集型行业。" },
  { name: "营收增长", desc: "同比营收增速。成长股核心指标；负增长通常要警惕。" },
  { name: "Beta", desc: "相对大盘波动度。1 = 同步大盘，> 1.5 波动放大（高风险高收益），< 0.7 防御性较强。" },
  { name: "距 ATH", desc: "距历史最高价的百分比（负数）。-10% 内 = 接近高点，-25% 内 = 合理回撤，< -40% = 深度回撤。" },
  { name: "做空占比", desc: "Short % of Float，流通盘中被借券做空的比例。> 10% 通常意味空头押注较重，可能出现轧空（short squeeze）。" },
];

const HK_INDICATORS: IndicatorDef[] = [
  { name: "主力净流入（今日/5日）", desc: "大单资金净买入额（港币百万）。正数 = 主力在买入，负数 = 主力在卖出。5 日值比单日更能反映趋势。" },
  { name: "量比", desc: "当日成交量 / 过去 5 日平均成交量。> 1 放量，> 2 异动，< 0.8 缩量；常与价格共同判断突破有效性。" },
  { name: "换手率", desc: "当日成交股数 / 流通股数。反映交易活跃度，港股通常 < 2% 偏冷，> 5% 偏热。" },
  { name: "价差 bps", desc: "买卖盘一档的价差（基点，1% = 100bps）。大蓝筹通常 < 10 bps，小票可能 > 30 bps，影响交易成本。" },
  { name: "盘口比", desc: "买 5 档量 / 卖 5 档量。> 1 买盘强于卖盘，< 1 相反；仅作为短期情绪参考。" },
];

function Section({ title, defs }: { title: string; defs: IndicatorDef[] }) {
  return (
    <div>
      <div className="text-[11px] font-semibold text-slate-500 mb-2">{title}</div>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
        {defs.map((d) => (
          <div key={d.name} className="text-[11px] leading-relaxed">
            <dt className="font-medium text-slate-700">{d.name}</dt>
            <dd className="text-slate-500">{d.desc}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function MatrixNotes({ market }: { market: Market }) {
  return (
    <div className="px-5 py-4 border-t border-slate-100 text-[11px] text-slate-400 space-y-3">
      {/* Action note — always visible */}
      <div>
        <span className="font-medium text-slate-500">动作说明：</span>
        <span className="text-slate-400">
          动作由打分规则决定（非 LLM），LLM 仅生成中文解释。
        </span>
        <ul className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
          {ACTION_NOTE.map((a) => (
            <li key={a.k} className="text-slate-500">
              <span className="font-medium text-slate-700">{a.k}</span>
              <span className="mx-1 text-slate-400">({a.score})</span>
              <span className="text-slate-400">{a.desc}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Indicator glossary — collapsed by default */}
      <details className="group">
        <summary className="cursor-pointer list-none select-none text-slate-500 hover:text-slate-700 flex items-center gap-1">
          <span className="inline-block w-3 transition-transform group-open:rotate-90">▸</span>
          <span className="font-medium">指标释义</span>
          <span className="text-slate-400">（展开查看 RSI、ADTV、52w、Beta、P/S 等解释）</span>
        </summary>
        <div className="mt-3 pl-4 space-y-4">
          <Section title="通用指标" defs={COMMON_INDICATORS} />
          {market === "us" && <Section title="美股专属" defs={US_INDICATORS} />}
          {market === "hk" && <Section title="港股专属" defs={HK_INDICATORS} />}
        </div>
      </details>
    </div>
  );
}
