import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Plus } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createWebhookSource,
  linkTelegram,
  listWebhookSources,
  revokeWebhookSource,
} from "@/api/rest/endpoints";
import type { WebhookSource } from "@/types/api";
import { formatDateTime } from "@/utils/format";

const SOURCE_TYPES: { value: WebhookSource["source_type"]; label: string }[] = [
  { value: "chartink", label: "ChartInk" },
  { value: "tradingview", label: "TradingView" },
  { value: "amibroker", label: "AmiBroker" },
  { value: "metatrader", label: "MetaTrader" },
  { value: "gocharting", label: "GoCharting" },
  { value: "n8n", label: "n8n" },
];

const telegramSchema = z.object({
  chat_id: z.string().min(3, "Required"),
});
type TelegramForm = z.infer<typeof telegramSchema>;

export function NotificationsPage() {
  const qc = useQueryClient();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TelegramForm>({
    resolver: zodResolver(telegramSchema),
    defaultValues: { chat_id: "" },
  });

  const telegramMut = useMutation({
    mutationFn: (v: TelegramForm) => linkTelegram(v.chat_id),
    onSuccess: () => toast.success("Telegram linked"),
    onError: () => toast.error("Failed to link Telegram"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description="Link Telegram and manage incoming webhook sources."
      />

      <Card>
        <CardHeader>
          <CardTitle>Telegram</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit((v) => telegramMut.mutate(v))}
            className="flex flex-wrap items-end gap-3"
          >
            <div className="flex-1 min-w-[220px]">
              <Label htmlFor="chat_id">Chat ID</Label>
              <Input id="chat_id" placeholder="123456789" {...register("chat_id")} />
              {errors.chat_id && (
                <p className="text-xs text-[hsl(var(--loss))]">{errors.chat_id.message}</p>
              )}
            </div>
            <Button type="submit" disabled={telegramMut.isPending}>
              Link Telegram
            </Button>
          </form>
          <p className="mt-3 text-xs text-muted-foreground">
            Start a chat with the DHRUVA bot, then paste the chat ID it replies with.
          </p>
        </CardContent>
      </Card>

      <WebhookSourcesCard qc={qc} />
    </div>
  );
}

interface WebhookCardProps {
  qc: ReturnType<typeof useQueryClient>;
}

function WebhookSourcesCard({ qc }: WebhookCardProps) {
  const [open, setOpen] = useState(false);
  const [sourceType, setSourceType] = useState<WebhookSource["source_type"]>("tradingview");
  const [displayName, setDisplayName] = useState("");
  const [createdToken, setCreatedToken] = useState<{ id: string; token: string } | null>(null);

  const sources = useQuery({
    queryKey: ["webhook-sources"],
    queryFn: listWebhookSources,
  });

  const createMut = useMutation({
    mutationFn: () =>
      createWebhookSource({ source_type: sourceType, display_name: displayName || sourceType }),
    onSuccess: (data) => {
      setCreatedToken({ id: data.id, token: data.token });
      qc.invalidateQueries({ queryKey: ["webhook-sources"] });
      setOpen(false);
      setDisplayName("");
    },
    onError: () => toast.error("Failed to create source"),
  });

  const revokeMut = useMutation({
    mutationFn: (id: string) => revokeWebhookSource(id),
    onSuccess: () => {
      toast.success("Revoked");
      qc.invalidateQueries({ queryKey: ["webhook-sources"] });
    },
    onError: () => toast.error("Failed to revoke"),
  });

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Copy failed");
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Webhook Sources</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Add Source
        </Button>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {sources.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (sources.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No webhook sources yet. Add one to receive signals from TradingView, ChartInk, etc.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.data!.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <Badge variant="secondary">{s.source_type}</Badge>
                  </TableCell>
                  <TableCell className="font-medium">{s.display_name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(s.created_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={s.revoked_at ? "destructive" : "success"}>
                      {s.revoked_at ? "Revoked" : "Active"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {!s.revoked_at && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => revokeMut.mutate(s.id)}
                      >
                        Revoke
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Webhook Source</DialogTitle>
            <DialogDescription>
              A secret token will be shown once — store it safely.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Source</Label>
              <Select
                value={sourceType}
                onValueChange={(v) => setSourceType(v as WebhookSource["source_type"])}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SOURCE_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="display_name">Name</Label>
              <Input
                id="display_name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => createMut.mutate()} disabled={createMut.isPending}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!createdToken} onOpenChange={(v) => !v && setCreatedToken(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Secret token</DialogTitle>
            <DialogDescription>
              This token is shown only once. Copy it now — you won't see it again.
            </DialogDescription>
          </DialogHeader>
          {createdToken && (
            <div className="rounded-md border border-border bg-muted/40 p-3">
              <code className="break-all font-mono text-xs">{createdToken.token}</code>
            </div>
          )}
          <DialogFooter>
            {createdToken && (
              <Button onClick={() => copy(createdToken.token)}>
                <Copy className="h-4 w-4" /> Copy
              </Button>
            )}
            <Button variant="outline" onClick={() => setCreatedToken(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
