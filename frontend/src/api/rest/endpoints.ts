/**
 * Thin wrappers around the REST API. Pure functions — never call hooks.
 *
 * Hooks live in `src/hooks/use<Resource>.ts` and use these via React Query.
 */
import { rest } from "./axios";
import type {
  Approval,
  AuthTokens,
  BrokerAccount,
  InstrumentSearchResult,
  IvSmilePoint,
  OiProfilePoint,
  OptionChain,
  Order,
  PlaceOrderRequest,
  Position,
  Report,
  ScannerResult,
  Strategy,
  User,
  WebhookSource,
} from "@/types/api";

const BASE = "/v1";

// ---------- Auth ----------
export async function apiRegister(input: {
  email: string;
  password: string;
  display_name: string;
}): Promise<void> {
  await rest.post(`${BASE}/auth/register`, input);
}

export async function apiLogin(input: {
  email: string;
  password: string;
}): Promise<AuthTokens> {
  const { data } = await rest.post<AuthTokens>(`${BASE}/auth/login`, input);
  return data;
}

export async function apiRefresh(refresh_token: string): Promise<AuthTokens> {
  const { data } = await rest.post<AuthTokens>(`${BASE}/auth/refresh`, { refresh_token });
  return data;
}

export async function apiLogout(): Promise<void> {
  await rest.post(`${BASE}/auth/logout`);
}

export async function apiMe(): Promise<User> {
  const { data } = await rest.get<User>(`${BASE}/auth/me`);
  return data;
}

// ---------- Orders ----------
export async function listOrders(params: { account_id?: string } = {}): Promise<Order[]> {
  const { data } = await rest.get<Order[]>(`${BASE}/orders`, { params });
  return Array.isArray(data) ? data : (data as { items?: Order[] })?.items ?? [];
}

export async function placeOrder(input: PlaceOrderRequest): Promise<Order> {
  const { data } = await rest.post<Order>(`${BASE}/orders`, input);
  return data;
}

export async function placeSmartOrder(
  input: PlaceOrderRequest & { target_quantity: number },
): Promise<Order> {
  const { data } = await rest.post<Order>(`${BASE}/orders/smart`, input);
  return data;
}

export async function placeBasket(input: {
  orders: PlaceOrderRequest[];
  atomic: boolean;
}): Promise<{ orders: Order[] }> {
  const { data } = await rest.post(`${BASE}/orders/basket`, input);
  return data;
}

export async function cancelOrder(orderId: string): Promise<void> {
  await rest.post(`${BASE}/orders/${orderId}/cancel`);
}

export async function modifyOrder(
  orderId: string,
  patch: Partial<PlaceOrderRequest>,
): Promise<Order> {
  const { data } = await rest.patch<Order>(`${BASE}/orders/${orderId}`, patch);
  return data;
}

export async function cancelAllOrders(accountId: string): Promise<void> {
  await rest.post(`${BASE}/accounts/${accountId}/orders/cancel-all`);
}

// ---------- Positions ----------
export async function listPositions(params: { account_id?: string } = {}): Promise<Position[]> {
  const { data } = await rest.get<Position[]>(`${BASE}/positions`, { params });
  return Array.isArray(data) ? data : (data as { items?: Position[] })?.items ?? [];
}

export async function closePosition(accountId: string, symbol: string): Promise<void> {
  await rest.post(`${BASE}/accounts/${accountId}/positions/${encodeURIComponent(symbol)}/close`);
}

// ---------- Strategies ----------
export async function listStrategies(params: { account_id?: string } = {}): Promise<Strategy[]> {
  const { data } = await rest.get<Strategy[]>(`${BASE}/strategies`, { params });
  return Array.isArray(data) ? data : (data as { items?: Strategy[] })?.items ?? [];
}

export async function getStrategy(id: string): Promise<Strategy> {
  const { data } = await rest.get<Strategy>(`${BASE}/strategies/${id}`);
  return data;
}

export async function createStrategy(input: Partial<Strategy>): Promise<Strategy> {
  const { data } = await rest.post<Strategy>(`${BASE}/strategies`, input);
  return data;
}

export async function enableStrategy(id: string): Promise<void> {
  await rest.post(`${BASE}/strategies/${id}/enable`);
}

export async function disableStrategy(id: string): Promise<void> {
  await rest.post(`${BASE}/strategies/${id}/disable`);
}

