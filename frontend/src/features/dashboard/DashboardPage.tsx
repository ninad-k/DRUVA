import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  Briefcase,
  LineChart,
  Plus,
  RefreshCw,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EquityCurveChart, type EquityPoint } from "@/components/charts/EquityCurveChart";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getAnalyticsSummary,
  getEquityCurve,
  listOrders,
  syncAccount,
} from "@/api/rest/endpoints";
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

export function DashboardPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();

  const ordersQ = useQuery({
    queryKey: ["dashboard-orders", accountId],
    queryFn: () => listOrders(accountId ? { account_id: accountId } : {}),
    refetchInterval: 15_000,
    enabled: !!accountId,
  });

  const summaryQ = useQuery({
    queryKey: ["analytics-summary", accountId],
    queryFn: () => getAnalyticsSummary(accountId!),
    refetchInterval: 10_000,
    enabled: !!accountId,
  });

  const equityQ = useQuery({
    queryKey: ["analytics-equity-curve", accountId],
    queryFn: () => getEquityCurve(accountId!, 60),
    refetchInterval: 60_000,
    enabled: !!accountId,
  });

  const sync = useMutation({
    mutationFn: () => syncAccount(accountId!),
    onSuccess: (res) => {
      if (res.synced) {
        toast.success(`Synced ${res.positions} positions and ${res.orders} orders`);
      } else {
        toast.info(res.reason ?? "Nothing to sync for this account");
      }
      qc.invalidateQueries({ queryKey: ["analytics-summary", accountId] });
      qc.invalidateQueries({ queryKey: ["analytics-equity-curve", accountId] });
      qc.invalidateQueries({ queryKey: ["dashboard-orders", accountId] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail ?? "Sync failed");
    },
  });

  const equityData: EquityPoint[] = useMemo(
    () =>
      (equityQ.data ?? []).map((p) => ({
        ts: p.ts.slice(5, 10),
        equity: p.equity,
      })),
    [equityQ.data],
  );

  const totalEquity = summaryQ.data?.total_equity ?? 0;
  const dayPnl = summaryQ.data?.day_pnl ?? 0;
  const dayPnlPct = summaryQ.data?.day_pnl_pct ?? 0;
  const openPositions = summaryQ.data?.open_positions ?? 0;
  const activeStrategies = summaryQ.data?.active_strategies ?? 0;
  const totalStrategies = summaryQ.data?.total_strategies ?? 0;

  const recentOrders = (ordersQ.data ?? []).slice(0, 10);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Live view of your accounts, P&L, and strategies."
        actions={
          accountId ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
            >
              <RefreshCw className={`h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
              Sync
            </Button>
          ) : null
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Total Equity"
          value={formatINR(totalEquity, { compact: true })}
          delta={{ value: dayPnlPct, label: `${formatPct(dayPnlPct)} today` }}
          icon={<Wallet className="h-4 w-4" />}
        />
        <KpiCard
          title="Day P&L"
          value={formatSignedINR(dayPnl)}
          delta={{ value: dayPnl, label: formatPct(dayPnlPct) }}
          icon={<LineChart className="h-4 w-4" />}
        />
        <KpiCard
          title="Open Positions"
          value={String(openPositions)}
          icon={<Briefcase className="h-4 w-4" />}
        />
        <KpiCard
          title="Active Strategies"
          value={`${activeStrategies} / ${totalStrategies}`}
          icon={<LineChart className="h-4 w-4" />}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Equity Curve</CardTitle>
        </CardHeader>
        <CardContent>
          {equityQ.isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : equityData.length === 0 ? (
            <EmptyState
              icon={LineChart}
              title={accountId ? "No equity history yet" : "Select an account"}
              description={
                accountId
                  ? "Place trades or run strategies to start building your equity curve."
                  : "Add a broker account from Settings to begin."
              }
            />
          ) : (
            <EquityCurveChart data={equityData} height={280} />
          )}
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
