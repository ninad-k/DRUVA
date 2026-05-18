/**
 * Public surface of the gRPC/Connect-RPC layer.
 *
 * Import from "@/api/grpc" to get:
 *  - Transport: `grpcTransport`, `setGrpcAccessToken`
 *  - Client factory: `createGrpcClient`
 *  - React Query hooks: `useGrpcOrders`, `useGrpcPlaceOrder`, ...
 */
export { grpcTransport, setGrpcAccessToken } from "./transport";
export { createGrpcClient } from "./client";
export {
  useGrpcOrders,
  useGrpcPlaceOrder,
  useGrpcCancelOrder,
  useGrpcPositions,
  useGrpcStrategies,
  useGrpcStrategy,
  useGrpcInstrumentSearch,
  useGrpcScanResults,
  useGrpcGoals,
  useGrpcCreateGoal,
} from "./hooks";
export type { Goal } from "./hooks";