export interface BacktestRequest {
  from: string;
  to: string;
  symbols: string[];
  timeframe: string;
}

export interface BacktestResult {
  metrics: {
    total_return_pct?: number;
    sharpe?: number;
    sortino?: number;
    max_drawdown_pct?: number;
    win_rate?: number;
    trades?: number;
  };
  equity_curve: { ts: string; equity: number }[];
}

export async function runBacktest(id: string, input: BacktestRequest): Promise<BacktestResult> {
  const { data } = await rest.post<BacktestResult>(`${BASE}/strategies/${id}/backtest`, input);
  return data;
}

// ---------- Approvals ----------
export async function listApprovals(params: {
  account_id?: string;
  status?: "pending" | "approved" | "rejected";
}): Promise<Approval[]> {
  const { data } = await rest.get<Approval[]>(`${BASE}/approvals`, { params });
  return Array.isArray(data) ? data : (data as { items?: Approval[] })?.items ?? [];
}

export async function approveApproval(id: string): Promise<void> {
  await rest.post(`${BASE}/approvals/${id}/approve`);
}

export async function rejectApproval(id: string): Promise<void> {
  await rest.post(`${BASE}/approvals/${id}/reject`);
}

// ---------- Instruments ----------
export async function searchInstruments(params: {
  q: string;
  exchange?: string;
  limit?: number;
}): Promise<InstrumentSearchResult[]> {
  const { data } = await rest.get<InstrumentSearchResult[]>(`${BASE}/instruments/search`, {
    params,
  });
  return Array.isArray(data) ? data : (data as { items?: InstrumentSearchResult[] })?.items ?? [];
}

// ---------- Calendar ----------
export async function isMarketOpen(exchange: string): Promise<{ is_open: boolean; reason?: string }> {
  const { data } = await rest.get<{ is_open: boolean; reason?: string }>(`${BASE}/calendar/is-open`, {
    params: { exchange },
  });
  return data;
}

// ---------- Options ----------
export async function getOptionChain(params: {
  account_id: string;
  underlying: string;
  expiry: string;
  spot?: number;
  risk_free_rate?: number;
}): Promise<OptionChain> {
  const { data } = await rest.get<OptionChain>(`${BASE}/options/chain`, { params });
  return data;
}

export async function getOiProfile(params: {
  account_id: string;
  underlying: string;
  expiry: string;
}): Promise<OiProfilePoint[]> {
  const { data } = await rest.get<OiProfilePoint[]>(`${BASE}/options/oi-profile`, { params });
  return Array.isArray(data) ? data : (data as { items?: OiProfilePoint[] })?.items ?? [];
}

export async function getIvSmile(params: {
  account_id: string;
  underlying: string;
  expiry: string;
}): Promise<IvSmilePoint[]> {
  const { data } = await rest.get<IvSmilePoint[]>(`${BASE}/options/iv-smile`, { params });
  return Array.isArray(data) ? data : (data as { items?: IvSmilePoint[] })?.items ?? [];
}

// ---------- Accounts ----------
export async function listAccounts(): Promise<BrokerAccount[]> {
  const { data } = await rest.get<BrokerAccount[]>(`${BASE}/accounts`);
  return Array.isArray(data) ? data : (data as { items?: BrokerAccount[] })?.items ?? [];
}

export async function createAccount(input: {
  broker: BrokerAccount["broker"];
  display_name?: string;
  api_key: string;
  api_secret: string;
  is_paper: boolean;
}): Promise<BrokerAccount> {
  const { data } = await rest.post<BrokerAccount>(`${BASE}/accounts`, input);
  return data;
}

// ---------- Scanner ----------
export async function listScannerResults(params: {
  pattern?: string;
  min_score?: number;
}): Promise<ScannerResult[]> {
  const { data } = await rest.get<ScannerResult[]>(`${BASE}/scanner`, { params });
  return Array.isArray(data) ? data : (data as { items?: ScannerResult[] })?.items ?? [];
}

// ---------- Reports ----------
export async function listReports(): Promise<Report[]> {
  const { data } = await rest.get<Report[]>(`${BASE}/reports`);
  return Array.isArray(data) ? data : (data as { items?: Report[] })?.items ?? [];
}

export async function generateReport(type: string): Promise<Report> {
  const { data } = await rest.post<Report>(`${BASE}/reports`, { type });
  return data;
}

