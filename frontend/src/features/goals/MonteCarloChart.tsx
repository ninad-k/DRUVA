import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, TrendingUp } from "lucide-react";

interface FanDataPoint {
  month: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

interface SimulationResult {
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  probability_of_success: number;
  expected_final_value: number;
  worst_case: number;
  best_case: number;
  horizon_months: number;
  target_corpus: number;
  total_invested: number;
  fan_data: FanDataPoint[];
}

interface Props {
  goalId: string;
  targetCorpus: number;
}

const fmt = (v: number) =>
  v >= 1e7
    ? `₹${(v / 1e7).toFixed(2)}Cr`
    : v >= 1e5
    ? `₹${(v / 1e5).toFixed(2)}L`
    : `₹${v.toFixed(0)}`;

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export function MonteCarloChart({ goalId, targetCorpus }: Props) {
  const [params, setParams] = useState({
    annual_return_pct: 12,
    annual_volatility_pct: 18,
    sip_step_up_pct: 10,
    n_simulations: 1000,
    regime_return_adj_pct: 0,
  });
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSimulation = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/goals/${goalId}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error(await res.text());
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setLoading(false);
    }
  };

  // Downsample fan_data to max 60 points for chart performance
  const chartData = result
    ? result.fan_data.filter((_, i) => i % Math.max(1, Math.floor(result.fan_data.length / 60)) === 0)
    : [];

  const successColor =
    result && result.probability_of_success >= 0.75
      ? "text-green-500"
      : result && result.probability_of_success >= 0.5
      ? "text-amber-500"
      : "text-red-500";

  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <TrendingUp className="h-4 w-4 text-amber-500" />
          Monte Carlo Goal Projection
        </CardTitle>
        {result && (
          <Badge variant="outline" className={`text-xs font-mono ${successColor}`}>
            {pct(result.probability_of_success)} success
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Parameter inputs */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Expected return %</Label>
            <Input
              type="number"
              value={params.annual_return_pct}
              onChange={(e) =>
                setParams((p) => ({ ...p, annual_return_pct: +e.target.value }))
              }
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Volatility %</Label>
            <Input
              type="number"
              value={params.annual_volatility_pct}
              onChange={(e) =>
                setParams((p) => ({ ...p, annual_volatility_pct: +e.target.value }))
              }
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">SIP step-up %</Label>
            <Input
              type="number"
              value={params.sip_step_up_pct}
              onChange={(e) =>
                setParams((p) => ({ ...p, sip_step_up_pct: +e.target.value }))
              }
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Regime adj %</Label>
            <Input
              type="number"
              value={params.regime_return_adj_pct}
              onChange={(e) =>
                setParams((p) => ({ ...p, regime_return_adj_pct: +e.target.value }))
              }
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Simulations</Label>
            <Input
              type="number"
              value={params.n_simulations}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  n_simulations: Math.min(5000, +e.target.value),
                }))
              }
              className="h-8 text-sm"
            />
          </div>
        </div>

        <Button onClick={runSimulation} disabled={loading} size="sm" className="w-full sm:w-auto">
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Running {params.n_simulations.toLocaleString()} paths…
            </>
          ) : (
            "Run Simulation"
          )}
        </Button>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {/* Fan chart */}
        {result && chartData.length > 0 && (
          <>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="p90fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="p75fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="p50fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.1} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="month"
                  tickFormatter={(v: number) => `${Math.round(v / 12)}y`}
                  className="text-xs text-muted-foreground"
                />
                <YAxis
                  tickFormatter={fmt}
                  width={70}
                  className="text-xs text-muted-foreground"
                />
                <Tooltip
                  formatter={(v: number) => fmt(v)}
                  labelFormatter={(l: number) => `Month ${l} (${(l / 12).toFixed(1)}y)`}
                />
                {/* Outer band: p10–p90 */}
                <Area
                  type="monotone"
                  dataKey="p90"
                  stroke="#f59e0b"
                  strokeWidth={1}
                  strokeDasharray="4 2"
                  fill="url(#p90fill)"
                  name="P90 (best)"
                />
                {/* Inner band: p25–p75 */}
                <Area
                  type="monotone"
                  dataKey="p75"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  fill="url(#p75fill)"
                  name="P75"
                />
                {/* Median */}
                <Area
                  type="monotone"
                  dataKey="p50"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  fill="url(#p50fill)"
                  name="P50 (median)"
                />
                <Area
                  type="monotone"
                  dataKey="p25"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  fill="none"
                  name="P25"
                />
                <Area
                  type="monotone"
                  dataKey="p10"
                  stroke="#f59e0b"
                  strokeWidth={1}
                  strokeDasharray="4 2"
                  fill="none"
                  name="P10 (worst)"
                />
                {/* Target corpus reference line */}
                <ReferenceLine
                  y={targetCorpus}
                  stroke="#ef4444"
                  strokeDasharray="6 3"
                  label={{ value: "Target", fill: "#ef4444", fontSize: 11, position: "right" }}
                />
              </AreaChart>
            </ResponsiveContainer>

            {/* Summary row */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-center">
              {[
                { label: "Worst (P10)", value: fmt(result.p10) },
                { label: "Median (P50)", value: fmt(result.p50) },
                { label: "Best (P90)", value: fmt(result.p90) },
                { label: "Total invested", value: fmt(result.total_invested) },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-md border p-2">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
                    {label}
                  </div>
                  <div className="text-sm font-semibold font-mono mt-0.5">{value}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
