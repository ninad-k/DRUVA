import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Play, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  addAdvisorWatchlist,
  allocateAdvisor,
  getAdvisorConfig,
  latestAdvisorScores,
  listAdvisorRuns,
  listAdvisorWatchlist,
  removeAdvisorWatchlist,
  saveAdvisorConfig,
  triggerAdvisorRun,
  type AdvisorProvider,
} from "@/api/rest/endpoints";
import { formatNumber } from "@/utils/format";

const PROVIDERS: { value: AdvisorProvider; label: string; defaultModel: string; defaultUrl: string }[] = [
  { value: "ollama", label: "Ollama (local)", defaultModel: "gemma3:4b", defaultUrl: "http://localhost:11434" },
  { value: "openai_compatible", label: "OpenAI-compatible (vLLM / LM Studio)", defaultModel: "gemma-3-4b", defaultUrl: "http://localhost:8000/v1" },
  { value: "anthropic", label: "Anthropic Claude", defaultModel: "claude-haiku-4-5-20251001", defaultUrl: "" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini", defaultUrl: "" },
  { value: "none", label: "Disabled (rules only)", defaultModel: "-", defaultUrl: "" },
];

function tierColor(tier: string | null | undefined) {
  if (tier === "S") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
  if (tier === "A") return "bg-blue-500/15 text-blue-400 border-blue-500/30";
  if (tier === "B") return "bg-amber-500/15 text-amber-400 border-amber-500/30";
  return "bg-muted text-muted-foreground";
}

function regimeColor(r?: string) {
  if (r === "aggressive") return "text-emerald-400";
  if (r === "defensive") return "text-red-400";
  return "text-amber-400";
}

export function AdvisorPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Advisor"
        description="Rules-based scoring + configurable LLM for multibagger research on NSE/BSE. Not investment advice."
      />
      <Tabs defaultValue="scores">
        <TabsList>
          <TabsTrigger value="scores">Scores</TabsTrigger>
          <TabsTrigger value="allocate">Allocate</TabsTrigger>
          <TabsTrigger value="watchlist">Watchlist</TabsTrigger>
          <TabsTrigger value="llm">LLM Config</TabsTrigger>
        </TabsList>
        <TabsContent value="scores"><ScoresTab /></TabsContent>
        <TabsContent value="allocate"><AllocateTab /></TabsContent>
        <TabsContent value="watchlist"><WatchlistTab /></TabsContent>
        <TabsContent value="llm"><LLMTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function ScoresTab() {
  const qc = useQueryClient();
  const [capital, setCapital] = useState(100000);
  const [maxPositions, setMaxPositions] = useState(8);
  const [stopLoss, setStopLoss] = useState(10);

  const scoresQ = useQuery({
    queryKey: ["advisor-scores"],
    queryFn: latestAdvisorScores,
    refetchInterval: 60_000,
  });
  const runsQ = useQuery({ queryKey: ["advisor-runs"], queryFn: listAdvisorRuns });
  const triggerM = useMutation({
    mutationFn: () => triggerAdvisorRun({
      capital_inr: capital,
      max_positions: maxPositions,
      stop_loss_pct: stopLoss,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["advisor-scores"] });
      qc.invalidateQueries({ queryKey: ["advisor-runs"] });
    },
  });

  const latest = runsQ.data?.[0];

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-40">
            <Label>Capital (₹)</Label>
            <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value) || 0)} />
          </div>
          <div className="w-28">
            <Label>Max positions</Label>
            <Input type="number" value={maxPositions} onChange={(e) => setMaxPositions(Number(e.target.value) || 1)} />
          </div>
          <div className="w-28">
            <Label>SL %</Label>
            <Input type="number" value={stopLoss} onChange={(e) => setStopLoss(Number(e.target.value) || 1)} />
          </div>
          <Button onClick={() => triggerM.mutate()} disabled={triggerM.isPending} className="gap-2">
            <Play className="h-4 w-4" />
            {triggerM.isPending ? "Running…" : "Run advisor"}
          </Button>
          {latest && (
            <div className="ml-auto text-xs text-muted-foreground">
              Last run: {new Date(latest.ran_at).toLocaleString()} · Regime:{" "}
              <span className={regimeColor(latest.macro_regime) + " font-medium uppercase"}>
                {latest.macro_regime}
              </span>
              {latest.nifty_roc != null && <> · Nifty ROC(18m): {latest.nifty_roc.toFixed(1)}%</>}
              {latest.llm_model && <> · LLM: {latest.llm_provider}/{latest.llm_model}</>}
            </div>
          )}
        </div>

        {scoresQ.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
          </div>
        ) : (scoresQ.data ?? []).length === 0 ? (
          <EmptyState
            icon={Brain}
            title="No scores yet"
            description="Add symbols to your watchlist and trigger a run."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead className="text-right">Composite</TableHead>
                <TableHead className="text-right">Tech</TableHead>
                <TableHead className="text-right">Mom</TableHead>
                <TableHead className="text-right">Fund</TableHead>
                <TableHead className="text-right">LLM</TableHead>
                <TableHead className="text-right">LTP</TableHead>
                <TableHead className="text-right">SL</TableHead>
                <TableHead className="text-right">Target</TableHead>
                <TableHead className="text-right">Alloc %</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(scoresQ.data ?? []).map((r) => (
                <TableRow key={`${r.symbol}-${r.exchange}`}>
                  <TableCell>
                    <Badge variant="outline" className={tierColor(r.multibagger_tier)}>
                      {r.multibagger_tier ?? "-"}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-medium">
                    {r.symbol}
                    <span className="ml-1 text-xs text-muted-foreground">{r.exchange}</span>
                    {r.rationale && (
                      <div className="mt-1 text-xs text-muted-foreground max-w-md truncate" title={r.rationale}>
                        {r.rationale}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums font-semibold">
                    {r.composite_score.toFixed(1)}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{r.technical_score.toFixed(0)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{r.momentum_score.toFixed(0)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{r.fundamental_score.toFixed(0)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                    {r.llm_score != null ? r.llm_score.toFixed(0) : "-"}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatNumber(r.last_price ?? 0)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-red-400">
                    {r.stop_loss != null ? formatNumber(r.stop_loss) : "-"}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-emerald-400">
                    {r.target_price != null ? formatNumber(r.target_price) : "-"}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {r.suggested_allocation_pct.toFixed(1)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function AllocateTab() {
  const [capital, setCapital] = useState(100000);
  const [maxPositions, setMaxPositions] = useState(8);
  const [stopLoss, setStopLoss] = useState(10);

  const allocQ = useQuery({
    queryKey: ["advisor-allocate", capital, maxPositions, stopLoss],
    queryFn: () => allocateAdvisor({
      capital_inr: capital,
      max_positions: maxPositions,
      stop_loss_pct: stopLoss,
    }),
    enabled: false,
  });

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-40">
            <Label>Capital (₹)</Label>
            <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value) || 0)} />
          </div>
          <div className="w-28">
            <Label>Max positions</Label>
            <Input type="number" value={maxPositions} onChange={(e) => setMaxPositions(Number(e.target.value) || 1)} />
          </div>
          <div className="w-28">
            <Label>SL %</Label>
            <Input type="number" value={stopLoss} onChange={(e) => setStopLoss(Number(e.target.value) || 1)} />
          </div>
          <Button onClick={() => allocQ.refetch()}>Compute allocation</Button>
        </div>
        {(allocQ.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Hit "Compute allocation" after at least one advisor run exists.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead className="text-right">% of capital</TableHead>
                <TableHead className="text-right">₹ allocated</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Stop-loss</TableHead>
                <TableHead className="text-right">Target</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(allocQ.data ?? []).map((a) => (
                <TableRow key={`${a.symbol}-${a.exchange}`}>
                  <TableCell className="font-medium">
                    {a.symbol} <span className="text-xs text-muted-foreground">{a.exchange}</span>
                  </TableCell>
                  <TableCell><Badge variant="outline" className={tierColor(a.tier)}>{a.tier}</Badge></TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{a.suggested_pct.toFixed(1)}%</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{formatNumber(a.suggested_inr)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{a.qty}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-red-400">{formatNumber(a.stop_loss)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-emerald-400">{formatNumber(a.target_price)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function WatchlistTab() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["advisor-wl"], queryFn: listAdvisorWatchlist });
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [sector, setSector] = useState("");
  const [notes, setNotes] = useState("");

  const addM = useMutation({
    mutationFn: () => addAdvisorWatchlist({ symbol, exchange, sector: sector || undefined, notes: notes || undefined }),
    onSuccess: () => {
      setSymbol(""); setSector(""); setNotes("");
      qc.invalidateQueries({ queryKey: ["advisor-wl"] });
    },
  });
  const delM = useMutation({
    mutationFn: (id: string) => removeAdvisorWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["advisor-wl"] }),
  });

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-40"><Label>Symbol</Label><Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="RELIANCE" /></div>
          <div className="w-24"><Label>Exchange</Label><Input value={exchange} onChange={(e) => setExchange(e.target.value.toUpperCase())} /></div>
          <div className="w-40"><Label>Sector</Label><Input value={sector} onChange={(e) => setSector(e.target.value)} /></div>
          <div className="flex-1 min-w-64">
            <Label>Fundamentals JSON (optional)</Label>
            <Input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={'{"roce": 22, "eps_growth_yoy": 18, "pe_ratio": 25, "sector_median_pe": 30}'}
            />
          </div>
          <Button onClick={() => addM.mutate()} disabled={!symbol || addM.isPending} className="gap-2">
            <Plus className="h-4 w-4" /> Add
          </Button>
        </div>
        {data.length === 0 ? (
          <EmptyState icon={Brain} title="Empty watchlist" description="Add symbols you want the advisor to track daily." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Exchange</TableHead>
                <TableHead>Sector</TableHead>
                <TableHead>Fundamentals</TableHead>
                <TableHead className="w-16"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((w) => (
                <TableRow key={w.id}>
                  <TableCell className="font-medium">{w.symbol}</TableCell>
                  <TableCell>{w.exchange}</TableCell>
                  <TableCell className="text-muted-foreground">{w.sector ?? "-"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-sm truncate" title={w.notes ?? ""}>
                    {w.notes ?? "-"}
                  </TableCell>
                  <TableCell>
                    <Button size="sm" variant="ghost" onClick={() => delM.mutate(w.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function LLMTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["advisor-config"], queryFn: getAdvisorConfig });
  const [provider, setProvider] = useState<AdvisorProvider>("ollama");
  const [model, setModel] = useState("gemma3:4b");
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(1024);

  useEffect(() => {
    if (data) {
      setProvider(data.provider);
      setModel(data.model);
      setBaseUrl(data.base_url);
      setTemperature(data.temperature);
      setMaxTokens(data.max_tokens);
    }
  }, [data]);

  const saveM = useMutation({
    mutationFn: () => saveAdvisorConfig({
      provider,
      model,
      base_url: baseUrl,
      api_key: apiKey || undefined,
      temperature,
      max_tokens: maxTokens,
      is_enabled: true,
    }),
    onSuccess: () => {
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["advisor-config"] });
    },
  });

  return (
    <Card>
      <CardContent className="p-4 space-y-4 max-w-2xl">
        <div className="grid gap-3">
          <div>
            <Label>Provider</Label>
            <Select
              value={provider}
              onValueChange={(v) => {
                const p = v as AdvisorProvider;
                setProvider(p);
                const meta = PROVIDERS.find((x) => x.value === p);
                if (meta) {
                  setModel(meta.defaultModel);
                  if (meta.defaultUrl) setBaseUrl(meta.defaultUrl);
                }
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Model</Label>
            <Input value={model} onChange={(e) => setModel(e.target.value)} />
            {provider === "ollama" && (
              <p className="mt-1 text-xs text-muted-foreground">
                Install locally via <code>ollama pull {model}</code>.
              </p>
            )}
          </div>
          <div>
            <Label>Base URL</Label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          </div>
          <div>
            <Label>API key {data?.has_api_key && <span className="text-xs text-muted-foreground">(stored)</span>}</Label>
            <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="leave blank to keep existing" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Temperature</Label>
              <Input type="number" step="0.1" min="0" max="2" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
            </div>
            <div>
              <Label>Max tokens</Label>
              <Input type="number" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
            </div>
          </div>
          <Button onClick={() => saveM.mutate()} disabled={saveM.isPending}>
            {saveM.isPending ? "Saving…" : "Save configuration"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
