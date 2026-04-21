import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { cn } from "@/utils/cn";
import { getMarketCycleCurrent } from "@/api/rest/endpoints";

const REGIME_META: Record<
  string,
  { label: string; color: string; description: string }
> = {
  bull: {
    label: "Bull",
    color: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
    description: "Risk-on. Deploy capital aggressively.",
  },
  neutral: {
    label: "Neutral",
    color: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
    description: "Stock-pickers market. Be selective.",
  },
  bear: {
    label: "Bear",
    color: "bg-red-500/15 text-red-300 ring-red-500/30",
    description: "Reduce exposure. Preserve capital.",
  },
};

export function MarketCycleBanner() {
  const { data } = useQuery({
    queryKey: ["market-cycle", "current"],
    queryFn: getMarketCycleCurrent,
    refetchInterval: 60_000,
  });
  if (!data) return null;

  const meta = REGIME_META[data.regime] ?? REGIME_META.neutral;
  return (
    <div
      className={cn(
        "mb-4 flex items-center justify-between rounded-md border px-4 py-2 text-sm ring-1",
        meta.color,
      )}
    >
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4" />
        <span className="font-semibold uppercase tracking-wider">{meta.label}</span>
        <span className="text-xs opacity-80">— {meta.description}</span>
      </div>
      <div className="flex items-center gap-4 text-xs opacity-90">
        <span>
          Nifty 18m ROC:{" "}
          <span className="font-mono tabular-nums">
            {data.nifty_roc_18m !== null ? data.nifty_roc_18m.toFixed(2) + "%" : "—"}
          </span>
        </span>
        <span>
          SmallCap 20m ROC:{" "}
          <span className="font-mono tabular-nums">
            {data.smallcap_roc_20m !== null
              ? data.smallcap_roc_20m.toFixed(2) + "%"
              : "—"}
          </span>
        </span>
        <span>
          Alloc:{" "}
          <span className="font-mono tabular-nums">
            {data.suggested_allocation_pct.toFixed(0)}%
          </span>
        </span>
      </div>
    </div>
  );
}
