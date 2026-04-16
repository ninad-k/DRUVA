import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createStrategy } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";

const STRATEGY_CLASSES = [
  "ema_crossover",
  "rsi_reversion",
  "vwap_breakout",
  "supertrend",
  "options_iron_condor",
  "ml_xgboost_intraday",
  "ml_lstm_swing",
];

const schema = z.object({
  name: z.string().min(2),
  strategy_class: z.string().min(1),
  parameters: z.string().refine(
    (s) => {
      try {
        JSON.parse(s);
        return true;
      } catch {
        return false;
      }
    },
    { message: "Invalid JSON" },
  ),
  mode: z.enum(["paper", "live"]),
  requires_approval: z.boolean(),
  is_ml: z.boolean(),
  model_version: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function NewStrategyDialog({ open, onOpenChange }: Props) {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();
  const [strategyClass, setStrategyClass] = useState<string>(STRATEGY_CLASSES[0]);
  const [mode, setMode] = useState<"paper" | "live">("paper");

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
    reset,
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      strategy_class: STRATEGY_CLASSES[0],
      parameters: "{}",
      mode: "paper",
      requires_approval: false,
      is_ml: false,
      model_version: "",
    },
  });
  const isMl = watch("is_ml");
  const requiresApproval = watch("requires_approval");

  const mut = useMutation({
    mutationFn: (values: FormValues) =>
      createStrategy({
        ...values,
        account_id: accountId ?? undefined,
        parameters: JSON.parse(values.parameters),
      }),
    onSuccess: () => {
      toast.success("Strategy created");
      qc.invalidateQueries({ queryKey: ["strategies"] });
      reset();
      onOpenChange(false);
    },
    onError: () => toast.error("Failed to create strategy"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New Strategy</DialogTitle>
          <DialogDescription>
            Configure a new strategy. Always test in paper mode first.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit((v) => mut.mutate(v))} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" {...register("name")} />
            {errors.name && (
              <p className="text-xs text-[hsl(var(--loss))]">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Strategy class</Label>
            <Select
              value={strategyClass}
              onValueChange={(v) => {
                setStrategyClass(v);
                setValue("strategy_class", v);
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STRATEGY_CLASSES.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="parameters">Parameters (JSON)</Label>
            <Textarea
              id="parameters"
              rows={5}
              placeholder={`{\n  "ema_fast": 9,\n  "ema_slow": 21\n}`}
              {...register("parameters")}
            />
            {errors.parameters && (
              <p className="text-xs text-[hsl(var(--loss))]">{errors.parameters.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Mode</Label>
            <Select
              value={mode}
              onValueChange={(v) => {
                setMode(v as "paper" | "live");
                setValue("mode", v as "paper" | "live");
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="paper">Paper</SelectItem>
                <SelectItem value="live">Live</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-3">
            <Checkbox
              id="requires_approval"
              checked={requiresApproval}
              onCheckedChange={(v) => setValue("requires_approval", v)}
            />
            <Label htmlFor="requires_approval" className="cursor-pointer">
              Require manual approval per trade
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Checkbox
              id="is_ml"
              checked={isMl}
              onCheckedChange={(v) => setValue("is_ml", v)}
            />
            <Label htmlFor="is_ml" className="cursor-pointer">
              ML strategy
            </Label>
          </div>

          {isMl && (
            <div className="space-y-1.5">
              <Label htmlFor="model_version">Model version</Label>
              <Input id="model_version" placeholder="e.g. xgb-2024.04" {...register("model_version")} />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mut.isPending}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
