// Typed API client. All requests go through the Next.js rewrite to the
// FastAPI backend on port 8000.

export interface IndexMeta {
  code: string;
  name: string;
  full_name: string;
  exchange: string;
  description: string;
  supports_long_history_pe: boolean;
}

export interface Overview {
  code: string;
  name: string;
  as_of: string;
  close: number | null;
  change_pct: number | null;
  pe_ttm: number | null;
  pe_static: number | null;
  dividend_yield: number | null;
  yield_spread_bps: number | null;
  dividend_yield_percentile: Record<ValuationWindow, number | null>;
  dividend_yield_history_start: string | null;
  pe_percentile: Record<ValuationWindow, number | null>;
  pe_history_start: string | null;
}

export type ValuationWindow = "1y" | "3y" | "5y" | "10y" | "all";

export interface TimeSeriesPoint {
  date: string;
  value: number | null;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ValuationSeries {
  code: string;
  pe_ttm: TimeSeriesPoint[];
  pe_static: TimeSeriesPoint[];
  dividend_yield: TimeSeriesPoint[];
  pb: TimeSeriesPoint[];
}

export interface YieldSpreadPoint {
  date: string;
  dividend_yield: number;
  yield_10y: number;
  spread: number;
}

export interface YieldSpreadSeries {
  code: string;
  points: YieldSpreadPoint[];
}

export interface ConstituentItem {
  stock_code: string;
  stock_name: string;
  exchange: string;
  weight: number | null;
}

export interface Constituents {
  code: string;
  as_of: string;
  total: number;
  items: ConstituentItem[];
}

export interface BenchmarkMeta {
  code: string;
  name: string;
}

export interface RangeStats {
  return_pct: number | null;
  annualized_pct: number | null;
  max_drawdown: number | null;
  max_gain: number | null;
  volatility: number | null;
}

export interface ComparePoint {
  date: string;
  close: number;
}

export interface CompareSeries {
  code: string;
  name: string;
  points: ComparePoint[];
  stats: RangeStats;
}

export interface YearlyRow {
  year: number;
  index_return: number | null;
  benchmark_return: number | null;
  index_volatility: number | null;
  benchmark_volatility: number | null;
  index_max_drawdown: number | null;
  benchmark_max_drawdown: number | null;
  index_max_gain: number | null;
  benchmark_max_gain: number | null;
}

export interface BenchmarkCompare {
  start: string;
  end: string;
  index: CompareSeries;
  benchmark: CompareSeries;
  yearly: YearlyRow[];
}

export const fetcher = async <T,>(url: string): Promise<T> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
};

export const api = {
  indices: () => "/api/dividend/indices",
  overview: (code: string) => `/api/dividend/indices/${code}/overview`,
  priceHistory: (code: string, years = 10) =>
    `/api/dividend/indices/${code}/price-history?years=${years}`,
  valuationHistory: (code: string, years = 10) =>
    `/api/dividend/indices/${code}/valuation-history?years=${years}`,
  yieldSpread: (code: string, years = 10) =>
    `/api/dividend/indices/${code}/yield-spread?years=${years}`,
  constituents: (code: string, limit = 30) =>
    `/api/dividend/indices/${code}/constituents?limit=${limit}`,
  benchmarks: () => "/api/dividend/benchmarks",
  benchmarkCompare: (
    code: string,
    benchmark: string,
    start?: string,
    end?: string
  ) => {
    const qs = new URLSearchParams({ benchmark });
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);
    return `/api/dividend/indices/${code}/benchmark-compare?${qs.toString()}`;
  },
};
