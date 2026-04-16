import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { cancelOrder, listOrders } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import { OrderTicket } from "./OrderTicket";
import { formatDateTime, formatNumber } from "@/utils/format";
import type { OrderStatus } from "@/types/api";

const STATUSES: ("ALL" | OrderStatus)[] = [
  "ALL",
  "PENDING",
  "OPEN",
  "COMPLETE",
  "CANCELLED",
  "REJECTED",
  "TRIGGER_PENDING",
];

export function OrdersPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<"ALL" | OrderStatus>("ALL");
  const [sideFilter, setSideFilter] = useState<"ALL" | "BUY" | "SELL">("ALL");
  const [ticketOpen, setTicketOpen] = useState(false);

  const { data: orders = [], isLoading } = useQuery({
    queryKey: ["orders", accountId],
    queryFn: () => listOrders(accountId ? { account_id: accountId } : {}),
    refetchInterval: 3_000,
  });

  const cancelMut = useMutation({
    mutationFn: (id: string) => cancelOrder(id),
    onSuccess: () => {
      toast.success("Order cancelled");
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: () => toast.error("Failed to cancel order"),
  });

  const filtered = useMemo(() => {
    return orders.filter(
      (o) =>
        (statusFilter === "ALL" || o.status === statusFilter) &&
        (sideFilter === "ALL" || o.side === sideFilter),
    );
  }, [orders, statusFilter, sideFilter]);

  const cancellable = (s: OrderStatus) =>
    s === "OPEN" || s === "PENDING" || s === "TRIGGER_PENDING";

  return (
    <div className="space-y-5">
      <PageHeader
        title="Orders"
        description="Live order book — cancel, modify, or place new."
        actions={
          <Button onClick={() => setTicketOpen(true)}>
            <Plus className="h-4 w-4" /> New Order
          </Button>
        }
      />

      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            <div className="w-40">
              <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-32">
              <Select value={sideFilter} onValueChange={(v) => setSideFilter(v as typeof sideFilter)}>
                <SelectTrigger>
                  <SelectValue placeholder="Side" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All sides</SelectItem>
                  <SelectItem value="BUY">Buy</SelectItem>
                  <SelectItem value="SELL">Sell</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <span className="ml-auto self-center text-xs text-muted-foreground">
              {filtered.length} of {orders.length}
            </span>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Plus}
              title="No matching orders"
              description="Adjust filters or place a new order."
              action={{ label: "New Order", onClick: () => setTicketOpen(true) }}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="font-medium">
                      {o.symbol}
                      <span className="ml-1 text-xs text-muted-foreground">{o.exchange}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={o.side === "BUY" ? "success" : "destructive"}>
                        {o.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {o.filled_quantity ?? 0}/{o.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {o.price ? formatNumber(o.price) : "—"}
                    </TableCell>
                    <TableCell className="text-xs">{o.order_type}</TableCell>
                    <TableCell className="text-xs">{o.product}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{o.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(o.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {cancellable(o.status) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelMut.mutate(o.id)}
                          disabled={cancelMut.isPending}
                        >
                          <X className="h-3 w-3" /> Cancel
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <OrderTicket open={ticketOpen} onOpenChange={setTicketOpen} />
    </div>
  );
}
