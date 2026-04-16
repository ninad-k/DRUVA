import { useEffect, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth";

/** Redirects unauthenticated users to /login. */
export function AuthGuard({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!accessToken) {
      void navigate({ to: "/login" });
    }
  }, [accessToken, navigate]);

  if (!accessToken) return null;
  return <>{children}</>;
}
