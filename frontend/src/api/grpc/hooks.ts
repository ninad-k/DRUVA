/**
 * React Query hooks shaped for Connect-RPC / gRPC-Web.
 *
 * TODAY: These hooks call the existing REST endpoints so the app works
 * while buf codegen is being wired up.
 *
 * MIGRATION PATH: Once `buf generate` has produced TypeScript service
 * definitions under `src/api/grpc/_generated/`, replace each `queryFn`
 * with a `createGrpcClient(XxxService).method(...)` call.  The hook
 * signatures, query keys, and return types stay identical — no consumer
 * changes required.
 *
 * Example (post-migration):
 *   import { createGrpcClient } from "./client"
 *   import { OrderService } from "./_generated/dhruva/v1/orders_connect"
 *
 *   const orderClient = createGrpcClient(OrderService)
 *
 *   export function useGrpcOrders(accountId: string) {
 *     return useQuery({
 *       queryKey: ["grpc", "orders", accountId],
 *       queryFn: () => orderClient.listOrders({ accountId }),
 *       enabled: !!accountId,
 *     })
 *   }
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listOrders,
  placeOrder,
  cancelOrder,
  listPositions,
  listStrategies,
  getStrategy,
  searchInstruments,
  listScanResults,
  listGoals,
  createGoal,
  type Goal,
} from "@/api/rest/endpoints";
import type { PlaceOrderRequest } from "@/types/api";

// ── Orders ────────────────────────────────────────────────────────────────────

/**
 * Fetch all orders for the given account.
 * REST-backed now; replace queryFn with gRPC call after codegen.
 */
export function useGrpcOrders(accountId: string) {
  return useQuery({
    queryKey: ["grpc", "orders", accountId],
    queryFn: () => listOrders({ account_id: accountId }),
    enabled: !!accountId,
  });
}

/**
 * Place a new order.
 * Invalidates the grpc orders cache on success.
 */
export function useGrpcPlaceOrder(accountId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: PlaceOrderRequest) => placeOrder(req),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["grpc", "orders", accountId] });
    },
  });
}

/**
 * Cancel an order by id.
 */
export function useGrpcCancelOrder(accountId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) => cancelOrder(orderId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["grpc", "orders", accountId] });
    },
  });
}

// ── Positions ─────────────────────────────────────────────────────────────────

/**
 * Fetch open positions for the given account.
 */
export function useGrpcPositions(accountId: string) {
  return useQuery({
    queryKey: ["grpc", "positions", accountId],
    queryFn: () => listPositions({ account_id: accountId }),
    enabled: !!accountId,
    refetchInterval: 30_000,
  });
}

// ── Strategies ────────────────────────────────────────────────────────────────

/**
 * Fetch all strategies for the given account.
 */
export function useGrpcStrategies(accountId: string) {
  return useQuery({
    queryKey: ["grpc", "strategies", accountId],
    queryFn: () => listStrategies({ account_id: accountId }),
    enabled: !!accountId,
  });
}

/**
 * Fetch a single strategy by id.
 */
export function useGrpcStrategy(id: string) {
  return useQuery({
    queryKey: ["grpc", "strategy", id],
    queryFn: () => getStrategy(id),
    enabled: !!id,
  });
}

// ── Instruments ───────────────────────────────────────────────────────────────

/**
 * Search instruments (debounce is the caller's responsibility).
 */
export function useGrpcInstrumentSearch(q: string) {
  return useQuery({
    queryKey: ["grpc", "instruments-search", q],
    queryFn: () => searchInstruments({ q, limit: 10 }),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
}

// ── Scanner results ───────────────────────────────────────────────────────────

/**
 * Fetch multibagger scan results.
 */
export function useGrpcScanResults(params: {
  accountId?: string;
  status?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["grpc", "scan-results", params],
    queryFn: () =>
      listScanResults({
        account_id: params.accountId,
        status: params.status,
        limit: params.limit,
      }),
    enabled: !!params.accountId,
    refetchInterval: 60_000,
  });
}

// ── Goals ─────────────────────────────────────────────────────────────────────

/**
 * Fetch goals for the given account.
 */
export function useGrpcGoals(accountId: string) {
  return useQuery({
    queryKey: ["grpc", "goals", accountId],
    queryFn: () => listGoals(accountId),
    enabled: !!accountId,
  });
}

/**
 * Create a new goal.
 */
export function useGrpcCreateGoal(accountId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof createGoal>[0]) => createGoal(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["grpc", "goals", accountId] });
    },
  });
}

// ── Re-export Goal type so consumers don't need a separate import ──────────────
export type { Goal };
