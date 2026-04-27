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

  // One file input per broker, triggered programmatically
  const tiantianRef = useRef<HTMLInputElement>(null);
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
          label={busy === "screenshot:tiantian" ? "识别中…" : "上传天天基金截图"}
          disabled={!!busy}
          inputRef={tiantianRef}
          onFile={(f) => uploadScreenshot("tiantian", f)}
        />
        <UploadButton
          label={busy === "screenshot:eastmoney" ? "识别中…" : "上传东方财富截图"}
          disabled={!!busy}
          inputRef={eastmoneyRef}
          onFile={(f) => uploadScreenshot("eastmoney", f)}
        />

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
