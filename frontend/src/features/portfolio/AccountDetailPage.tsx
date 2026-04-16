import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EquityCurveChart, type EquityPoint } from "@/components/charts/EquityCurveChart";
import { Sparkline } from "@/components/charts/Sparkline";
import { listAccounts, listPositions } from "@/api/rest/endpoints";
import { formatINR, formatNumber, formatPct, formatSignedINR, pnlColorClass } from "@/utils/format";

function makeEquity(points = 90): EquityPoint[] {
  const out: EquityPoint[] = [];
  let v = 800_000;
  const now = Date.now();
  for (let i = points - 1; i >= 0; i--) {
    v += (Math.random() - 0.45) * 7_000;
    out.push({ ts: new Date(now - i * 86_400_000).toISOString().slice(5, 10), equity: v });
  }
  return out;
}

function drawdownData(equity: EquityPoint[]): { v: number }[] {
  let peak = -Infinity;
  return equity.map((p) => {
    peak = Math.max(peak, p.equity);
    return { v: ((p.equity - peak) / peak) * 100 };
  });
}

export function AccountDetailPage() {
  const { accountId } = useParams({ strict: false }) as { accountId: string };

  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const positionsQ = useQuery({
    queryKey: ["positions", accountId],
    queryFn: () => listPositions({ account_id: accountId }),
    refetchInterval: 10_000,
  });

  const account = (accountsQ.data ?? []).find((a) => a.id === accountId);
  const equity = useMemo(() => makeEquity(60), []);
  const dd = useMemo(() => drawdownData(equity), [equity]);
  const positions = positionsQ.data ?? [];
  const totalPnl = positions.reduce((acc, p) => acc + (p.pnl ?? 0), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title={account?.display_name ?? "Account"}
        description={account ? `${account.broker} · ${account.is_paper ? "Paper" : "Live"}` : "—"}
      />

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-muted-foreground">Equity</p>
            <p className="mt-2 font-mono text-xl font-semibold">
              {formatINR(equity[equity.length - 1]?.equity ?? 0, { compact: true })}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-muted-foreground">Today's P&L</p>
            <p className={"mt-2 font-mono text-xl font-semibold " + pnlColorClass(totalPnl)}>
              {formatSignedINR(totalPnl)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-muted-foreground">Sharpe</p>
            <p className="mt-2 font-mono text-xl font-semibold">1.42</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-muted-foreground">Sortino</p>
            <p className="mt-2 font-mono text-xl font-semibold">1.81</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Equity Curve</CardTitle>
        </CardHeader>
        <CardContent>
          <EquityCurveChart data={equity} height={260} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Drawdown</CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline data={dd} color="hsl(var(--loss))" height={80} />
            <p className="mt-2 text-xs text-muted-foreground">Max drawdown shown over last 60 days.</p>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            {positions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No holdings.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Avg</TableHead>
                    <TableHead className="text-right">LTP</TableHead>
                    <TableHead className="text-right">P&L</TableHead>
                    <TableHead className="text-right">%</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((p) => (
                    <TableRow key={p.symbol}>
                      <TableCell className="font-medium">{p.symbol}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{p.product}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">{p.quantity}</TableCell>
                      <TableCell className="text-right font-mono">
                        {formatNumber(p.average_price)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatNumber(p.last_price)}
                      </TableCell>
                      <TableCell
                        className={"text-right font-mono " + pnlColorClass(p.pnl)}
                      >
                        {formatINR(p.pnl)}
                      </TableCell>
                      <TableCell
                        className={"text-right font-mono " + pnlColorClass(p.pnl_pct)}
                      >
                        {formatPct(p.pnl_pct)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
