import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LineChart, Plus } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { Sparkline } from "@/components/charts/Sparkline";
import {
  disableStrategy,
  enableStrategy,
  listStrategies,
} from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import { formatPct, formatSignedINR, pnlColorClass } from "@/utils/format";
import { NewStrategyDialog } from "./NewStrategyDialog";
import { ApprovalsCard } from "./ApprovalsCard";

function pnlSpark(history?: { ts: string; equity: number }[]) {
  if (!history || history.length === 0) {
    return Array.from({ length: 12 }).map((_, i) => ({ v: 100 + Math.sin(i / 2) * 8 }));
  }
  return history.map((p) => ({ v: p.equity }));
}

export function StrategiesListPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ["strategies", accountId],
    queryFn: () => listStrategies(accountId ? { account_id: accountId } : {}),
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, enable }: { id: string; enable: boolean }) =>
      enable ? enableStrategy(id) : disableStrategy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
    onError: () => toast.error("Failed to toggle strategy"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Strategies"
        description="Rule-based and ML strategies. Toggle paper/live and review approvals."
        actions={
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" /> New Strategy
          </Button>
        }
      />

      <ApprovalsCard />

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full" />
          ))}
        </div>
      ) : strategies.length === 0 ? (
        <EmptyState
          icon={LineChart}
          title="No strategies yet"
          description="Create your first strategy. We recommend starting with paper mode."
          action={{ label: "New Strategy", onClick: () => setDialogOpen(true) }}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {strategies.map((s) => (
            <Card key={s.id} className="transition-colors hover:border-primary/40">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link
                      to="/strategies/$id"
                      params={{ id: s.id }}
                      className="block truncate text-base font-semibold hover:text-primary"
                    >
                      {s.name}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">{s.strategy_class}</p>
                  </div>
                  <Switch
                    checked={s.enabled}
                    onCheckedChange={(v) => toggleMut.mutate({ id: s.id, enable: v })}
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <Badge variant={s.mode === "live" ? "default" : "outline"}>{s.mode}</Badge>
                  {s.is_ml && <Badge variant="secondary">ML</Badge>}
                  {s.requires_approval && <Badge variant="warning">Approval</Badge>}
                </div>
                <div className="mt-3">
                  <Sparkline data={pnlSpark(s.pnl_history)} height={36} />
                </div>
                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">P&L</p>
                    <p className={"font-mono text-lg " + pnlColorClass(s.pnl ?? 0)}>
                      {formatSignedINR(s.pnl ?? 0)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">Win rate</p>
                    <p className="font-mono">
                      {s.win_rate != null ? formatPct(s.win_rate * 100) : "—"}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <NewStrategyDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
