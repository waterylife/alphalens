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

// ----------------------------- Portfolio -----------------------------

export interface Holding {
  id: number;
  market: string;
  asset_class: string;
  tag_l1: string | null;
  tag_l2: string | null;
  name: string;
  code: string | null;
  currency: string;
  current_price: number | null;
  cost_price: number | null;
  quantity: number | null;
  cost_value_cny: number;
  market_value_cny: number;
  unrealized_pnl_cny: number | null;
  return_pct: number | null;
  broker: string;
  weight: number;
  as_of: string;
}

export interface FxSnapshot {
  pair: string;
  rate: number;
  as_of: string;
}

export interface AllocationBucket {
  key: string;
  market_value_cny: number;
  weight: number;
}

export interface SyncRun {
  id: number;
  source: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  n_rows: number | null;
  error_msg: string | null;
}

export interface SyncResult {
  id: number;
  status: string;
  n_inserted: number;
  n_updated: number;
  fx_rates: Record<string, number>;
}

export interface ScreenshotRow {
  name: string;
  code: string | null;
  quantity: number | null;
  cost_price: number | null;
  current_price: number | null;
  market_value: number | null;
  cost_value: number | null;
  unrealized_pnl: number | null;
  return_pct: number | null;
  currency: string;
}

export interface ScreenshotParseResult {
  rows: ScreenshotRow[];
  warnings: string[];
}

export interface ImportRow {
  market: string;
  asset_class: string;
  tag_l1: string | null;
  tag_l2: string | null;
  name: string;
  code: string | null;
  currency: string;
  quantity: number | null;
  cost_price: number | null;
  current_price: number | null;
  market_value_cny: number;
  cost_value_cny: number | null;
  unrealized_pnl_cny: number | null;
  return_pct: number | null;
}

export interface ImportResult {
  id: number;
  status: string;
  n_inserted: number;
  n_updated: number;
}

export interface TagsConfig {
  tag_l1: string[];
  tag_l2: string[];
}

export interface RefreshPricesResult {
  id: number;
  status: string;
  n_updated: number;
  n_no_quote: number;
  n_skipped: number;
  skipped_examples: string[];
  fx_rates: Record<string, number>;
}

export interface PortfolioSummary {
  total_market_value_cny: number;
  total_cost_value_cny: number;
  total_unrealized_pnl_cny: number;
  total_return_pct: number | null;
  n_positions: number;
  last_updated: string | null;
  fx_rates: FxSnapshot[];
  by_market: AllocationBucket[];
  by_asset_class: AllocationBucket[];
  by_tag_l1: AllocationBucket[];
  by_broker: AllocationBucket[];
}

export const fetcher = async <T,>(url: string): Promise<T> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
};

// ─────────────────────────── HK Tech types ───────────────────────────

export interface HKStockSnapshot {
  ticker: string;
  name: string | null;
  price: number | null;
  change_pct: number | null;
  pe_ttm: number | null;
  pb: number | null;
  volume_hkd_mn: number | null;
  as_of: string;
}

export interface HKStockReturn {
  ticker: string;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_6m: number | null;
  ret_12m: number | null;
}

export interface HKStockSearchResult {
  ticker: string;
  name: string;
}

export interface HKIndexChartPoint {
  date: string;
  close: number;
}

export interface HKIndexChart {
  points: HKIndexChartPoint[];
}

export interface HKStockTechnical {
  ticker: string;
  rsi14: number | null;
  dist_ma200_pct: number | null;
  adtv_20d_hkd_mn: number | null;
  turnover_rate: number | null;
  volume_ratio: number | null;
  net_inflow_today_hkd_mn: number | null;
  net_inflow_5d_hkd_mn: number | null;
  pos_52w_pct: number | null;
  bid_ask_spread_bps: number | null;
  depth_ratio_5: number | null;
}

export interface HKStockFundamental {
  ticker: string;
  name: string | null;
  pe_ttm: number | null;
  forward_pe: number | null;
  pb: number | null;
  peg: number | null;
  ps_ttm: number | null;
  market_cap_hkd_bn: number | null;
  revenue_growth_pct: number | null;
  gross_margin_pct: number | null;
  roe_pct: number | null;
  beta: number | null;
}

