import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ShieldAlert, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  approveApproval,
  listApprovals,
  rejectApproval,
} from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import { formatNumber } from "@/utils/format";

export function ApprovalsCard() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();

  const { data = [] } = useQuery({
    queryKey: ["approvals", accountId, "pending"],
    queryFn: () =>
      listApprovals({ account_id: accountId ?? undefined, status: "pending" }),
    refetchInterval: 5_000,
  });

  const approve = useMutation({
    mutationFn: (id: string) => approveApproval(id),
    onSuccess: () => {
      toast.success("Approved");
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: () => toast.error("Failed to approve"),
  });

  const reject = useMutation({
    mutationFn: (id: string) => rejectApproval(id),
    onSuccess: () => {
      toast.success("Rejected");
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: () => toast.error("Failed to reject"),
  });

  if (data.length === 0) return null;

  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardHeader className="flex flex-row items-center gap-2">
        <ShieldAlert className="h-5 w-5 text-primary" />
        <CardTitle>Pending Approvals ({data.length})</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {data.map((a) => (
          <div
            key={a.id}
            className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card/60 p-3"
          >
            <div className="flex-1">
              <p className="text-sm font-medium">
                {a.strategy_name ?? "Strategy"} ·{" "}
                <Badge variant={a.side === "BUY" ? "success" : "destructive"} className="ml-1">
                  {a.side}
                </Badge>{" "}
                <span className="font-mono">
                  {a.quantity} × {a.symbol}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                {a.order_type}
                {a.price != null && ` @ ${formatNumber(a.price)}`}
              </p>
            </div>
            <Button
              size="sm"
              variant="default"
              onClick={() => approve.mutate(a.id)}
              disabled={approve.isPending}
            >
              <Check className="h-3 w-3" /> Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => reject.mutate(a.id)}
              disabled={reject.isPending}
            >
              <X className="h-3 w-3" /> Reject
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
