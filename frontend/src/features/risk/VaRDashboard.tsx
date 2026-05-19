import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatINR } from "@/utils/format";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VaRMetric {
  var_pct: number;
  cvar_pct: number;
  var_inr: number;
  cvar_inr: number;
}

interface PositionContribution {
  symbol: string;
  weight_pct: number;
  var_contribution_pct: number;
  standalone_var_pct: number;
}

interface VaRReport {
  var_95: VaRMetric;
  var_99: VaRMetric;
  cvar_95: VaRMetric;
  cvar_99: VaRMetric;
  position_contributions: PositionContribution[];
  computed_at: string;
}

interface VaRDashboardProps {
  report: VaRReport | null;
  loading?: boolean;
}

// ---------------------------------------------------------------------------
// Risk level helpers
// ---------------------------------------------------------------------------

function getRiskLevel(varPct95: number): "LOW" | "MEDIUM" | "HIGH" {
  if (varPct95 < 1.5) return "LOW";
  if (varPct95 < 3.0) return "MEDIUM";
  return "HIGH";
}

function riskBadgeClass(level: "LOW" | "MEDIUM" | "HIGH"): string {
  switch (level) {
    case "LOW":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "MEDIUM":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "HIGH":
      return "bg-red-500/15 text-red-400 border-red-500/30";
  }
}

// ---------------------------------------------------------------------------
// KPI card
// ---------------------------------------------------------------------------

interface KpiCardProps {
  label: string;
  inr: number;
  pct: number;
  colorClass: string;
}

function KpiCard({ label, inr, pct, colorClass }: KpiCardProps) {
  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardContent className="p-5">
        <p className={`text-xs uppercase tracking-wide font-medium ${colorClass}`}>{label}</p>
        <p className="mt-2 font-mono text-xl font-semibold tabular-nums text-zinc-100">
          {formatINR(inr)}
        </p>
        <p className={`mt-0.5 font-mono text-sm tabular-nums ${colorClass}`}>
          {pct.toFixed(2)}%
        </p>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Skeleton placeholder
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-40 w-full rounded-lg" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function VaRDashboard({ report, loading = false }: VaRDashboardProps) {
  if (loading) {
    return <DashboardSkeleton />;
  }

  if (!report) {
    return (
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="p-8 text-center">
          <p className="text-sm text-zinc-500">
            No VaR report available. Submit a portfolio to compute risk metrics.
          </p>
        </CardContent>
      </Card>
    );
  }

  const riskLevel = getRiskLevel(report.var_95.var_pct);
  const sortedContributions = [...report.position_contributions].sort(
    (a, b) => b.var_contribution_pct - a.var_contribution_pct,
  );
  const topSymbol = sortedContributions[0]?.symbol ?? null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            Portfolio Risk — VaR / CVaR
          </h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            As of {formatDateTime(report.computed_at)}
          </p>
        </div>
        <Badge
          variant="outline"
          className={`px-3 py-1 text-xs font-semibold uppercase tracking-wide ${riskBadgeClass(riskLevel)}`}
        >
          {riskLevel} RISK
        </Badge>
      </div>

      {/* KPI Cards — 2×2 grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <KpiCard
          label="VaR 95%"
          inr={report.var_95.var_inr}
          pct={report.var_95.var_pct}
          colorClass="text-amber-400"
        />
        <KpiCard
          label="CVaR 95% (ES)"
          inr={report.cvar_95.cvar_inr}
          pct={report.cvar_95.cvar_pct}
          colorClass="text-orange-400"
        />
        <KpiCard
          label="VaR 99%"
          inr={report.var_99.var_inr}
          pct={report.var_99.var_pct}
          colorClass="text-red-400"
        />
        <KpiCard
          label="CVaR 99% (ES)"
          inr={report.cvar_99.cvar_inr}
          pct={report.cvar_99.cvar_pct}
          colorClass="text-red-600"
        />
      </div>

      {/* Position Contribution Table */}
      {sortedContributions.length > 0 && (
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-300">
              Position Contribution to VaR (95%)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-xs text-zinc-500">Symbol</TableHead>
                  <TableHead className="text-right text-xs text-zinc-500">
                    Weight %
                  </TableHead>
                  <TableHead className="text-right text-xs text-zinc-500">
                    Standalone VaR %
                  </TableHead>
                  <TableHead className="text-right text-xs text-zinc-500">
                    Portfolio Contribution %
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedContributions.map((pos) => {
                  const isTop = pos.symbol === topSymbol;
                  return (
                    <TableRow
                      key={pos.symbol}
                      className={`border-zinc-800 ${isTop ? "bg-amber-500/5" : "hover:bg-zinc-800/50"}`}
                    >
                      <TableCell
                        className={`font-medium ${isTop ? "text-amber-400" : "text-zinc-200"}`}
                      >
                        {pos.symbol}
                        {isTop && (
                          <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-400">
                            Top
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm tabular-nums text-zinc-300">
                        {pos.weight_pct.toFixed(2)}%
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm tabular-nums text-zinc-300">
                        {pos.standalone_var_pct.toFixed(2)}%
                      </TableCell>
                      <TableCell
                        className={`text-right font-mono text-sm tabular-nums ${
                          isTop ? "text-amber-400 font-semibold" : "text-zinc-300"
                        }`}
                      >
                        {pos.var_contribution_pct.toFixed(2)}%
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
