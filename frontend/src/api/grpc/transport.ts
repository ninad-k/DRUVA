import { createGrpcWebTransport } from "@bufbuild/connect-web";
import type { Interceptor } from "@bufbuild/connect";

/**
 * gRPC-Web transport pointed at Envoy (which upstreams to our Python gRPC server).
 *
 * Auth interceptor:
 *   - Reads the current access token from the auth store (set via `setAccessToken`).
 *   - Attaches `authorization: Bearer <access>` on every outgoing request.
 *   - On `code: unauthenticated`, the calling code should trigger a refresh via
 *     the REST auth client (single source of truth for token lifecycle).
 */

const baseUrl = import.meta.env.VITE_GRPC_URL ?? "http://localhost:8080";

let accessToken: string | null = null;
export function setGrpcAccessToken(token: string | null) {
  accessToken = token;
}

const authInterceptor: Interceptor = (next) => async (req) => {
  if (accessToken) {
    req.header.set("Authorization", `Bearer ${accessToken}`);
  }
  return next(req);
};

export const grpcTransport = createGrpcWebTransport({
  baseUrl,
  interceptors: [authInterceptor],
});
