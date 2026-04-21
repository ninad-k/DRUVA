import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gem, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { MarketCycleBanner } from "@/components/common/MarketCycleBanner";
import { FundamentalsDrawer } from "@/components/common/FundamentalsDrawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  acknowledgeScanResult,
  createMultibaggerScanner,
  deleteMultibaggerScanner,
  disableMultibaggerScanner,
  dismissScanResult,
  enableMultibaggerScanner,
  listAccounts,
  listMultibaggerScannerRegistry,
  listMultibaggerScanners,
  listScanResults,
  promoteScanResult,
  runMultibaggerScanner,
} from "@/api/rest/endpoints";

const STATUS_FILTERS = [
  { value: "new", label: "New" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "promoted", label: "Promoted" },
  { value: "dismissed", label: "Dismissed" },
];

export function MultibaggerPage() {
  const qc = useQueryClient();
  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: listAccounts,
  });
  const [accountId, setAccountId] = useState<string>("");
  const activeAccount = accountId || accounts[0]?.id || "";
  const [statusFilter, setStatusFilter] = useState<string>("new");
  const [focusSymbol, setFocusSymbol] = useState<string | null>(null);

  const { data: registry = [] } = useQuery({
    queryKey: ["multibagger", "registry"],
    queryFn: listMultibaggerScannerRegistry,
  });

  const { data: scanners = [], isLoading: loadingScanners } = useQuery({
    queryKey: ["multibagger", "scanners", activeAccount],
    queryFn: () => listMultibaggerScanners(activeAccount),
    enabled: !!activeAccount,
  });

  const { data: results = [], isLoading: loadingResults } = useQuery({
    queryKey: ["multibagger", "results", activeAccount, statusFilter],
    queryFn: () =>
      listScanResults({ account_id: activeAccount, status: statusFilter, limit: 300 }),
    enabled: !!activeAccount,
    refetchInterval: 60_000,
  });

  const sorted = useMemo(
    () => [...results].sort((a, b) => b.score - a.score),
    [results],
  );

  const runMutation = useMutation({
    mutationFn: (id: string) => runMultibaggerScanner(id),
    onSuccess: (r) => {
      toast.success(`Scanner emitted ${r.emitted} candidate(s)`);
      qc.invalidateQueries({ queryKey: ["multibagger"] });
    },
    onError: (e: unknown) => toast.error(`Run failed: ${String(e)}`),
  });

  const promoteMutation = useMutation({
    mutationFn: (id: string) => promoteScanResult(id),
    onSuccess: (r) => {
      if (r.approval_id) toast.success("Candidate routed to Action Center");
      else toast.message("Promotion skipped", { description: r.reason ?? "" });
      qc.invalidateQueries({ queryKey: ["multibagger", "results"] });
    },
    onError: (e: unknown) => toast.error(`Promote failed: ${String(e)}`),
  });

  const dismissMutation = useMutation({
    mutationFn: (id: string) => dismissScanResult(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["multibagger", "results"] }),
  });

  const ackMutation = useMutation({
    mutationFn: (id: string) => acknowledgeScanResult(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["multibagger", "results"] }),
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Multibagger"
        description="VCP + fundamentals + market-cycle aware stock picks. Routes through approvals."
        actions={
          <div className="flex items-center gap-2">
            <div className="w-48">
              <Select value={activeAccount} onValueChange={setAccountId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select account" />
                </SelectTrigger>
                <SelectContent>
                  {accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.display_name ?? a.broker}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <CreateScannerDialog
              accountId={activeAccount}
              registry={registry}
              onCreated={() =>
                qc.invalidateQueries({ queryKey: ["multibagger", "scanners"] })
              }
            />
          </div>
        }
      />

      <MarketCycleBanner />

      <Card>
        <CardContent className="p-4">
          <h3 className="mb-3 text-sm font-semibold text-muted-foreground">
            Configured scanners
          </h3>
          {loadingScanners ? (
            <Skeleton className="h-16 w-full" />
          ) : scanners.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No scanners configured. Add one to start emitting candidates.
            </p>
          ) : (
            <div className="space-y-2">
              {scanners.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-sm"
                >
                  <div>
                    <div className="font-medium">{s.name}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {s.scanner_class} · {s.cadence} ·{" "}
                      {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "never run"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={s.is_enabled ? "default" : "secondary"}>
                      {s.is_enabled ? "enabled" : "disabled"}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => runMutation.mutate(s.id)}
                    >
                      <Play className="mr-1 h-3 w-3" />
                      Run now
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        if (s.is_enabled) await disableMultibaggerScanner(s.id);
                        else await enableMultibaggerScanner(s.id);
                        qc.invalidateQueries({ queryKey: ["multibagger", "scanners"] });
                      }}
                    >
                      {s.is_enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={async () => {
                        await deleteMultibaggerScanner(s.id);
                        qc.invalidateQueries({ queryKey: ["multibagger", "scanners"] });
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-red-400" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-muted-foreground">Candidates</h3>
            <div className="w-44">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTERS.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {loadingResults ? (
            <Skeleton className="h-40 w-full" />
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={Gem}
              title="No candidates"
              description="Run a scanner to populate the board."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  <TableHead className="text-right">Stop</TableHead>
                  <TableHead className="text-right">Target</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell
                      className="cursor-pointer font-medium hover:underline"
                      onClick={() => setFocusSymbol(r.symbol)}
                    >
                      {r.symbol}
                      <span className="ml-1 text-xs text-muted-foreground">
                        {r.exchange}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{r.stage ?? "—"}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {r.score.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {r.suggested_entry?.toFixed(2) ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {r.suggested_stop?.toFixed(2) ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {r.suggested_target?.toFixed(2) ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                      {r.reason ?? ""}
                    </TableCell>
                    <TableCell className="space-x-1 text-right">
                      {r.status === "new" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => ackMutation.mutate(r.id)}
                        >
                          Ack
                        </Button>
                      )}
                      {(r.status === "new" || r.status === "acknowledged") && (
                        <Button
                          size="sm"
                          onClick={() => promoteMutation.mutate(r.id)}
                        >
                          Promote
                        </Button>
                      )}
                      {r.status !== "dismissed" && r.status !== "promoted" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => dismissMutation.mutate(r.id)}
                        >
                          Dismiss
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

      <FundamentalsDrawer
        symbol={focusSymbol}
        onOpenChange={(v) => !v && setFocusSymbol(null)}
      />
    </div>
  );
}

function CreateScannerDialog({
  accountId,
  registry,
  onCreated,
}: {
  accountId: string;
  registry: string[];
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("VCP Multibagger");
  const [scannerClass, setScannerClass] = useState<string>(
    "scanner.vcp_multibagger.v1",
  );
  const [cadence, setCadence] = useState<string>("daily");

  const createMutation = useMutation({
    mutationFn: () =>
      createMultibaggerScanner({
        account_id: accountId,
        name,
        scanner_class: scannerClass,
        cadence,
        parameters: {},
      }),
    onSuccess: () => {
      setOpen(false);
      onCreated();
      toast.success("Scanner created");
    },
    onError: (e: unknown) => toast.error(String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={!accountId}>New scanner</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create scanner</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="sc-name">Name</Label>
            <Input
              id="sc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label>Scanner class</Label>
            <Select value={scannerClass} onValueChange={setScannerClass}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {registry.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Cadence</Label>
            <Select value={cadence} onValueChange={setCadence}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">daily</SelectItem>
                <SelectItem value="weekly">weekly</SelectItem>
                <SelectItem value="monthly">monthly</SelectItem>
                <SelectItem value="on_demand">on_demand</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!accountId || createMutation.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
