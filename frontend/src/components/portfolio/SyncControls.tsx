"use client";

import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  api,
  fetcher,
  ImportResult,
  ImportRow,
  PortfolioSummary,
  RefreshPricesResult,
  ScreenshotParseResult,
  SyncResult,
  SyncRun,
} from "@/lib/api";
import { ImportConfirmModal } from "./ImportConfirmModal";

function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

interface ModalState {
  brokerKey: string;
  parsed: ScreenshotParseResult;
}

export function SyncControls() {
  const { mutate } = useSWRConfig();
  const { data: runs } = useSWR<SyncRun[]>(
    api.portfolioSyncRuns(),
    fetcher,
    { refreshInterval: 0 }
  );
  const { data: summary } = useSWR<PortfolioSummary>(
    api.portfolioSummary(),
    fetcher
  );
  const lastFutu = runs?.find((r) => r.source === "futu");

  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ tone: "ok" | "err"; text: string } | null>(
    null
  );
  const [modal, setModal] = useState<ModalState | null>(null);
  const [tiantianScript, setTiantianScript] = useState("");

  // Screenshot upload input, triggered programmatically.
  const eastmoneyRef = useRef<HTMLInputElement>(null);

  async function readError(res: Response): Promise<string> {
    // Backend returns JSON {detail}; Next.js proxy 5xx returns plain text
    // ("Internal Server Error", "socket hang up", ...). Read once as text
    // and try JSON, fall back to text so the toast surfaces the real cause.
    const text = await res.text();
    try {
      const obj = JSON.parse(text);
      return obj.detail || text;
    } catch {
      return text || `HTTP ${res.status}`;
    }
  }

  async function runRefreshPrices() {
    setBusy("refresh");
    setToast(null);
    try {
      const res = await fetch(api.portfolioRefreshPrices(), { method: "POST" });
      if (!res.ok) throw new Error(await readError(res));
      const data: RefreshPricesResult = await res.json();
      let txt = `刷新价格成功：更新 ${data.n_updated} 行`;
      if (data.n_no_quote > 0) {
        const ex = data.skipped_examples.length
          ? `（如 ${data.skipped_examples.slice(0, 3).join("、")}）`
          : "";
        txt += ` · 未取到行情 ${data.n_no_quote} 行${ex}`;
      }
      if (data.n_skipped > 0) txt += ` · 跳过 ${data.n_skipped} 行（缺数量/汇率）`;
      setToast({ tone: "ok", text: txt });
      mutate(api.portfolioHoldings());
      mutate(api.portfolioSummary());
      mutate(api.portfolioSyncRuns());
    } catch (e) {
      setToast({ tone: "err", text: `刷新失败：${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  }

  async function runFutuSync() {
    setBusy("futu");
    setToast(null);
    try {
      const res = await fetch(api.portfolioSyncFutu(), { method: "POST" });
      if (!res.ok) throw new Error(await readError(res));
      const data: SyncResult = await res.json();
      setToast({
        tone: "ok",
        text: `富途同步成功：新增 ${data.n_inserted} · 更新 ${data.n_updated} · USDCNY ${data.fx_rates.USDCNY?.toFixed(4)} HKDCNY ${data.fx_rates.HKDCNY?.toFixed(4)}`,
      });
      mutate(api.portfolioHoldings());
      mutate(api.portfolioSummary());
      mutate(api.portfolioSyncRuns());
    } catch (e) {
      setToast({ tone: "err", text: `同步失败：${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  }

  async function uploadScreenshot(brokerKey: string, file: File) {
    setBusy(`screenshot:${brokerKey}`);
    setToast(null);
    try {
      const blob = await downsizeForUpload(file);
      const fd = new FormData();
      fd.append("image", blob, file.name.replace(/\.\w+$/, ".jpg"));
      fd.append("broker", brokerKey);
      const res = await fetch(api.portfolioScreenshotParse(), {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await readError(res));
      const parsed: ScreenshotParseResult = await res.json();
      if (parsed.rows.length === 0) {
        setToast({
          tone: "err",
          text: `识别 0 行${parsed.warnings.length ? ": " + parsed.warnings.join("; ") : ""}`,
        });
        return;
      }
      setModal({ brokerKey, parsed });
    } catch (e) {
      setToast({ tone: "err", text: `识别失败：${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  }

  async function confirmImport(broker: string, rows: ImportRow[]) {
    const res = await fetch(api.portfolioImportRows(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ broker, rows }),
    });
    if (!res.ok) throw new Error(await readError(res));
    const data: ImportResult = await res.json();
    setToast({
      tone: "ok",
      text: `${broker}导入成功：新增 ${data.n_inserted} · 更新 ${data.n_updated}`,
    });
    setModal(null);
    mutate(api.portfolioHoldings());
    mutate(api.portfolioSummary());
    mutate(api.portfolioSyncRuns());
  }

  async function generateTiantianScript() {
    setBusy("tiantian-browser");
    setToast(null);
    try {
      const res = await fetch(api.portfolioTiantianBrowserToken(), { method: "POST" });
      if (!res.ok) throw new Error(await readError(res));
      const data: { token: string; expires_in_seconds: number } = await res.json();
      setTiantianScript(buildTiantianReadOnlyCollector(data.token));
      setToast({
        tone: "ok",
        text: `已生成只读采集脚本，${Math.floor(data.expires_in_seconds / 60)} 分钟内有效`,
      });
    } catch (e) {
      setToast({ tone: "err", text: `生成失败：${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  }

  async function copyTiantianScript() {
    if (!tiantianScript) return;
    try {
      await navigator.clipboard.writeText(tiantianScript);
      setToast({ tone: "ok", text: "脚本已复制。请在天天基金持仓页的 Console 中运行。" });
    } catch {
      setToast({ tone: "err", text: "复制失败，请手动选中脚本复制。" });
    }
  }

  function fxRates(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const f of summary?.fx_rates ?? []) out[f.pair] = f.rate;
    return out;
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={runRefreshPrices}
          disabled={!!busy}
          className="px-3 py-1.5 text-sm rounded-md bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition"
          title="按代码批量从 sina/eastmoney 拉最新价,重算市值/浮盈/收益率"
        >
          {busy === "refresh" ? "刷新中…" : "刷新价格"}
        </button>
        <button
          onClick={runFutuSync}
          disabled={!!busy}
          className="px-3 py-1.5 text-sm rounded-md border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed transition"
        >
          {busy === "futu" ? "同步中…" : "同步富途"}
        </button>

        <UploadButton
          label={busy === "screenshot:eastmoney" ? "识别中…" : "上传东方财富截图"}
          disabled={!!busy}
          inputRef={eastmoneyRef}
          onFile={(f) => uploadScreenshot("eastmoney", f)}
        />
        <button
          onClick={generateTiantianScript}
          disabled={!!busy}
          className="px-3 py-1.5 text-sm rounded-md border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed transition"
          title="生成只读脚本：在天天基金持仓页读取基金代码/名称/份额/摊薄单价并导入本地"
        >
          {busy === "tiantian-browser" ? "生成中…" : "天天基金页面采集"}
        </button>

        <div className="ml-auto text-xs text-slate-500">
          {lastFutu ? (
            <span>
              上次富途同步：{fmtTime(lastFutu.finished_at)} ·{" "}
              <span
                className={
                  lastFutu.status === "ok"
                    ? "text-emerald-600"
                    : "text-rose-600"
                }
              >
                {lastFutu.status}
              </span>
              {lastFutu.n_rows != null && ` · ${lastFutu.n_rows} 行`}
            </span>
          ) : (
            <span>尚未同步过富途</span>
          )}
        </div>
      </div>

      {toast && (
        <div
          className={`mt-3 px-3 py-2 rounded-md text-xs ${
            toast.tone === "ok"
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
              : "bg-rose-50 text-rose-700 border border-rose-200"
          }`}
        >
          {toast.text}
        </div>
      )}

      {runs && runs.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-700">
            同步历史 ({runs.length})
          </summary>
          <table className="mt-2 w-full text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left py-1">来源</th>
                <th className="text-left py-1">完成时间</th>
                <th className="text-right py-1">行数</th>
                <th className="text-left py-1 pl-3">状态</th>
                <th className="text-left py-1 pl-3">错误</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="py-1.5">{r.source}</td>
                  <td className="py-1.5 text-slate-500 tabular-nums">
                    {fmtTime(r.finished_at)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">
                    {r.n_rows ?? "—"}
                  </td>
                  <td className="py-1.5 pl-3">
                    <span
                      className={
                        r.status === "ok"
                          ? "text-emerald-600"
                          : r.status === "running"
                          ? "text-amber-600"
                          : "text-rose-600"
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="py-1.5 pl-3 text-rose-600 truncate max-w-xs">
                    {r.error_msg ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {tiantianScript && (
        <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3" open>
          <summary className="text-xs font-medium text-slate-700 cursor-pointer">
            天天基金只读采集脚本
          </summary>
          <div className="mt-3 space-y-2">
            <p className="text-xs leading-5 text-slate-500">
              在已登录的
              <code className="mx-1 px-1 py-0.5 bg-white border border-slate-200 rounded">
                trade.1234567.com.cn/MyAssets/hold
              </code>
              页面运行。脚本只读取基金代码、名称、持有份额和摊薄单价；不会点击交易按钮或提交天天基金表单。
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={copyTiantianScript}
                className="px-3 py-1.5 text-xs rounded-md bg-slate-900 text-white hover:bg-slate-700 transition"
              >
                复制脚本
              </button>
              <span className="text-xs text-slate-400">
                导入目标：本机 AlphaLens SQLite
              </span>
            </div>
            <textarea
              readOnly
              value={tiantianScript}
              className="w-full h-40 p-2 text-[11px] leading-4 font-mono rounded-md border border-slate-200 bg-white text-slate-700"
            />
          </div>
        </details>
      )}

      {modal && (
        <ImportConfirmModal
          brokerKey={modal.brokerKey}
          parsed={modal.parsed.rows}
          warnings={modal.parsed.warnings}
          fxRates={fxRates()}
          onClose={() => setModal(null)}
          onConfirm={confirmImport}
        />
      )}
    </div>
  );
}

function buildTiantianReadOnlyCollector(token: string): string {
  return `(() => {
  "use strict";
  const TOKEN = ${JSON.stringify(token)};
  const API = "http://127.0.0.1:8000/api/portfolio/tiantian-browser-import";
  const DETAIL = "https://trade.1234567.com.cn/myassets/single?iv=false&fc=";

  const normalizeText = (s) => String(s || "").replace(/\\s+/g, " ").trim();
  const toNumber = (s) => {
    const cleaned = String(s || "").replace(/,/g, "").replace(/[^0-9.\\-]/g, "");
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : null;
  };
  const fundCodeFromUrl = (href) => {
    try {
      const u = new URL(href, location.href);
      return (u.searchParams.get("fc") || u.searchParams.get("fundcode") || "").match(/\\d{6}/)?.[0] || null;
    } catch {
      return String(href || "").match(/(?:fc|fundcode)=([0-9]{6})/)?.[1] || null;
    }
  };
  const cleanName = (text, code) => {
    const cleaned = normalizeText(text)
      .replace(code, "")
      .replace(/明细|详情|查看|持仓|交易|买入|卖出|赎回|转换|预约/g, "")
      .replace(/[()（）【】\\[\\]]/g, " ")
      .trim();
    return cleaned.replace(/\\s+/g, " ");
  };
  const nameFromText = (text, code) => {
    const src = normalizeText(text);
    const aroundCode = src.match(new RegExp("([\\\\u4e00-\\\\u9fa5A-Za-z0-9·（）() -]{2,50})\\\\s*" + code));
    if (aroundCode) {
      const name = cleanName(aroundCode[1], code);
      if (name && !/份额|金额|收益|净值|到期/.test(name)) return name;
    }
    const parts = src.split(code);
    const candidates = [parts[0], parts[1] || ""].map((part) => cleanName(part.slice(-60), code));
    return candidates.find((name) => name && name !== "明细" && !/份额|金额|收益|净值|到期/.test(name)) || "";
  };
  const findFunds = () => {
    const funds = new Map();
    document.querySelectorAll("a[href*='single'][href*='fc='], a[href*='fundcode=']").forEach((a) => {
      const code = fundCodeFromUrl(a.getAttribute("href"));
      if (!code) return;
      let el = a;
      let rowText = a.textContent || "";
      for (let i = 0; i < 8 && el; i += 1) {
        const text = normalizeText(el.innerText || el.textContent || "");
        if (text.includes(code) && text.length > rowText.length && text.length < 1000) rowText = text;
        el = el.parentElement;
      }
      const name = nameFromText(rowText, code) || cleanName(a.textContent, code);
      funds.set(code, { code, name: name || code });
    });
    if (funds.size === 0) {
      const text = document.body?.innerText || "";
      for (const m of text.matchAll(/([^\\n\\r]{0,40}?)(\\d{6})([^\\n\\r]{0,40})/g)) {
        const code = m[2];
        const name = cleanName((m[1] + " " + m[3]).slice(0, 80), code);
        if (name) funds.set(code, { code, name });
      }
    }
    return [...funds.values()];
  };
  const valueAfterLabels = (text, labels) => {
    for (const label of labels) {
      const escaped = label.replace(/[.*+?^$|()[\\]{}\\\\]/g, "\\\\$&").replace(/\\s+/g, "\\\\s*");
      const re = new RegExp(escaped + "\\\\s*[:：]?\\\\s*[^0-9\\\\-]{0,24}([0-9][0-9,]*\\\\.?[0-9]*)");
      const m = text.match(re);
      if (m) {
        const n = toNumber(m[1]);
        if (n != null) return n;
      }
    }
    return null;
  };
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const readRenderedDetailText = async (code) => {
    const iframe = document.createElement("iframe");
    iframe.src = DETAIL + encodeURIComponent(code);
    iframe.setAttribute("aria-hidden", "true");
    iframe.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:1200px;height:900px;opacity:0;pointer-events:none;";
    document.body.appendChild(iframe);
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(code + " 详情页加载超时")), 12000);
        iframe.onload = () => {
          clearTimeout(timer);
          resolve();
        };
      });
      for (let i = 0; i < 40; i += 1) {
        const text = normalizeText(iframe.contentDocument?.body?.innerText || "");
        if (/摊薄|成本/.test(text) && /份额|份数|数量/.test(text) && /[0-9]/.test(text)) return text;
        await sleep(250);
      }
      return normalizeText(iframe.contentDocument?.body?.innerText || "");
    } finally {
      iframe.remove();
    }
  };
  const parseDetail = async (fund) => {
    const text = await readRenderedDetailText(fund.code);
    const quantity = valueAfterLabels(text, ["持有份额", "可用份额", "持有份数", "可用份数", "持仓份额", "基金份额", "持有数量", "当前份额", "数量"]);
    const costPrice = valueAfterLabels(text, ["摊薄单价", "摊薄成本", "成本单价", "持仓成本价", "持仓单价", "成本价"]);
    return { name: fund.name, code: fund.code, quantity, cost_price: costPrice };
  };
  (async () => {
    if (location.hostname !== "trade.1234567.com.cn") {
      throw new Error("请在天天基金 trade.1234567.com.cn 的持仓页运行。");
    }
    const funds = findFunds();
    if (!funds.length) throw new Error("未在当前页面找到基金代码。");
    console.log("[AlphaLens] 发现基金", funds);
    const rows = [];
    for (const fund of funds) {
      const row = await parseDetail(fund);
      if (row.quantity != null && row.cost_price != null) rows.push(row);
      else console.warn("[AlphaLens] 跳过，缺少份额或摊薄单价", row);
    }
    if (!rows.length) throw new Error("详情页未解析到可导入行。");
    const importRes = await fetch(API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-AlphaLens-Import-Token": TOKEN
      },
      body: JSON.stringify({ rows })
    });
    const body = await importRes.text();
    if (!importRes.ok) throw new Error(body || ("导入失败 HTTP " + importRes.status));
    console.log("[AlphaLens] 导入完成", JSON.parse(body));
    alert("AlphaLens 导入完成：" + rows.length + " 行。请回到持仓页刷新。");
  })().catch((err) => {
    console.error("[AlphaLens] 天天基金只读采集失败", err);
    alert("AlphaLens 采集失败：" + err.message);
  });
})();`;
}

/**
 * Resize a phone screenshot before upload. Phone shots are typically
 * 1170×2532 RGBA PNG (~5–8 MB) — way more pixels than the OCR needs and
 * big enough to trip the Next.js dev rewrite proxy. We cap the long side
 * at 1600 px and re-encode as JPEG q=0.85, which usually drops to <500 KB
 * with no measurable loss in OCR accuracy.
 */
async function downsizeForUpload(
  file: File,
  maxLongSide = 1600,
  quality = 0.85
): Promise<Blob> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("无法读取图片"));
      i.src = url;
    });

    const long = Math.max(img.width, img.height);
    const scale = long > maxLongSide ? maxLongSide / long : 1;
    const w = Math.round(img.width * scale);
    const h = Math.round(img.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("无法初始化 canvas");
    // White background to avoid transparent PNG → black areas after JPEG conv
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);

    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("压缩失败"))),
        "image/jpeg",
        quality
      )
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

function UploadButton({
  label,
  disabled,
  inputRef,
  onFile,
}: {
  label: string;
  disabled: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onFile: (file: File) => void;
}) {
  return (
    <>
      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="px-3 py-1.5 text-sm rounded-md border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed transition"
      >
        {label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </>
  );
}
