import { useState, type ReactNode } from "react";
import { Outlet } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { useAccountStore } from "@/store/account";
import { apiMe, listAccounts } from "@/api/rest/endpoints";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { AuthGuard } from "./AuthGuard";

/**
 * Authenticated app shell.
 *
 * - Auth guard redirects to /login if not authenticated.
 * - Loads `/auth/me` and `/accounts` once to populate the auth + account stores.
 * - Renders sidebar + topbar around <Outlet />.
 */
export function Shell({ children }: { children?: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const setUser = useAuthStore((s) => s.setUser);
  const accessToken = useAuthStore((s) => s.accessToken);
  const setActiveAccountId = useAccountStore((s) => s.setActiveAccountId);
  const activeAccountId = useAccountStore((s) => s.activeAccountId);

  useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const u = await apiMe();
      setUser(u);
      return u;
    },
    enabled: !!accessToken,
    staleTime: 5 * 60_000,
  });

  useQuery({
    queryKey: ["accounts-bootstrap"],
    queryFn: async () => {
      const accounts = await listAccounts();
      if (!activeAccountId && accounts.length > 0) {
        setActiveAccountId(accounts[0].id);
      }
      return accounts;
    },
    enabled: !!accessToken,
    staleTime: 60_000,
  });

  return (
    <AuthGuard>
      <div className="flex min-h-screen bg-background text-foreground">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onToggleSidebar={() => setSidebarOpen((v) => !v)} />
          <main className="flex-1 overflow-x-hidden p-4 md:p-6">{children ?? <Outlet />}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
