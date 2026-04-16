import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Briefcase } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { closePosition, listPositions } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import {
  formatINR,
  formatNumber,
  formatPct,
  formatSignedINR,
  pnlColorClass,
} from "@/utils/format";
import type { Position } from "@/types/api";

export function PositionsPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();
  const [closeTarget, setCloseTarget] = useState<Position | null>(null);

  const { data: positions = [], isLoading } = useQuery({
    queryKey: ["positions", accountId],
    queryFn: () => listPositions(accountId ? { account_id: accountId } : {}),
    refetchInterval: 5_000,
  });

  const closeMut = useMutation({
    mutationFn: (p: Position) => closePosition(p.account_id, p.symbol),
    onSuccess: () => {
      toast.success("Position close order submitted");
      qc.invalidateQueries({ queryKey: ["positions"] });
      setCloseTarget(null);
    },
    onError: () => toast.error("Failed to close position"),
  });

  const totalPnl = positions.reduce((acc, p) => acc + (p.pnl ?? 0), 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Positions"
        description={`Net P&L: ${formatSignedINR(totalPnl)}`}
      />

      <Card>
        <CardContent className="p-4">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : positions.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No open positions"
              description="Place an order or run a strategy to see positions here."
            />
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
                  <TableHead className="text-right">Change</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((p) => (
                  <TableRow key={`${p.account_id}-${p.symbol}`}>
                    <TableCell className="font-medium">
                      {p.symbol}
                      <span className="ml-1 text-xs text-muted-foreground">{p.exchange}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{p.product}</Badge>
                    </TableCell>
                    <TableCell
                      className={
                        "text-right font-mono tabular-nums " +
                        (p.quantity < 0 ? "text-[hsl(var(--loss))]" : "")
                      }
                    >
                      {p.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(p.average_price)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(p.last_price)}
                    </TableCell>
                    <TableCell
                      className={"text-right font-mono tabular-nums " + pnlColorClass(p.pnl)}
                    >
                      {formatINR(p.pnl)}
                    </TableCell>
                    <TableCell
                      className={"text-right font-mono tabular-nums " + pnlColorClass(p.pnl_pct)}
                    >
                      {formatPct(p.pnl_pct)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setCloseTarget(p)}
                      >
                        Close
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!closeTarget}
        onOpenChange={(v) => !v && setCloseTarget(null)}
        title={`Close ${closeTarget?.symbol ?? ""}?`}
        description={`This will submit a market order to flatten ${
          closeTarget?.quantity ?? 0
        } units of ${closeTarget?.symbol ?? ""}.`}
        confirmLabel="Close position"
        destructive
        busy={closeMut.isPending}
        onConfirm={() => closeTarget && closeMut.mutate(closeTarget)}
      />
    </div>
  );
}