// ---------- Notifications ----------
export async function linkTelegram(chat_id: string): Promise<void> {
  await rest.post(`${BASE}/notifications/telegram`, { chat_id });
}

export async function listWebhookSources(): Promise<WebhookSource[]> {
  const { data } = await rest.get<WebhookSource[]>(`${BASE}/notifications/webhooks`);
  return Array.isArray(data) ? data : (data as { items?: WebhookSource[] })?.items ?? [];
}

export async function createWebhookSource(input: {
  source_type: WebhookSource["source_type"];
  display_name: string;
}): Promise<WebhookSource & { token: string }> {
  const { data } = await rest.post<WebhookSource & { token: string }>(
    `${BASE}/notifications/webhooks`,
    input,
  );
  return data;
}

export async function revokeWebhookSource(id: string): Promise<void> {
  await rest.post(`${BASE}/notifications/webhooks/${id}/revoke`);
}

// ---------- AI Advisor ----------
export type AdvisorProvider =
  | "none"
  | "anthropic"
  | "openai"
  | "ollama"
  | "openai_compatible";

export interface AdvisorLLMConfig {
  id: string;
  provider: AdvisorProvider;
  model: string;
  base_url: string;
  has_api_key: boolean;
  temperature: number;
  max_tokens: number;
  is_enabled: boolean;
  updated_at: string;
}

