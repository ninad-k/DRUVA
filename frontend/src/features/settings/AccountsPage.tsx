import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Wallet } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/EmptyState";
import { createAccount, listAccounts } from "@/api/rest/endpoints";
import type { BrokerAccount } from "@/types/api";

const BROKERS: { value: BrokerAccount["broker"]; label: string }[] = [
  { value: "zerodha", label: "Zerodha" },
  { value: "upstox", label: "Upstox" },
  { value: "dhan", label: "Dhan" },
  { value: "fyers", label: "Fyers" },
  { value: "five_paisa", label: "5paisa" },
  { value: "alice_blue", label: "Alice Blue" },
  { value: "angel_one", label: "Angel One" },
  { value: "kotak_neo", label: "Kotak Neo" },
  { value: "shoonya", label: "Shoonya" },
];

const schema = z.object({
  broker: z.enum([
    "zerodha",
    "upstox",
    "dhan",
    "fyers",
    "five_paisa",
    "alice_blue",
    "angel_one",
    "kotak_neo",
    "shoonya",
  ]),
  display_name: z.string().min(1).optional(),
  api_key: z.string().min(1, "Required"),
  api_secret: z.string().min(1, "Required"),
  is_paper: z.boolean(),
});
type FormValues = z.infer<typeof schema>;

export function AccountsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [broker, setBroker] = useState<BrokerAccount["broker"]>("zerodha");

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ["accounts"],
    queryFn: listAccounts,
  });

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      broker: "zerodha",
      display_name: "",
      api_key: "",
      api_secret: "",
      is_paper: true,
    },
  });
  const isPaper = watch("is_paper");

  const create = useMutation({
    mutationFn: createAccount,
    onSuccess: () => {
      toast.success("Account added");
      qc.invalidateQueries({ queryKey: ["accounts"] });
      setOpen(false);
      reset();
    },
    onError: () => toast.error("Failed to add account"),
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Broker Accounts"
        description="Connect your broker accounts. Paper accounts are sandboxed."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> Add Account
          </Button>
        }
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : accounts.length === 0 ? (
        <EmptyState
          icon={Wallet}
          title="No accounts connected"
          description="Add a broker account to start placing orders. We support 9+ Indian brokers."
          action={{ label: "Add Account", onClick: () => setOpen(true) }}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {accounts.map((a) => (
            <Card key={a.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold">{a.display_name}</p>
                    <p className="text-xs text-muted-foreground capitalize">{a.broker}</p>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    <Badge variant={a.is_paper ? "outline" : "default"}>
                      {a.is_paper ? "Paper" : "Live"}
                    </Badge>
                    <Badge variant={a.is_connected ? "success" : "destructive"}>
                      {a.is_connected ? "Connected" : "Disconnected"}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Broker Account</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="space-y-4">
            <div className="space-y-1.5">
              <Label>Broker</Label>
              <Select
                value={broker}
                onValueChange={(v) => {
                  setBroker(v as BrokerAccount["broker"]);
                  setValue("broker", v as BrokerAccount["broker"]);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BROKERS.map((b) => (
                    <SelectItem key={b.value} value={b.value}>
                      {b.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="display_name">Display name (optional)</Label>
              <Input id="display_name" {...register("display_name")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="api_key">API Key</Label>
              <Input id="api_key" {...register("api_key")} autoComplete="off" />
              {errors.api_key && (
                <p className="text-xs text-[hsl(var(--loss))]">{errors.api_key.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="api_secret">API Secret</Label>
              <Input
                id="api_secret"
                type="password"
                autoComplete="new-password"
                {...register("api_secret")}
              />
              {errors.api_secret && (
                <p className="text-xs text-[hsl(var(--loss))]">{errors.api_secret.message}</p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Checkbox
                id="is_paper"
                checked={isPaper}
                onCheckedChange={(v) => setValue("is_paper", v)}
              />
              <Label htmlFor="is_paper" className="cursor-pointer">
                Paper trading (sandboxed)
              </Label>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                Add Account
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
