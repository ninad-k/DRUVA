import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { getStrategy, runBacktest, type BacktestResult } from "@/api/rest/endpoints";
import { formatPct } from "@/utils/format";

const backtestSchema = z.object({
  from: z.string().min(1),
  to: z.string().min(1),
  symbols: z.string().min(1),
  timeframe: z.string().min(1),
});
type BacktestForm = z.infer<typeof backtestSchema>;

export function StrategyDetailPage() {
  const { id } = useParams({ strict: false }) as { id: string };
  const [result, setResult] = useState<BacktestResult | null>(null);

  const { data: strategy, isLoading } = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => getStrategy(id),
    enabled: !!id,
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<BacktestForm>({
    resolver: zodResolver(backtestSchema),
    defaultValues: {
      from: "2024-01-01",
      to: "2024-12-31",
      symbols: "RELIANCE,INFY",
      timeframe: "5m",
    },
  });

  const backtest = useMutation({
    mutationFn: (v: BacktestForm) =>
      runBacktest(id, {
        from: v.from,
        to: v.to,
        symbols: v.symbols.split(",").map((s) => s.trim()).filter(Boolean),
        timeframe: v.timeframe,
      }),
    onSuccess: (r) => {
      setResult(r);
      toast.success("Backtest complete");
    },
    onError: () => toast.error("Backtest failed"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={strategy?.name ?? (isLoading ? "Loading…" : "Strategy")}
        description={strategy ? strategy.strategy_class : ""}
        actions={
          strategy && (
            <div className="flex gap-2">
              <Badge variant={strategy.mode === "live" ? "default" : "outline"}>
                {strategy.mode}
              </Badge>
              {strategy.is_ml && <Badge variant="secondary">ML</Badge>}
            </div>
          )
        }
      />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="parameters">Parameters</TabsTrigger>
          <TabsTrigger value="backtest">Backtest</TabsTrigger>
          <TabsTrigger value="trades">Trades</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardHeader>
              <CardTitle>Overview</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <div>
                <p className="text-xs uppercase text-muted-foreground">Class</p>
                <p className="font-medium">{strategy?.strategy_class ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Mode</p>
                <p className="font-medium capitalize">{strategy?.mode ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Enabled</p>
                <p className="font-medium">{strategy?.enabled ? "Yes" : "No"}</p>
              </div>
              {strategy?.is_ml && (
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Model version</p>
                  <p className="font-medium">{strategy.model_version ?? "—"}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="parameters">
          <Card>
            <CardHeader>
              <CardTitle>Parameters</CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea
                readOnly
                rows={12}
                value={JSON.stringify(strategy?.parameters ?? {}, null, 2)}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="backtest">
          <Card>
            <CardHeader>
              <CardTitle>Run Backtest</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={handleSubmit((v) => backtest.mutate(v))}
                className="grid gap-3 md:grid-cols-5"
              >
                <div>
                  <Label htmlFor="from">From</Label>
                  <Input id="from" type="date" {...register("from")} />
                </div>
                <div>
                  <Label htmlFor="to">To</Label>
                  <Input id="to" type="date" {...register("to")} />
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="symbols">Symbols (comma-separated)</Label>
                  <Input id="symbols" {...register("symbols")} />
                </div>
                <div>
                  <Label htmlFor="timeframe">Timeframe</Label>
                  <Input id="timeframe" placeholder="5m" {...register("timeframe")} />
                </div>
                {(errors.from || errors.to) && (
                  <p className="md:col-span-5 text-xs text-[hsl(var(--loss))]">
                    All fields are required.
                  </p>
                )}
                <div className="md:col-span-5 flex justify-end">
                  <Button type="submit" disabled={backtest.isPending}>
                    {backtest.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                    Run
                  </Button>
                </div>
              </form>

              {result && (
                <div className="mt-6 space-y-4">
                  <div className="grid gap-3 md:grid-cols-6">
                    <Metric label="Return" value={formatPct(result.metrics.total_return_pct ?? 0)} />
                    <Metric label="Sharpe" value={(result.metrics.sharpe ?? 0).toFixed(2)} />
                    <Metric label="Sortino" value={(result.metrics.sortino ?? 0).toFixed(2)} />
                    <Metric
                      label="Max DD"
                      value={formatPct(result.metrics.max_drawdown_pct ?? 0)}
                    />
                    <Metric
                      label="Win rate"
                      value={formatPct((result.metrics.win_rate ?? 0) * 100)}
                    />
                    <Metric label="Trades" value={String(result.metrics.trades ?? 0)} />
                  </div>
                  <Card>
                    <CardHeader>
                      <CardTitle>Equity curve</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <EquityCurveChart
                        data={(result.equity_curve ?? []).map((p) => ({
                          ts: p.ts.slice(0, 10),
                          equity: p.equity,
                        }))}
                        height={260}
                      />
                    </CardContent>
                  </Card>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trades">
          <Card>
            <CardHeader>
              <CardTitle>Trades</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Strategy trade history endpoint not yet wired. Use the Trading page for live orders.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase text-muted-foreground">{label}</p>
        <p className="mt-1 font-mono text-lg font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}
