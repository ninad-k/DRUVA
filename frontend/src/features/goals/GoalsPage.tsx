import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createGoal,
  createStpPlan,
  getGoalProgress,
  listAccounts,
  listGoals,
  pauseGoal,
  resumeGoal,
  type Goal,
} from "@/api/rest/endpoints";

export function GoalsPage() {
  const qc = useQueryClient();
  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: listAccounts,
  });
  const [accountId, setAccountId] = useState<string>("");
  const activeAccount = accountId || accounts[0]?.id || "";

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ["goals", activeAccount],
    queryFn: () => listGoals(activeAccount),
    enabled: !!activeAccount,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Goals"
        description="Goal-based investing with SIP cadence + STP drain plans."
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
            <CreateGoalDialog
              accountId={activeAccount}
              onCreated={() => qc.invalidateQueries({ queryKey: ["goals"] })}
            />
          </div>
        }
      />

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : goals.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No goals yet"
          description="Create a goal with a target amount + date to start a SIP."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {goals.map((g) => (
            <GoalCard key={g.id} goal={g} />
          ))}
        </div>
      )}
    </div>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const qc = useQueryClient();
  const { data: progress } = useQuery({
    queryKey: ["goal-progress", goal.id],
    queryFn: () => getGoalProgress(goal.id),
    refetchInterval: 60_000,
  });
  const pct = Math.min(100, parseFloat(progress?.progress_pct ?? "0"));

  const pauseMutation = useMutation({
    mutationFn: () =>
      goal.status === "active" ? pauseGoal(goal.id) : resumeGoal(goal.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["goals"] }),
  });

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold">{goal.name}</h3>
            <p className="text-xs text-muted-foreground">
              Target ₹{Number(goal.target_amount).toLocaleString("en-IN")} by{" "}
              {goal.target_date}
            </p>
          </div>
          <Badge variant={goal.status === "active" ? "default" : "secondary"}>
            {goal.status}
          </Badge>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Progress</span>
            <span className="font-mono tabular-nums">{pct.toFixed(1)}%</span>
          </div>
          <div className="h-2 rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <Cell label="Current" value={`₹${fmt(progress?.current_value)}`} />
          <Cell label="Projected" value={`₹${fmt(progress?.projected_value)}`} />
          <Cell
            label="Required monthly"
            value={`₹${fmt(progress?.required_monthly)}`}
          />
          <Cell label="Months left" value={progress?.months_remaining.toString() ?? "—"} />
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
          >
            {goal.status === "active" ? "Pause" : "Resume"}
          </Button>
          <StpDialog goalId={goal.id} />
        </div>
      </CardContent>
    </Card>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground">{label}</div>
      <div className="font-mono tabular-nums">{value}</div>
    </div>
  );
}

function fmt(v: string | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  if (isNaN(n)) return v;
  return n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function StpDialog({ goalId }: { goalId: string }) {
  const [open, setOpen] = useState(false);
  const [lumpSum, setLumpSum] = useState(100000);
  const [months, setMonths] = useState(12);
  const mutation = useMutation({
    mutationFn: () => createStpPlan(goalId, { lump_sum: lumpSum, months }),
    onSuccess: (r) => {
      toast.success(`STP scheduled — next run ${r.next_run_date}`);
      setOpen(false);
    },
    onError: (e: unknown) => toast.error(String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="secondary">
          STP plan
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set up STP</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="lump-sum">Lump sum (INR)</Label>
            <Input
              id="lump-sum"
              type="number"
              value={lumpSum}
              onChange={(e) => setLumpSum(Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="months">Months</Label>
            <Input
              id="months"
              type="number"
              value={months}
              onChange={(e) => setMonths(Number(e.target.value))}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CreateGoalDialog({
  accountId,
  onCreated,
}: {
  accountId: string;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("Retirement");
  const [target, setTarget] = useState(10_000_000);
  const [date, setDate] = useState(new Date(Date.now() + 10 * 365 * 864e5).toISOString().slice(0, 10));
  const [monthly, setMonthly] = useState(30000);
  const [symbols, setSymbols] = useState("NIFTYBEES");

  const mutation = useMutation({
    mutationFn: () =>
      createGoal({
        account_id: accountId,
        name,
        target_amount: target,
        target_date: date,
        monthly_sip_amount: monthly,
        target_symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      setOpen(false);
      onCreated();
      toast.success("Goal created");
    },
    onError: (e: unknown) => toast.error(String(e)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={!accountId}>New goal</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create goal</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Target amount (INR)">
            <Input
              type="number"
              value={target}
              onChange={(e) => setTarget(Number(e.target.value))}
            />
          </Field>
          <Field label="Target date">
            <Input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>
          <Field label="Monthly SIP">
            <Input
              type="number"
              value={monthly}
              onChange={(e) => setMonthly(Number(e.target.value))}
            />
          </Field>
          <Field label="Target symbols (comma-separated)">
            <Input value={symbols} onChange={(e) => setSymbols(e.target.value)} />
          </Field>
        </div>
        <DialogFooter>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}
