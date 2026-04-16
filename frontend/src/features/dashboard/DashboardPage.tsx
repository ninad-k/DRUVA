import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  Briefcase,
  LineChart,
  Plus,
  Wallet,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EquityCurveChart, type EquityPoint } from "@/components/charts/EquityCurveChart";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { listOrders, listPositions, listStrategies } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import { formatDateTime, formatINR, formatPct, formatSignedINR, pnlColorClass } from "@/utils/format";

interface KpiCardProps {
  title: string;
  value: string;
  delta?: { value: number; label: string };
  icon: React.ReactNode;
}

function KpiCard({ title, value, delta, icon }: KpiCardProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
          <div className="grid h-8 w-8 place-items-center rounded-md bg-primary/10 text-primary">
            {icon}
          </div>
        </div>
        <p className="mt-3 font-mono text-2xl font-semibold tabular-nums">{value}</p>
        {delta && (
          <p
            className={
              "mt-1 inline-flex items-center gap-1 font-mono text-xs " +
              pnlColorClass(delta.value)
            }
          >
            {delta.value >= 0 ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : (
              <ArrowDownRight className="h-3 w-3" />
            )}
            {delta.label}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function generateMockEquity(points = 60): EquityPoint[] {
  const out: EquityPoint[] = [];
  let v = 1_000_000;
  const now = Date.now();
  for (let i = points - 1; i >= 0; i--) {
    v += (Math.random() - 0.45) * 8_000;
    out.push({ ts: new Date(now - i * 86_400_000).toISOString().slice(5, 10), equity: v });
  }
  return out;
}

export function DashboardPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);

  const ordersQ = useQuery({
    queryKey: ["dashboard-orders", accountId],
    queryFn: () => listOrders(accountId ? { account_id: accountId } : {}),
    refetchInterval: 15_000,
  });

  const positionsQ = useQuery({
    queryKey: ["dashboard-positions", accountId],
    queryFn: () => listPositions(accountId ? { account_id: accountId } : {}),
    refetchInterval: 10_000,
  });

  const strategiesQ = useQuery({
    queryKey: ["dashboard-strategies", accountId],
    queryFn: () => listStrategies(accountId ? { account_id: accountId } : {}),
  });

  const equityData = useMemo(() => generateMockEquity(60), []);

  const totalPnl = (positionsQ.data ?? []).reduce((acc, p) => acc + (p.pnl ?? 0), 0);
  const openPositions = (positionsQ.data ?? []).length;
  const activeStrategies = (strategiesQ.data ?? []).filter((s) => s.enabled).length;
  const totalEquity = equityData.length ? equityData[equityData.length - 1].equity : 0;

  const recentOrders = (ordersQ.data ?? []).slice(0, 10);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Live view of your accounts, P&L, and strategies."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Total Equity"
          value={formatINR(totalEquity, { compact: true })}
          delta={{ value: 1.42, label: "+1.42% today" }}
          icon={<Wallet className="h-4 w-4" />}
        />
        <KpiCard
          title="Day P&L"
          value={formatSignedINR(totalPnl)}
          delta={{ value: totalPnl, label: formatPct((totalPnl / Math.max(totalEquity, 1)) * 100) }}
          icon={<LineChart className="h-4 w-4" />}
        />
        <KpiCard
          title="Open Positions"
          value={String(openPositions)}
          icon={<Briefcase className="h-4 w-4" />}
        />
        <KpiCard
          title="Active Strategies"
          value={`${activeStrategies} / ${(strategiesQ.data ?? []).length}`}
          icon={<LineChart className="h-4 w-4" />}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Equity Curve</CardTitle>
        </CardHeader>
        <CardContent>
          <EquityCurveChart data={equityData} height={280} />
          <p className="mt-2 text-xs text-muted-foreground">
            Sample data. Live wiring requires the analytics endpoint.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent Orders</CardTitle>
          <Button asChild variant="outline" size="sm">
            <Link to="/trading/orders">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {ordersQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : recentOrders.length === 0 ? (
            <EmptyState
              icon={Plus}
              title="No orders yet"
              description="Place your first order from the Trading page or via a strategy."
              action={{ label: "Go to Trading", onClick: () => (window.location.href = "/trading/orders") }}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentOrders.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="font-medium">{o.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={o.side === "BUY" ? "success" : "destructive"}>
                        {o.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {o.quantity}
                    </TableCell>
                    <TableCell className="text-xs">{o.order_type}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{o.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(o.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
