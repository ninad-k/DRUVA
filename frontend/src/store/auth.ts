import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AuthTokens, User } from "@/types/api";
import { setAccessToken } from "@/api/rest/axios";
import { setGrpcAccessToken } from "@/api/grpc/transport";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  user: User | null;
  setSession: (tokens: AuthTokens, user?: User | null) => void;
  setUser: (user: User | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      user: null,
      setSession: (tokens, user) => {
        const expiresAt = Date.now() + tokens.expires_in * 1000;
        setAccessToken(tokens.access_token);
        setGrpcAccessToken(tokens.access_token);
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          expiresAt,
          ...(user !== undefined ? { user } : {}),
        });
      },
      setUser: (user) => set({ user }),
      clear: () => {
        setAccessToken(null);
        setGrpcAccessToken(null);
        set({ accessToken: null, refreshToken: null, expiresAt: null, user: null });
      },
    }),
    {
      name: "dhruva.auth",
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        expiresAt: s.expiresAt,
        user: s.user,
      }),
    },
  ),
);