export interface HKMarketLiquidity {
  vhsi: number | null;
  vhsi_change_pct: number | null;
  usd_hkd: number | null;
  hibor_1m: number | null;
  hibor_3m: number | null;
  us_10y_yield: number | null;
  as_of: string;
}

export interface HKSouthbound {
  net_inflow_mtd_hkd_bn: number | null;
  net_inflow_ytd_hkd_bn: number | null;
  as_of: string;
}

export interface HKSectorFlowRow {
  ticker: string;
  name: string | null;
  today_hkd_mn: number | null;
  d5_hkd_mn: number | null;
}

export interface HKSectorFlow {
  total_today_hkd_mn: number | null;
  total_5d_hkd_mn: number | null;
  breakdown: HKSectorFlowRow[];
  as_of: string;
}

export interface HKETFRow {
  ticker: string;
  name: string | null;
  price: number | null;
  change_pct: number | null;
  volume_hkd_mn: number | null;
  tracking_gap_pct: number | null;
}

export interface HKETFPanel {
  index_change_pct: number | null;
  items: HKETFRow[];
  as_of: string;
}

export interface HKStrategyComponents {
  valuation: number | null;
  momentum: number | null;
  flow: number | null;
  liquidity: number | null;
  macro_delta: number | null;
}

export interface HKStrategySignal {
  ticker: string;
  action: "buy" | "hold" | "sell" | string;
  score: number | null;
  components: HKStrategyComponents;
  triggers: string[];
  explanation: string | null;
}

// ─────────────────────────── US Tech types ───────────────────────────

export interface USStockSnapshot {
  ticker: string;
  name: string | null;
  price: number | null;
  change_pct: number | null;
  volume_usd_mn: number | null;
  as_of: string;
}

export interface USStockReturn {
  ticker: string;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_6m: number | null;
  ret_12m: number | null;
}

export interface USStockFundamental {
  ticker: string;
  name: string | null;
  pe_ttm: number | null;
  forward_pe: number | null;
  peg: number | null;
  pb: number | null;
  ps_ttm: number | null;
  market_cap_usd_bn: number | null;
  revenue_growth_pct: number | null;
  gross_margin_pct: number | null;
  roe_pct: number | null;
  eps_ttm: number | null;
  dividend_yield_pct: number | null;
  beta: number | null;
}

export interface USStockTechnical {
  ticker: string;
  rsi14: number | null;
  dist_ma200_pct: number | null;
  pos_52w_pct: number | null;
  dist_ath_pct: number | null;
  adtv_20d_usd_mn: number | null;
  short_pct_float: number | null;
}

export interface USMacro {
  vix: number | null;
  vix_change_pct: number | null;
  us_10y: number | null;
  us_2y: number | null;
  dxy: number | null;
  fed_funds_13w: number | null;
  curve_2s10s_bps: number | null;
  as_of: string;
}

export interface USSectorRow {
  ticker: string;
  sector: string;
  price: number | null;
  change_pct: number | null;
  change_5d_pct: number | null;
  volume_usd_mn: number | null;
}

export interface USSectorFlow {
  items: USSectorRow[];
  as_of: string;
}

export interface USIndexChart {
  symbol: string;
  points: { date: string; close: number }[];
}

export interface USStockSearchResult {
  ticker: string;
  name: string;
}

export interface USStrategyComponents {
  valuation: number | null;
  momentum: number | null;
  quality: number | null;
  risk: number | null;
  macro_delta: number | null;
}

export interface USStrategySignal {
  ticker: string;
  action: "buy" | "hold" | "sell" | string;
  score: number | null;
  components: USStrategyComponents;
  triggers: string[];
  explanation: string | null;
}

// ───────────────────────── Investment Agent types ─────────────────────

export interface StrategyDocument {
  id: number;
  title: string;
  category: string;
  symbols: string[];
  thesis: string;
  conclusion: string;
  summary: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface StrategyDocumentList {
  items: StrategyDocument[];
  total: number;
}

export interface AgentConversationResult {
  document: StrategyDocument;
  reply: string;
}

// ─────────────────────────────────────────────────────────────────────

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

