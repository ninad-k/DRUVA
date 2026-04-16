import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CandlestickChart } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/common/EmptyState";
import { getIvSmile, getOiProfile, getOptionChain } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import { formatNumber } from "@/utils/format";

export function OptionsPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const [underlying, setUnderlying] = useState("NIFTY");
  const [expiry, setExpiry] = useState("");
  const [spot, setSpot] = useState<number | "">("");
  const [submittedKey, setSubmittedKey] = useState<string | null>(null);

  const enabled = !!submittedKey && !!accountId;

  const chain = useQuery({
    queryKey: ["option-chain", submittedKey, accountId],
    queryFn: () =>
      getOptionChain({
        account_id: accountId!,
        underlying,
        expiry,
        spot: spot ? Number(spot) : undefined,
        risk_free_rate: 0.07,
      }),
    enabled,
  });

  const oi = useQuery({
    queryKey: ["option-oi", submittedKey, accountId],
    queryFn: () =>
      getOiProfile({ account_id: accountId!, underlying, expiry }),
    enabled,
  });

  const iv = useQuery({
    queryKey: ["option-iv", submittedKey, accountId],
    queryFn: () =>
      getIvSmile({ account_id: accountId!, underlying, expiry }),
    enabled,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Options Chain"
        description="Live option chain with Greeks, OI profile, and IV smile."
      />

      <Card>
        <CardContent className="p-4">
          <div className="grid gap-3 md:grid-cols-5">
            <div>
              <Label htmlFor="underlying">Underlying</Label>
              <Input
                id="underlying"
                value={underlying}
                onChange={(e) => setUnderlying(e.target.value.toUpperCase())}
              />
            </div>
            <div>
              <Label htmlFor="expiry">Expiry</Label>
              <Input
                id="expiry"
                type="date"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="spot">Spot (optional)</Label>
              <Input
                id="spot"
                type="number"
                value={spot}
                onChange={(e) => setSpot(e.target.value === "" ? "" : Number(e.target.value))}
              />
            </div>
            <div className="md:col-span-2 flex items-end">
              <Button
                onClick={() => setSubmittedKey(`${underlying}-${expiry}-${spot}`)}
                disabled={!underlying || !expiry || !accountId}
                className="w-full md:w-auto"
              >
                Load Chain
              </Button>
            </div>
          </div>
          {!accountId && (
            <p className="mt-2 text-xs text-[hsl(var(--loss))]">
              Connect a broker account before loading the option chain.
            </p>
          )}
        </CardContent>
      </Card>

      <Tabs defaultValue="chain">
        <TabsList>
          <TabsTrigger value="chain">Chain</TabsTrigger>
          <TabsTrigger value="oi">OI Profile</TabsTrigger>
          <TabsTrigger value="iv">IV Smile</TabsTrigger>
        </TabsList>

        <TabsContent value="chain">
          <Card>
            <CardContent className="p-2">
              {!enabled ? (
                <EmptyState
                  icon={CandlestickChart}
                  title="Load a chain"
                  description="Choose an underlying and expiry, then click Load Chain."
                />
              ) : chain.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading chain…</p>
              ) : chain.isError ? (
                <p className="p-4 text-sm text-[hsl(var(--loss))]">Failed to load chain.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-right">CE LTP</TableHead>
                      <TableHead className="text-right">CE IV</TableHead>
                      <TableHead className="text-right">CE OI</TableHead>
                      <TableHead className="text-right">CE Δ</TableHead>
                      <TableHead className="text-center">Strike</TableHead>
                      <TableHead className="text-right">PE Δ</TableHead>
                      <TableHead className="text-right">PE OI</TableHead>
                      <TableHead className="text-right">PE IV</TableHead>
                      <TableHead className="text-right">PE LTP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(chain.data?.rows ?? []).map((r) => (
                      <TableRow key={r.strike}>
                        <TableCell className="text-right font-mono">
                          {r.ce.ltp != null ? formatNumber(r.ce.ltp) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.ce.iv != null ? r.ce.iv.toFixed(1) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.ce.oi != null ? r.ce.oi.toLocaleString("en-IN") : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.ce.delta != null ? r.ce.delta.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell className="text-center font-semibold">
                          {r.strike}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.pe.delta != null ? r.pe.delta.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.pe.oi != null ? r.pe.oi.toLocaleString("en-IN") : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.pe.iv != null ? r.pe.iv.toFixed(1) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {r.pe.ltp != null ? formatNumber(r.pe.ltp) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="oi">
          <Card>
            <CardHeader>
              <CardTitle>OI Profile</CardTitle>
            </CardHeader>
            <CardContent>
              {!enabled || !oi.data ? (
                <p className="text-sm text-muted-foreground">Load a chain to view OI.</p>
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={oi.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="strike" stroke="hsl(var(--muted-foreground))" />
                      <YAxis stroke="hsl(var(--muted-foreground))" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                        }}
                      />
                      <Legend />
                      <Bar dataKey="ce_oi" name="CE OI" fill="hsl(var(--gain))" />
                      <Bar dataKey="pe_oi" name="PE OI" fill="hsl(var(--loss))" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="iv">
          <Card>
            <CardHeader>
              <CardTitle>IV Smile</CardTitle>
            </CardHeader>
            <CardContent>
              {!enabled || !iv.data ? (
                <p className="text-sm text-muted-foreground">Load a chain to view IV.</p>
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={iv.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="strike" stroke="hsl(var(--muted-foreground))" />
                      <YAxis stroke="hsl(var(--muted-foreground))" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="ce_iv"
                        name="CE IV"
                        stroke="hsl(var(--gain))"
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="pe_iv"
                        name="PE IV"
                        stroke="hsl(var(--loss))"
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
