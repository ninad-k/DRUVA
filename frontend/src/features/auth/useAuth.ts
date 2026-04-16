import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  registerAuthFailureHandler,
  registerRefreshFn,
  setAccessToken,
} from "@/api/rest/axios";
import { setGrpcAccessToken } from "@/api/grpc/transport";
import { useAuthStore } from "@/store/auth";
import { apiRefresh } from "@/api/rest/endpoints";

/**
 * Wires the auth store into the axios + grpc transports.
 *
 * Mount this once at the app root so:
 * - Access token from persisted store is set on the axios instance.
 * - 401s trigger silent refresh using the persisted refresh token.
 * - Refresh failure clears state and redirects to /login.
 */
export function useAuthBootstrap() {
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const setSession = useAuthStore((s) => s.setSession);
  const clear = useAuthStore((s) => s.clear);

  useEffect(() => {
    setAccessToken(accessToken);
    setGrpcAccessToken(accessToken);
  }, [accessToken]);

  useEffect(() => {
    registerRefreshFn(async () => {
      const rt = useAuthStore.getState().refreshToken;
      if (!rt) return null;
      try {
        const tokens = await apiRefresh(rt);
        setSession(tokens);
        return tokens.access_token;
      } catch {
        clear();
        return null;
      }
    });

    registerAuthFailureHandler(() => {
      clear();
      toast.error("Session expired. Please log in again.");
      void navigate({ to: "/login" });
    });
  }, [setSession, clear, navigate]);

  return { isAuthenticated: !!accessToken && !!refreshToken };
}
