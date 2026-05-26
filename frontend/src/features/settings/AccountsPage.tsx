import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { MoreHorizontal, Pencil, Plus, Trash2, Wallet } from "lucide-react";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/common/EmptyState";
import { createAccount, deleteAccount, listAccounts, updateAccount } from "@/api/rest/endpoints";
import type { BrokerAccount } from "@/types/api";
import { useAccountStore } from "@/store/account";

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
  api_key: z.string().optional(),
  api_secret: z.string().optional(),
  is_paper: z.boolean(),
});
type FormValues = z.infer<typeof schema>;

export function AccountsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<BrokerAccount | null>(null);
  const [broker, setBroker] = useState<BrokerAccount["broker"]>("zerodha");
  const activeAccountId = useAccountStore((s) => s.activeAccountId);
  const setActiveAccountId = useAccountStore((s) => s.setActiveAccountId);

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

  const refreshAccounts = () => {
    qc.invalidateQueries({ queryKey: ["accounts"] });
    qc.invalidateQueries({ queryKey: ["accounts-bootstrap"] });
  };

  const openAddDialog = () => {
    setEditingAccount(null);
    setBroker("zerodha");
    reset({
      broker: "zerodha",
      display_name: "",
      api_key: "",
      api_secret: "",
      is_paper: true,
    });
    setOpen(true);
  };

  const openEditDialog = (account: BrokerAccount) => {
    setEditingAccount(account);
    setBroker(account.broker);
    reset({
      broker: account.broker,
      display_name: account.display_name,
      api_key: "",
      api_secret: "",
      is_paper: account.is_paper,
    });
    setOpen(true);
  };

  const create = useMutation({
    mutationFn: createAccount,
    onSuccess: (account) => {
      setActiveAccountId(account.id);
      toast.success("Account added");
      refreshAccounts();
      setOpen(false);
      reset();
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (err as { message?: string })?.message;
      toast.error(detail ? `Failed to add account: ${detail}` : "Failed to add account");
    },
  });

  const update = useMutation({
    mutationFn: ({ accountId, values }: { accountId: string; values: FormValues }) =>
      updateAccount(accountId, values),
    onSuccess: (account) => {
      setActiveAccountId(account.id);
      toast.success("Account updated");
      refreshAccounts();
      setOpen(false);
      setEditingAccount(null);
      reset();
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (err as { message?: string })?.message;
      toast.error(detail ? `Failed to update account: ${detail}` : "Failed to update account");
    },
  });

  const remove = useMutation({
    mutationFn: deleteAccount,
    onSuccess: (_, deletedId) => {
      if (activeAccountId === deletedId) {
        const nextAccount = accounts.find((account) => account.id !== deletedId);
        setActiveAccountId(nextAccount?.id ?? null);
      }
      toast.success("Account deleted");
      refreshAccounts();
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (err as { message?: string })?.message;
      toast.error(detail ? `Failed to delete account: ${detail}` : "Failed to delete account");
    },
  });

  const onSubmit = (values: FormValues) => {
    if (editingAccount) {
      update.mutate({ accountId: editingAccount.id, values });
      return;
    }
    if (!values.api_key || !values.api_secret) {
      toast.error("API key and API secret are required");
      return;
    }
    create.mutate({
      ...values,
      api_key: values.api_key,
      api_secret: values.api_secret,
    });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Broker Accounts"
        description="Connect your broker accounts. Paper accounts are sandboxed."
        actions={
          <Button onClick={openAddDialog}>
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
          action={{ label: "Add Account", onClick: openAddDialog }}
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
                  <div className="flex items-start gap-2">
                    <div className="flex flex-col gap-1 items-end">
                      <Badge variant={a.is_paper ? "outline" : "default"}>
                        {a.is_paper ? "Paper" : "Live"}
                      </Badge>
                      <Badge variant={a.is_connected ? "success" : "destructive"}>
                        {a.is_connected ? "Connected" : "Disconnected"}
                      </Badge>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label="Account actions">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEditDialog(a)}>
                          <Pencil className="mr-2 h-4 w-4" /> Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-[hsl(var(--destructive))]"
                          disabled={remove.isPending}
                          onClick={() => {
                            if (window.confirm(`Delete ${a.display_name}?`)) {
                              remove.mutate(a.id);
                            }
                          }}
                        >
                          <Trash2 className="mr-2 h-4 w-4" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
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
            <DialogTitle>{editingAccount ? "Edit Broker Account" : "Add Broker Account"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
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
              <Input
                id="api_key"
                {...register("api_key")}
                autoComplete="off"
                placeholder={editingAccount ? "Leave blank to keep existing" : ""}
              />
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
                placeholder={editingAccount ? "Leave blank to keep existing" : ""}
              />
              {errors.api_secret && (
                <p className="text-xs text-[hsl(var(--loss))]">{errors.api_secret.message}</p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Checkbox
                id="is_paper"
                checked={isPaper}
                onCheckedChange={(v) => setValue("is_paper", v === true)}
              />
              <Label htmlFor="is_paper" className="cursor-pointer">
                Paper trading (sandboxed)
              </Label>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending || update.isPending}>
                {editingAccount ? "Save Changes" : "Add Account"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
