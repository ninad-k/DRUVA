import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getFreqAIStatus, triggerFreqAIRetrain } from "@/api/rest/endpoints";

function formatRelative(iso: string | null): string {
  if (!iso) return "Never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

function formatAccuracy(value: number | null): string {
  if (value === null) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

export function FreqAIPage() {
  const queryClient = useQueryClient();
  const [retrainSuccess, setRetrainSuccess] = useState(false);

  const { data: status, isLoading } = useQuery({
    queryKey: ["freqai", "status"],
    queryFn: getFreqAIStatus,
    refetchInterval: 30_000,
  });

  const retrainMutation = useMutation({
    mutationFn: triggerFreqAIRetrain,
    onSuccess: () => {
      setRetrainSuccess(true);
      toast.success("Retrain triggered successfully");
      void queryClient.invalidateQueries({ queryKey: ["freqai", "status"] });
      setTimeout(() => setRetrainSuccess(false), 4000);
    },
    onError: (e: unknown) => {
      toast.error(`Retrain failed: ${String(e)}`);
    },
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="FreqAI Adaptive ML"
        description="Machine learning model status, accuracy metrics, and retraining controls."
        actions={
          <Button
            onClick={() => retrainMutation.mutate()}
            disabled={retrainMutation.isPending}
            size="sm"
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${retrainMutation.isPending ? "animate-spin" : ""}`}
            />
            {retrainMutation.isPending ? "Retraining…" : "Trigger Retrain"}
          </Button>
        }
      />

      {isLoading ? (
        <Card>
          <CardContent className="p-6 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : status ? (
        <>
          {!status.enabled && (
            <div className="rounded-md border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-700 dark:bg-yellow-950 dark:text-yellow-300">
              FreqAI is disabled. Set{" "}
              <code className="rounded bg-yellow-100 px-1 font-mono text-xs dark:bg-yellow-900">
                DHRUVA_FREQAI_ENABLED=true
              </code>{" "}
              in <code className="rounded bg-yellow-100 px-1 font-mono text-xs dark:bg-yellow-900">.env</code> to activate.
            </div>
          )}

          {retrainSuccess && (
            <div className="rounded-md border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-700 dark:bg-green-950 dark:text-green-300">
              Retrain triggered. The model will be updated in the background.
            </div>
          )}

          <Card>
            <CardContent className="p-6">
              <div className="mb-4 flex items-center gap-3">
                <BrainCircuit className="h-6 w-6 text-muted-foreground" />
                <h2 className="text-lg font-semibold">Model Status</h2>
                <Badge
                  variant={status.enabled ? "default" : "secondary"}
                  className={
                    status.enabled
                      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
                      : ""
                  }
                >
                  {status.enabled ? "Enabled" : "Disabled"}
                </Badge>
              </div>

              <dl className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Model Kind
                  </dt>
                  <dd className="mt-1 font-mono text-sm">{status.model_kind}</dd>
                </div>

                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Last Retrain
                  </dt>
                  <dd className="mt-1 text-sm">{formatRelative(status.last_retrain_at)}</dd>
                </div>

                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Next Retrain In
                  </dt>
                  <dd className="mt-1 text-sm">
                    {status.next_retrain_in_bars !== null
                      ? `${status.next_retrain_in_bars} bar${status.next_retrain_in_bars === 1 ? "" : "s"}`
                      : "N/A"}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Train Accuracy
                  </dt>
                  <dd className="mt-1 font-mono text-sm tabular-nums">
                    {formatAccuracy(status.train_accuracy)}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Test Accuracy
                  </dt>
                  <dd className="mt-1 font-mono text-sm tabular-nums">
                    {formatAccuracy(status.test_accuracy)}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Feature Count
                  </dt>
                  <dd className="mt-1 font-mono text-sm tabular-nums">{status.feature_count}</dd>
                </div>

                <div className="sm:col-span-2 lg:col-span-3">
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Model Directory
                  </dt>
                  <dd className="mt-1 break-all font-mono text-xs text-muted-foreground">
                    {status.model_dir}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
