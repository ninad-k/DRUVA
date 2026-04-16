import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Briefcase, ChevronRight, Wallet } from "lucide-react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/EmptyState";
import { Sparkline } from "@/components/charts/Sparkline";
import { listAccounts, listPositions } from "@/api/rest/endpoints";
import { formatINR, formatPct, formatSignedINR, pnlColorClass } from "@/utils/format";

const COLORS = [
  "hsl(var(--primary))",
  "#3b82f6",
  "#22c55e",
  "#a855f7",
  "#ec4899",
  "#f97316",
  "#14b8a6",
];

function mockSparkline(seed: number, points = 20) {
  const out: { v: number }[] = [];
  let v = 100 + seed;
  for (let i = 0; i < points; i++) {
    v += (Math.random() - 0.45) * 5;
    out.push({ v });
  }
  return out;
}

export function PortfolioPage() {
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const positionsQ = useQuery({
    queryKey: ["positions-all"],
    queryFn: () => listPositions(),
    refetchInterval: 10_000,
  });

  const totalEquity = 1_245_000;
  const totalPnl = (positionsQ.data ?? []).reduce((acc, p) => acc + (p.pnl ?? 0), 0);
  const sectorData = useMemo(() => {
    // Mock sector aggregation since the backend doesn't expose it directly yet.
    const groups: Record<string, number> = {};
    (positionsQ.data ?? []).forEach((p) => {
      const symbolPrefix = p.symbol.slice(0, 3);
      groups[symbolPrefix] = (groups[symbolPrefix] ?? 0) + Math.abs(p.quantity * p.last_price);
    });
    const entries = Object.entries(groups);
    if (entries.length === 0) {
      return [
        { name: "Banks", value: 38 },
        { name: "IT", value: 22 },
        { name: "Energy", value: 16 },
        { name: "Auto", value: 12 },
        { name: "FMCG", value: 12 },
      ];
    }
    return entries.map(([name, value]) => ({ name, value }));
  }, [positionsQ.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Portfolio"
        description="Aggregate view across all connected broker accounts."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Total Equity</p>
            <p className="mt-2 font-mono text-2xl font-semibold">
              {formatINR(totalEquity, { compact: true })}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Today's P&L</p>
            <p className={"mt-2 font-mono text-2xl font-semibold " + pnlColorClass(totalPnl)}>
              {formatSignedINR(totalPnl)}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatPct((totalPnl / Math.max(totalEquity, 1)) * 100)} of equity
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">All-time P&L</p>
            <p className="mt-2 font-mono text-2xl font-semibold text-[hsl(var(--gain))]">
              {formatSignedINR(totalPnl + 124_500)}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Accounts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {accountsQ.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (accountsQ.data ?? []).length === 0 ? (
              <EmptyState
                icon={Wallet}
                title="No accounts yet"
                description="Connect a broker account to start trading."
                action={{
                  label: "Add Account",
                  onClick: () => (window.location.href = "/settings/accounts"),
                }}
              />
            ) : (
              accountsQ.data!.map((a, i) => (
                <Link
                  key={a.id}
                  to="/portfolio/$accountId"
                  params={{ accountId: a.id }}
                  className="flex items-center gap-4 rounded-md border border-border bg-card/50 p-3 transition-colors hover:border-primary/40"
                >
                  <div className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 text-primary">
                    <Briefcase className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {a.display_name}{" "}
                      <span className="text-xs text-muted-foreground">
                        ({a.broker})
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {a.is_paper ? "Paper" : "Live"} ·{" "}
                      {a.is_connected ? "Connected" : "Disconnected"}
                    </p>
                  </div>
                  <div className="hidden w-32 sm:block">
                    <Sparkline data={mockSparkline(i * 7)} />
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </Link>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sector Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sectorData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                  >
                    {sectorData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "0.5rem",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1 text-xs">
              {sectorData.map((s, i) => (
                <div key={s.name} className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  />
                  <span className="truncate text-muted-foreground">{s.name}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
