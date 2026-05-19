/**
 * GreeksDashboard — real-time portfolio Greeks across all open option positions.
 *
 * Shows:
 *  - Summary row: Net Delta, Gamma, Theta (daily), Vega
 *  - Per-position table with all greeks and unrealised P&L
 *  - Greeks Risk Level badge: Safe / Warning / Danger
 */

import { useMemo } from "react";
import { AlertTriangle, CheckCircle2, ShieldAlert, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ─── Public types ──────────────────────────────────────────────────────────

export interface OptionPosition {
  /** Internal position identifier */
  id: string;
  /** NSE tradingsymbol, e.g. "NIFTY24JAN25000CE" */
  symbol: string;
  /** Strike price in ₹ */
  strike: number;
  /** Option type */
  optionType: "CE" | "PE";
  /** Expiry date as ISO string "YYYY-MM-DD" */
  expiry: string;
  /** Signed quantity (positive = long, negative = short) */
  quantity: number;
  /** Entry price per unit */
  entryPrice: number;
  /** Current market price per unit */
  currentPrice: number;
  /** Black-Scholes delta (per unit, signed by position) */
  delta: number;
  /** Black-Scholes gamma (per unit) */
  gamma: number;
  /** Black-Scholes theta per calendar day (per unit, usually negative) */
  theta: number;
  /** Black-Scholes vega per 1% vol move (per unit) */
  vega: number;
  /** Lot size for position-level calculations */
  lotSize: number;
}

export interface GreeksDashboardProps {
  positions: OptionPosition[];
}

// ─── Risk limits (for badge colouring) ────────────────────────────────────

const RISK_LIMITS = {
  /** Absolute net delta beyond which we warn */
  deltaWarn: 0.5,
  deltaDanger: 1.0,
  /** Absolute net gamma beyond which we warn */
  gammaWarn: 0.02,
  gammaDanger: 0.05,
  /** Daily theta loss beyond which we warn (negative) */
  thetaWarn: -500,
  thetaDanger: -1500,
  /** Net vega beyond which we warn */
  vegaWarn: 500,
  vegaDanger: 1500,
} as const;

// ─── Formatting helpers ────────────────────────────────────────────────────

function fmt2(n: number): string {
  return n.toFixed(4);
}

function fmtPnl(n: number): string {
  const abs = Math.abs(n).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return n >= 0 ? `+₹${abs}` : `-₹${abs}`;
}

function pnlClass(n: number): string {
  if (n > 0) return "text-[hsl(var(--gain))]";
  if (n < 0) return "text-[hsl(var(--loss))]";
  return "text-muted-foreground";
}

// ─── Per-position computed values ──────────────────────────────────────────

interface PositionGreeks {
  netDelta: number;
  netGamma: number;
  netTheta: number;
  netVega: number;
  unrealisedPnl: number;
}

function positionGreeks(p: OptionPosition): PositionGreeks {
  const units = p.quantity * p.lotSize;
  return {
    netDelta: p.delta * units,
    netGamma: p.gamma * units,
    netTheta: p.theta * units,
    netVega: p.vega * units,
    unrealisedPnl: (p.currentPrice - p.entryPrice) * units,
  };
}

// ─── Risk level classification ─────────────────────────────────────────────

type RiskLevel = "Safe" | "Warning" | "Danger";

function classifyRisk(
  totalDelta: number,
  totalGamma: number,
  totalTheta: number,
  totalVega: number,
): RiskLevel {
  const absDelta = Math.abs(totalDelta);
  const absGamma = Math.abs(totalGamma);
  const absVega = Math.abs(totalVega);

  const isDanger =
    absDelta >= RISK_LIMITS.deltaDanger ||
    absGamma >= RISK_LIMITS.gammaDanger ||
    totalTheta <= RISK_LIMITS.thetaDanger ||
    absVega >= RISK_LIMITS.vegaDanger;

  if (isDanger) return "Danger";

  const isWarning =
    absDelta >= RISK_LIMITS.deltaWarn ||
    absGamma >= RISK_LIMITS.gammaWarn ||
    totalTheta <= RISK_LIMITS.thetaWarn ||
    absVega >= RISK_LIMITS.vegaWarn;

  if (isWarning) return "Warning";

  return "Safe";
}

// ─── Sub-components ────────────────────────────────────────────────────────

interface SummaryKpiProps {
  label: string;
  value: string;
  valueClassName?: string;
  sub?: string;
}

function SummaryKpi({ label, value, valueClassName, sub }: SummaryKpiProps) {
  return (
    <div className="rounded-md border border-border bg-zinc-900/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-semibold ${valueClassName ?? "text-foreground"}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

interface RiskBadgeProps {
  level: RiskLevel;
}

function RiskBadge({ level }: RiskBadgeProps) {
  if (level === "Safe") {
    return (
      <Badge variant="success" className="gap-1 text-xs">
        <CheckCircle2 className="h-3 w-3" />
        Greeks Safe
      </Badge>
    );
  }
  if (level === "Warning") {
    return (
      <Badge variant="warning" className="gap-1 text-xs">
        <AlertTriangle className="h-3 w-3" />
        Greeks Warning
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="gap-1 text-xs">
      <ShieldAlert className="h-3 w-3" />
      Greeks Danger
    </Badge>
  );
}

// ─── Delta display helper ──────────────────────────────────────────────────

function DeltaCell({ value }: { value: number }) {
  let cls = "text-foreground";
  if (value > 0.5) cls = "text-[hsl(var(--gain))]";
  else if (value < -0.5) cls = "text-[hsl(var(--loss))]";
  return <span className={`font-mono ${cls}`}>{fmt2(value)}</span>;
}

function ThetaCell({ value }: { value: number }) {
  // Theta is always shown in red (it represents decay)
  return <span className="font-mono text-[hsl(var(--loss))]">{fmt2(value)}</span>;
}

function VegaCell({ value }: { value: number }) {
  const cls = value >= 0 ? "text-blue-400" : "text-[hsl(var(--loss))]";
  return <span className={`font-mono ${cls}`}>{fmt2(value)}</span>;
}

// ─── Main component ────────────────────────────────────────────────────────

/**
 * GreeksDashboard renders portfolio-level Greek summaries and a per-position
 * breakdown table with P&L and risk classification.
 */
export function GreeksDashboard({ positions }: GreeksDashboardProps) {
  const computed = useMemo(() => positions.map((p) => ({ pos: p, g: positionGreeks(p) })), [positions]);

  const totals = useMemo(() => {
    return computed.reduce(
      (acc, { g }) => ({
        delta: acc.delta + g.netDelta,
        gamma: acc.gamma + g.netGamma,
        theta: acc.theta + g.netTheta,
        vega: acc.vega + g.netVega,
        pnl: acc.pnl + g.unrealisedPnl,
      }),
      { delta: 0, gamma: 0, theta: 0, vega: 0, pnl: 0 },
    );
  }, [computed]);

  const riskLevel = useMemo(
    () => classifyRisk(totals.delta, totals.gamma, totals.theta, totals.vega),
    [totals],
  );

  if (positions.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <TrendingDown className="mb-3 h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-muted-foreground">No open option positions</p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            Greeks will appear here once you have open contracts.
          </p>
        </CardContent>
      </Card>
    );
  }

  const netDeltaClass =
    totals.delta > 0.5
      ? "text-[hsl(var(--gain))]"
      : totals.delta < -0.5
        ? "text-[hsl(var(--loss))]"
        : "text-foreground";

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Portfolio Greeks</h2>
          <p className="text-xs text-muted-foreground">
            {positions.length} open position{positions.length !== 1 ? "s" : ""}
          </p>
        </div>
        <RiskBadge level={riskLevel} />
      </div>

      {/* ── Summary KPIs ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryKpi
          label="Net Delta"
          value={fmt2(totals.delta)}
          valueClassName={netDeltaClass}
          sub="Directional exposure"
        />
        <SummaryKpi
          label="Net Gamma"
          value={fmt2(totals.gamma)}
          sub="Delta sensitivity / ₹"
        />
        <SummaryKpi
          label="Daily Theta"
          value={fmtPnl(totals.theta)}
          valueClassName="text-[hsl(var(--loss))]"
          sub="Daily time decay"
        />
        <SummaryKpi
          label="Net Vega"
          value={fmt2(totals.vega)}
          valueClassName={totals.vega >= 0 ? "text-blue-400" : "text-[hsl(var(--loss))]"}
          sub="Sensitivity to 1% vol"
        />
      </div>

      {/* ── Total P&L strip ── */}
      <div className="flex items-center gap-2 rounded-md border border-border bg-zinc-900/40 px-4 py-2.5">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Total Unrealised P&amp;L
        </span>
        <span className={`ml-auto font-mono text-sm font-semibold ${pnlClass(totals.pnl)}`}>
          {fmtPnl(totals.pnl)}
        </span>
      </div>

      {/* ── Per-position table ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Position Detail</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead className="text-right">Strike</TableHead>
                <TableHead className="text-center">Type</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Delta</TableHead>
                <TableHead className="text-right">Gamma</TableHead>
                <TableHead className="text-right">Theta/day</TableHead>
                <TableHead className="text-right">Vega/1%</TableHead>
                <TableHead className="text-right">Unr. P&amp;L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {computed.map(({ pos, g }) => (
                <TableRow key={pos.id}>
                  <TableCell className="font-mono text-xs">{pos.symbol}</TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {pos.strike.toLocaleString("en-IN")}
                  </TableCell>
                  <TableCell className="text-center">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                        pos.optionType === "CE"
                          ? "bg-[hsl(var(--gain))]/15 text-[hsl(var(--gain))]"
                          : "bg-[hsl(var(--loss))]/15 text-[hsl(var(--loss))]"
                      }`}
                    >
                      {pos.optionType}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{pos.quantity}</TableCell>
                  <TableCell className="text-right text-xs">
                    <DeltaCell value={g.netDelta} />
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs text-foreground">
                    {fmt2(g.netGamma)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    <ThetaCell value={g.netTheta} />
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    <VegaCell value={g.netVega} />
                  </TableCell>
                  <TableCell className={`text-right font-mono text-xs font-medium ${pnlClass(g.unrealisedPnl)}`}>
                    {fmtPnl(g.unrealisedPnl)}
                  </TableCell>
                </TableRow>
              ))}

              {/* ── Totals footer row ── */}
              <TableRow className="border-t-2 border-border font-semibold">
                <TableCell colSpan={4} className="text-xs text-muted-foreground">
                  Portfolio Total
                </TableCell>
                <TableCell className="text-right text-xs">
                  <DeltaCell value={totals.delta} />
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {fmt2(totals.gamma)}
                </TableCell>
                <TableCell className="text-right text-xs">
                  <ThetaCell value={totals.theta} />
                </TableCell>
                <TableCell className="text-right text-xs">
                  <VegaCell value={totals.vega} />
                </TableCell>
                <TableCell className={`text-right font-mono text-xs font-semibold ${pnlClass(totals.pnl)}`}>
                  {fmtPnl(totals.pnl)}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
