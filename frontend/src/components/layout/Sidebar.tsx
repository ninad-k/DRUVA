import { Link, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Briefcase,
  CandlestickChart,
  FileText,
  LayoutDashboard,
  LineChart,
  Radar,
  Settings,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/utils/cn";

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  match?: string[];
}

const NAV: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
  { label: "Trading", to: "/trading/orders", icon: TrendingUp, match: ["/trading"] },
  { label: "Portfolio", to: "/portfolio", icon: Briefcase, match: ["/portfolio"] },
  { label: "Strategies", to: "/strategies", icon: LineChart, match: ["/strategies"] },
  { label: "Scanner", to: "/scanner", icon: Radar },
  { label: "Options", to: "/options", icon: CandlestickChart },
  { label: "Reports", to: "/reports", icon: FileText },
  { label: "Settings", to: "/settings/accounts", icon: Settings, match: ["/settings"] },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const path = useRouterState({ select: (s) => s.location.pathname });

  const isActive = (item: NavItem) => {
    if (item.match) return item.match.some((p) => path.startsWith(p));
    return path === item.to || path.startsWith(item.to);
  };

  return (
    <>
      {/* mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-60 transform border-r border-border bg-card transition-transform md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center gap-2 border-b border-border px-5">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-primary font-bold text-primary-foreground">
            <BarChart3 className="h-4 w-4" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold">DHRUVA</p>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Algo Trading
            </p>
          </div>
        </div>
        <nav className="space-y-1 p-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = isActive(item);
            return (
              <Link
                key={item.to}
                to={item.to as never}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
