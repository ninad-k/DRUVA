/**
 * Shared TypeScript types for the DHRUVA REST API.
 *
 * Kept loose where the backend response shape may evolve.
 */

export type UUID = string;
export type ISO8601 = string;

export interface User {
  id: UUID;
  email: string;
  display_name: string;
  created_at: ISO8601;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT" | "SL" | "SL-M";
export type ProductType = "MIS" | "CNC" | "NRML";
export type OrderStatus =
  | "PENDING"
  | "OPEN"
  | "COMPLETE"
  | "CANCELLED"
  | "REJECTED"
  | "TRIGGER_PENDING";

export interface Order {
  id: UUID;
  account_id: UUID;
  symbol: string;
  exchange: string;
  side: OrderSide;
  quantity: number;
  filled_quantity?: number;
  order_type: OrderType;
  product: ProductType;
  price?: number;
  trigger_price?: number;
  status: OrderStatus;
  average_price?: number;
  created_at: ISO8601;
  updated_at?: ISO8601;
}

export interface PlaceOrderRequest {
  account_id: UUID;
  symbol: string;
  exchange: string;
  side: OrderSide;
  quantity: number;
  order_type: OrderType;
  product: ProductType;
  price?: number;
  trigger_price?: number;
}

export interface Position {
  id: UUID;
  account_id: UUID;
  symbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_pct: number;
  product: ProductType;
}

export interface Strategy {
  id: UUID;
  account_id: UUID;
  name: string;
  strategy_class: string;
  mode: "paper" | "live";
  enabled: boolean;
  parameters: Record<string, unknown>;
  requires_approval?: boolean;
  is_ml?: boolean;
  model_version?: string;
  win_rate?: number;
  pnl?: number;
  pnl_history?: { ts: ISO8601; equity: number }[];
  created_at: ISO8601;
}

export interface Approval {
  id: UUID;
  account_id: UUID;
  strategy_id: UUID;
  strategy_name?: string;
  symbol: string;
  side: OrderSide;
  quantity: number;
  order_type: OrderType;
  price?: number;
  status: "pending" | "approved" | "rejected";
  created_at: ISO8601;
}

export interface BrokerAccount {
  id: UUID;
  broker:
    | "zerodha"
    | "upstox"
    | "dhan"
    | "fyers"
    | "five_paisa"
    | "alice_blue"
    | "angel_one"
    | "kotak_neo"
    | "shoonya";
  display_name: string;
  is_paper: boolean;
  is_connected: boolean;
  created_at: ISO8601;
}

export interface InstrumentSearchResult {
  symbol: string;
  exchange: string;
  name?: string;
  segment?: string;
  instrument_type?: string;
  lot_size?: number;
}

export interface OptionChainRow {
  strike: number;
  ce: OptionLeg;
  pe: OptionLeg;
}

export interface OptionLeg {
  ltp?: number;
  iv?: number;
  oi?: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

export interface OptionChain {
  underlying: string;
  expiry: string;
  spot: number;
  rows: OptionChainRow[];
}

export interface OiProfilePoint {
  strike: number;
  ce_oi: number;
  pe_oi: number;
}

export interface IvSmilePoint {
  strike: number;
  ce_iv?: number;
  pe_iv?: number;
}

export interface ScannerResult {
  pattern: string;
  symbol: string;
  exchange: string;
  setup_score: number;
  last_price: number;
  change_pct: number;
}

export interface Report {
  id: UUID;
  type: string;
  generated_at: ISO8601;
  url?: string;
  status: "pending" | "ready" | "failed";
}

export interface WebhookSource {
  id: UUID;
  source_type:
    | "chartink"
    | "tradingview"
    | "amibroker"
    | "metatrader"
    | "gocharting"
    | "n8n";
  display_name: string;
  created_at: ISO8601;
  revoked_at?: ISO8601;
}
