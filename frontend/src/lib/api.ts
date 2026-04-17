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
  dividend_yield_percentile: number | null;
  pe_percentile: number | null;
}

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
};