  // HK Tech
  hkDefaults: () => "/api/hktech/stocks/defaults",
  hkSnapshot: (tickers: string[]) =>
    `/api/hktech/stocks/snapshot?tickers=${tickers.join(",")}`,
  hkReturns: (tickers: string[]) =>
    `/api/hktech/stocks/returns?tickers=${tickers.join(",")}`,
  hkSearch: (q: string) =>
    `/api/hktech/stocks/search?q=${encodeURIComponent(q)}`,
  hkIndexChart: (years = 1) => `/api/hktech/index/chart?years=${years}`,
  hkIndexCompare: (years = 3) => `/api/hktech/index/benchmark-compare?years=${years}`,
  hkTechnicals: (tickers: string[]) =>
    `/api/hktech/stocks/technicals?tickers=${tickers.join(",")}`,
  hkFundamentals: (tickers: string[]) =>
    `/api/hktech/stocks/fundamentals?tickers=${tickers.join(",")}`,
  hkMarketLiquidity: () => "/api/hktech/market/liquidity",
  hkSouthbound: () => "/api/hktech/market/southbound",
  hkSectorFlow: (tickers: string[]) =>
    `/api/hktech/market/sector-flow?tickers=${tickers.join(",")}`,
  hkETFPanel: () => "/api/hktech/market/etf-panel",
  hkSignals: (tickers: string[]) =>
    `/api/hktech/stocks/signals?tickers=${tickers.join(",")}`,

  // US Tech
  usDefaults: () => "/api/us/stocks/defaults",
  usSnapshot: (tickers: string[]) =>
    `/api/us/stocks/snapshot?tickers=${tickers.join(",")}`,
  usReturns: (tickers: string[]) =>
    `/api/us/stocks/returns?tickers=${tickers.join(",")}`,
  usFundamentals: (tickers: string[]) =>
    `/api/us/stocks/fundamentals?tickers=${tickers.join(",")}`,
  usTechnicals: (tickers: string[]) =>
    `/api/us/stocks/technicals?tickers=${tickers.join(",")}`,
  usSearch: (q: string) => `/api/us/stocks/search?q=${encodeURIComponent(q)}`,
  usSignals: (tickers: string[]) =>
    `/api/us/stocks/signals?tickers=${tickers.join(",")}`,
  usMacro: () => "/api/us/market/macro",
  usSectorFlow: () => "/api/us/market/sector-flow",
  usIndexChart: (symbol: string, years = 1) =>
    `/api/us/indices/chart?symbol=${encodeURIComponent(symbol)}&years=${years}`,

  // Portfolio
  portfolioHoldings: () => "/api/portfolio/holdings",
  portfolioSummary: () => "/api/portfolio/summary",
  portfolioSyncRuns: () => "/api/portfolio/sync-runs",
  portfolioSyncFutu: () => "/api/portfolio/sync/futu",
  portfolioScreenshotParse: () => "/api/portfolio/screenshot-parse",
  portfolioImportRows: () => "/api/portfolio/import-rows",
  portfolioTiantianBrowserToken: () => "/api/portfolio/tiantian-browser-token",
  portfolioTags: () => "/api/portfolio/tags",
  portfolioPatchHolding: (id: number) => `/api/portfolio/holdings/${id}`,
  portfolioRefreshPrices: () => "/api/portfolio/refresh-prices",

  // Investment Agent
  agentRecentDocument: () => "/api/agent/documents/recent",
  agentCategories: () => "/api/agent/categories",
  agentDocuments: (q = "", category = "全部") => {
    const qs = new URLSearchParams();
    if (q.trim()) qs.set("q", q.trim());
    if (category && category !== "全部") qs.set("category", category);
    return `/api/agent/documents${qs.toString() ? `?${qs.toString()}` : ""}`;
  },
  agentDocument: (id: number) => `/api/agent/documents/${id}`,
  agentChat: () => "/api/agent/chat",
};
