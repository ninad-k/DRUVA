import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listScannerResults } from "@/api/rest/endpoints";
import { OrderTicket } from "@/features/trading/OrderTicket";
import { formatNumber, formatPct, pnlColorClass } from "@/utils/format";

const PATTERNS = ["ALL", "BREAKOUT", "REVERSAL", "GAP_UP", "VOL_SPIKE", "ORB"];

export function ScannerPage() {
  const [pattern, setPattern] = useState<string>("ALL");
  const [minScore, setMinScore] = useState<number>(0);
  const [ticketDefaults, setTicketDefaults] = useState<
    | { symbol: string; exchange: string }
    | null
  >(null);

  const { data = [], isLoading } = useQuery({
    queryKey: ["scanner", pattern, minScore],
    queryFn: () =>
      listScannerResults({
        pattern: pattern === "ALL" ? undefined : pattern,
        min_score: minScore || undefined,
      }),
    refetchInterval: 30_000,
  });

  const sorted = useMemo(
    () => [...data].sort((a, b) => b.setup_score - a.setup_score),
    [data],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Scanner"
        description="Pre-market and intraday setup scans across NSE/BSE."
      />

      <Card>
        <CardContent className="p-4">
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="w-44">
              <Label>Pattern</Label>
              <Select value={pattern} onValueChange={setPattern}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PATTERNS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-32">
              <Label htmlFor="min-score">Min score</Label>
              <Input
                id="min-score"
                type="number"
                min="0"
                max="100"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value) || 0)}
              />
            </div>
            <span className="ml-auto text-xs text-muted-foreground">
              {sorted.length} results
            </span>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={Radar}
              title="No setups detected"
              description="The scanner will populate as patterns trigger throughout the session."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pattern</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead className="text-right">LTP</TableHead>
                  <TableHead className="text-right">Change</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((r, i) => (
                  <TableRow key={`${r.symbol}-${i}`}>
                    <TableCell>
                      <Badge variant="secondary">{r.pattern}</Badge>
                    </TableCell>
                    <TableCell className="font-medium">
                      {r.symbol}
                      <span className="ml-1 text-xs text-muted-foreground">{r.exchange}</span>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {r.setup_score.toFixed(1)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatNumber(r.last_price)}
                    </TableCell>
                    <TableCell
                      className={
                        "text-right font-mono tabular-nums " + pnlColorClass(r.change_pct)
                      }
                    >
                      {formatPct(r.change_pct)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setTicketDefaults({ symbol: r.symbol, exchange: r.exchange })
                        }
                      >
                        Quick Order
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <OrderTicket
        open={!!ticketDefaults}
        onOpenChange={(v) => !v && setTicketDefaults(null)}
        defaults={ticketDefaults ?? undefined}
      />
    </div>
  );
}
