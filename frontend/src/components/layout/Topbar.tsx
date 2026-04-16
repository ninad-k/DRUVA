import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { LogOut, Menu, Moon, Sun, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useThemeStore } from "@/store/theme";
import { useAuthStore } from "@/store/auth";
import { apiLogout, isMarketOpen } from "@/api/rest/endpoints";
import { InstrumentSearch } from "./InstrumentSearch";
import { cn } from "@/utils/cn";

interface TopbarProps {
  onToggleSidebar: () => void;
}

export function Topbar({ onToggleSidebar }: TopbarProps) {
  const navigate = useNavigate();
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);

  const { data: marketStatus } = useQuery({
    queryKey: ["market-open", "NSE"],
    queryFn: () => isMarketOpen("NSE"),
    refetchInterval: 60_000,
  });

  const logout = async () => {
    try {
      await apiLogout();
    } catch {
      /* ignore */
    } finally {
      clear();
      void navigate({ to: "/login" });
    }
  };

  const isOpen = marketStatus?.is_open ?? false;

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-4 border-b border-border bg-background/95 px-4 backdrop-blur">
      <Button variant="ghost" size="icon" onClick={onToggleSidebar} className="md:hidden">
        <Menu className="h-5 w-5" />
      </Button>

      <InstrumentSearch onSelect={() => navigate({ to: "/trading/orders" })} />

      <div className="ml-auto flex items-center gap-3">
        <div
          className={cn(
            "hidden items-center gap-2 rounded-full border border-border px-3 py-1 text-xs font-medium md:inline-flex",
            isOpen
              ? "border-[hsl(var(--gain))]/40 bg-[hsl(var(--gain))]/10 text-[hsl(var(--gain))]"
              : "border-border bg-muted text-muted-foreground",
          )}
        >
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              isOpen ? "bg-[hsl(var(--gain))]" : "bg-muted-foreground",
            )}
          />
          NSE {isOpen ? "Open" : "Closed"}
        </div>

        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <UserIcon className="h-4 w-4" />
              <span className="hidden sm:inline">{user?.display_name ?? "Account"}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-foreground">
                  {user?.display_name ?? "—"}
                </span>
                <span className="text-xs text-muted-foreground">{user?.email ?? ""}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate({ to: "/settings/accounts" })}>
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-[hsl(var(--loss))]">
              <LogOut className="mr-2 h-4 w-4" /> Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
