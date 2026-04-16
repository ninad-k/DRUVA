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
