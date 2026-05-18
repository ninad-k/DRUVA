/**
 * Connect-RPC / gRPC-Web client factory.
 *
 * Usage:
 *   import { grpcTransport, createGrpcClient } from "@/api/grpc/client"
 *   import { OrderService } from "@/api/grpc/_generated/dhruva/v1/orders_connect"
 *
 *   const client = createGrpcClient(OrderService)
 *   const order  = await client.placeOrder({ ... })
 *
 * When buf-generated TypeScript files are available under
 * `src/api/grpc/_generated/`, swap the REST-backed hooks in hooks.ts
 * for direct `createPromiseClient` calls using the generated service definitions.
 */
import { createPromiseClient } from "@connectrpc/connect";
import { grpcTransport } from "./transport";
import type { ServiceType } from "@bufbuild/protobuf";

/**
 * Creates a type-safe Connect promise-client for the given service descriptor.
 *
 * @example
 * const orderClient = createGrpcClient(OrderService)
 * await orderClient.placeOrder({ ... })
 */
export function createGrpcClient<T extends ServiceType>(service: T) {
  return createPromiseClient(service, grpcTransport);
}

// Re-export transport for callers that need it directly (e.g. streaming hooks)
export { grpcTransport };