export interface AdvisorWatchlistItem {
  id: string;
  symbol: string;
  exchange: string;
  sector: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface AdvisorRun {
  id: string;
  ran_at: string;
  macro_regime: "aggressive" | "neutral" | "defensive";
  nifty_roc: number | null;
  smallcap_roc: number | null;
  llm_provider: string | null;
  llm_model: string | null;
  symbols_scanned: number;
}

export interface AdvisorScore {
  symbol: string;
  exchange: string;
  last_price: number | null;
  composite_score: number;
  fundamental_score: number;
  technical_score: number;
  momentum_score: number;
  llm_score: number | null;
  multibagger_tier: string | null;
  stop_loss: number | null;
  target_price: number | null;
  suggested_allocation_pct: number;
  rationale: string | null;
  features: Record<string, unknown>;
}

export interface AdvisorAllocation {
  symbol: string;
  exchange: string;
  tier: string;
  suggested_pct: number;
  suggested_inr: number;
  qty: number;
  stop_loss: number;
  target_price: number;
}

export async function getAdvisorConfig(): Promise<AdvisorLLMConfig | null> {
  const { data } = await rest.get<AdvisorLLMConfig | null>(`${BASE}/advisor/config`);
  return data;
}

export async function saveAdvisorConfig(input: {
  provider: AdvisorProvider;
  model: string;
  base_url?: string;
  api_key?: string;
  temperature?: number;
  max_tokens?: number;
  is_enabled?: boolean;
}): Promise<AdvisorLLMConfig> {
  const { data } = await rest.put<AdvisorLLMConfig>(`${BASE}/advisor/config`, input);
  return data;
}

export async function listAdvisorWatchlist(): Promise<AdvisorWatchlistItem[]> {
  const { data } = await rest.get<AdvisorWatchlistItem[]>(`${BASE}/advisor/watchlist`);
  return data;
}

export async function addAdvisorWatchlist(input: {
  symbol: string;
  exchange?: string;
  sector?: string;
  notes?: string;
}): Promise<AdvisorWatchlistItem> {
  const { data } = await rest.post<AdvisorWatchlistItem>(`${BASE}/advisor/watchlist`, input);
  return data;
}

export async function removeAdvisorWatchlist(id: string): Promise<void> {
  await rest.delete(`${BASE}/advisor/watchlist/${id}`);
}

export interface AdvisorRunResult {
  run_id: string;
  regime: "aggressive" | "neutral" | "defensive";
  scored: number;
  top_picks: AdvisorScore[];
}

export async function triggerAdvisorRun(input: {
  capital_inr: number;
  max_positions?: number;
  stop_loss_pct?: number;
}): Promise<AdvisorRunResult> {
  const { data } = await rest.post<AdvisorRunResult>(`${BASE}/advisor/runs`, input);
  return data;
}

export async function listAdvisorRuns(): Promise<AdvisorRun[]> {
  const { data } = await rest.get<AdvisorRun[]>(`${BASE}/advisor/runs`);
  return data;
}

export async function latestAdvisorScores(): Promise<AdvisorScore[]> {
  const { data } = await rest.get<AdvisorScore[]>(`${BASE}/advisor/runs/latest/scores`);
  return data;
}

export async function allocateAdvisor(params: {
  capital_inr: number;
  max_positions?: number;
  stop_loss_pct?: number;
}): Promise<AdvisorAllocation[]> {
  const { data } = await rest.post<AdvisorAllocation[]>(`${BASE}/advisor/allocate`, null, {
    params,
  });
  return data;
}

// ---------- Multibagger Scanners ----------
export interface MultibaggerScanner {
  id: string;
  account_id: string;
  name: string;
  scanner_class: string;
  parameters: Record<string, unknown>;
  cadence: string;
  is_enabled: boolean;
  last_run_at: string | null;
}

export interface ScanResultRow {
  id: string;
  scanner_id: string;
  run_ts: string;
  symbol: string;
  exchange: string;
  score: number;
  stage: string | null;
  reason: string | null;
  suggested_entry: number | null;
  suggested_stop: number | null;
  suggested_target: number | null;
  status: string;
  metadata: Record<string, unknown>;
}

export async function listMultibaggerScannerRegistry(): Promise<string[]> {
  const { data } = await rest.get<string[]>(`${BASE}/scanners/registry`);
  return data;
}

export async function listMultibaggerScanners(
  account_id: string,
): Promise<MultibaggerScanner[]> {
  const { data } = await rest.get<MultibaggerScanner[]>(`${BASE}/scanners`, {
    params: { account_id },
  });
  return data;
}

export async function createMultibaggerScanner(input: {
  account_id: string;
  name: string;
  scanner_class: string;
  parameters?: Record<string, unknown>;
  cadence?: string;
}): Promise<MultibaggerScanner> {
  const { data } = await rest.post<MultibaggerScanner>(`${BASE}/scanners`, input);
  return data;
}

export async function enableMultibaggerScanner(id: string): Promise<MultibaggerScanner> {
  const { data } = await rest.post<MultibaggerScanner>(`${BASE}/scanners/${id}/enable`);
  return data;
}

export async function disableMultibaggerScanner(id: string): Promise<MultibaggerScanner> {
  const { data } = await rest.post<MultibaggerScanner>(`${BASE}/scanners/${id}/disable`);
  return data;
}

export async function deleteMultibaggerScanner(id: string): Promise<void> {
  await rest.delete(`${BASE}/scanners/${id}`);
}

export async function runMultibaggerScanner(
  id: string,
): Promise<{ scanner_id: string; emitted: number }> {
  const { data } = await rest.post(`${BASE}/scanners/${id}/run-now`);
  return data;
}

export interface MultibaggerBacktestMetrics {
  total_return_pct: string;
  cagr_pct: string;
  sharpe: string;
  max_drawdown_pct: string;
  win_rate_pct: string;
  avg_hold_days: string;
  trades: number;
  multibagger_2x: number;
  multibagger_5x: number;
  multibagger_10x: number;
}

export async function backtestMultibaggerScanner(
  id: string,
  input: { start: string; end: string; initial_equity?: number; step_days?: number },
): Promise<{
  metrics: MultibaggerBacktestMetrics;
  equity_curve: { ts: string; equity: string }[];
  trades: {
    symbol: string;
    entry_date: string;
    exit_date: string;
    entry_price: string;
    exit_price: string;
    return_pct: string;
  }[];
}> {
  const { data } = await rest.post(`${BASE}/scanners/${id}/backtest`, input);
  return data;
}

export async function listScanResults(params: {
  scanner_id?: string;
  account_id?: string;
  status?: string;
  limit?: number;
}): Promise<ScanResultRow[]> {
  const { data } = await rest.get<ScanResultRow[]>(`${BASE}/scan-results`, { params });
  return data;
}

export async function promoteScanResult(
  id: string,
  capital_inr?: number,
): Promise<{ result_id: string; approval_id: string | null; reason: string | null }> {
  const { data } = await rest.post(`${BASE}/scan-results/${id}/promote`, {
    capital_inr,
  });
  return data;
}

export async function dismissScanResult(id: string): Promise<ScanResultRow> {
  const { data } = await rest.post<ScanResultRow>(`${BASE}/scan-results/${id}/dismiss`);
  return data;
}

export async function acknowledgeScanResult(id: string): Promise<ScanResultRow> {
  const { data } = await rest.post<ScanResultRow>(`${BASE}/scan-results/${id}/acknowledge`);
  return data;
}

// ---------- Fundamentals ----------
export interface Fundamentals {
  symbol: string;
  exchange: string;
  as_of_date: string;
  roe: number | null;
  roce: number | null;
  eps: number | null;
  sales_growth_3y: number | null;
  profit_growth_3y: number | null;
  debt_to_equity: number | null;
  promoter_holding: number | null;
  market_cap: number | null;
  current_price: number | null;
  pe_ratio: number | null;
  sector: string | null;
  industry: string | null;
  source: string;
}

export async function getFundamentals(symbol: string, exchange = "NSE"): Promise<Fundamentals> {
  const { data } = await rest.get<Fundamentals>(`${BASE}/fundamentals/${symbol}`, {
    params: { exchange },
  });
  return data;
}

export async function refreshFundamentals(limit = 50): Promise<{ status: string; limit: number }> {
  const { data } = await rest.post(`${BASE}/fundamentals/refresh`, null, {
    params: { limit },
  });
  return data;
}

// ---------- Market Cycle ----------
export interface MarketCycleSnapshot {
  as_of_date: string;
  regime: "bull" | "neutral" | "bear";
  nifty_roc_18m: number | null;
  smallcap_roc_20m: number | null;
  suggested_allocation_pct: number;
  breadth_score: number | null;
  note: string | null;
}

export async function getMarketCycleCurrent(): Promise<MarketCycleSnapshot | null> {
  try {
    const { data } = await rest.get<MarketCycleSnapshot>(`${BASE}/market-cycle/current`);
    return data;
  } catch {
    return null;
  }
}

export async function getMarketCycleHistory(days = 90): Promise<MarketCycleSnapshot[]> {
  const { data } = await rest.get<MarketCycleSnapshot[]>(`${BASE}/market-cycle/history`, {
    params: { days },
  });
  return data;
}

export async function recomputeMarketCycle(): Promise<MarketCycleSnapshot> {
  const { data } = await rest.post<MarketCycleSnapshot>(`${BASE}/market-cycle/recompute`);
  return data;
}

// ---------- Goals ----------
export interface Goal {
  id: string;
  account_id: string;
  name: string;
  target_amount: string;
  target_date: string;
  current_value: string;
  monthly_sip_amount: string;
  arbitrage_buffer_pct: string;
  equity_allocation_pct: string;
  status: string;
  target_symbols: string[];
}

export interface GoalProgress {
  goal_id: string;
  name: string;
  target_amount: string;
  target_date: string;
  current_value: string;
  progress_pct: string;
  months_remaining: number;
  projected_value: string;
  required_monthly: string;
}

export async function listGoals(account_id: string): Promise<Goal[]> {
  const { data } = await rest.get<Goal[]>(`${BASE}/goals`, { params: { account_id } });
  return data;
}

export async function createGoal(input: {
  account_id: string;
  name: string;
  target_amount: number;
  target_date: string;
  monthly_sip_amount?: number;
  arbitrage_buffer_pct?: number;
  equity_allocation_pct?: number;
  target_symbols?: string[];
}): Promise<Goal> {
  const { data } = await rest.post<Goal>(`${BASE}/goals`, input);
  return data;
}

export async function getGoalProgress(id: string): Promise<GoalProgress> {
  const { data } = await rest.get<GoalProgress>(`${BASE}/goals/${id}/progress`);
  return data;
}

export async function createStpPlan(
  id: string,
  input: { lump_sum: number; months?: number; day_of_month?: number },
): Promise<{
  schedule_id: string;
  next_run_date: string;
  amount_per_tranche: string;
  tranches_remaining: number;
}> {
  const { data } = await rest.post(`${BASE}/goals/${id}/stp-plan`, input);
  return data;
}

export async function pauseGoal(id: string): Promise<Goal> {
  const { data } = await rest.post<Goal>(`${BASE}/goals/${id}/pause`);
  return data;
}

export async function resumeGoal(id: string): Promise<Goal> {
  const { data } = await rest.post<Goal>(`${BASE}/goals/${id}/resume`);
  return data;
}
