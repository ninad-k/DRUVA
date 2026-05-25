import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Newspaper, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { listLatestNews, refreshNews } from "@/api/rest/endpoints";
import type { NewsItem } from "@/types/api";

// ---------- helpers ----------

function formatRelativeTime(iso: string): string {
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

type SentimentLabel = "negative" | "neutral" | "positive";

function sentimentVariant(label: SentimentLabel | null): {
  label: string;
  className: string;
} {
  if (label === "positive") return { label: "Positive", className: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" };
  if (label === "negative") return { label: "Negative", className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" };
  if (label === "neutral") return { label: "Neutral", className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" };
  return { label: "Unscored", className: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400" };
}

// ---------- sub-components ----------

interface NewsCardProps {
  item: NewsItem;
}

function NewsCard({ item }: NewsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { label, className } = sentimentVariant(item.sentiment_label);

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-2">
        {/* top row: sentiment badge + source + time */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={className}>{label}</Badge>
          <span className="text-xs text-muted-foreground">
            {item.source}
          </span>
          <span className="text-xs text-muted-foreground">·</span>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(item.published_at)}
          </span>
        </div>

        {/* headline */}
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm font-semibold leading-snug hover:underline"
        >
          {item.title}
        </a>

        {/* summary */}
        {item.summary && (
          <div>
            <p
              className={
                "text-sm text-muted-foreground leading-relaxed " +
                (!expanded ? "line-clamp-2" : "")
              }
            >
              {item.summary}
            </p>
            {item.summary.length > 120 && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="mt-0.5 text-xs text-primary hover:underline focus:outline-none"
              >
                {expanded ? "Show less" : "Read more"}
              </button>
            )}
          </div>
        )}

        {/* symbol chips */}
        {item.symbols.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {item.symbols.map((sym) => (
              <Badge key={sym} variant="secondary" className="text-xs px-1.5 py-0">
                {sym}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------- loading skeleton ----------

function NewsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-2">
            <div className="flex gap-2">
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-5 w-24" />
            </div>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------- page ----------

export function NewsPage() {
  const [symbolFilter, setSymbolFilter] = useState("");
  const queryClient = useQueryClient();

  const { data = [], isLoading } = useQuery<NewsItem[]>({
    queryKey: ["news", symbolFilter],
    queryFn: () =>
      listLatestNews({
        limit: 50,
        symbol: symbolFilter.trim() || undefined,
      }),
    refetchInterval: 60_000,
  });

  const { mutate: doRefresh, isPending: refreshing } = useMutation({
    mutationFn: refreshNews,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Market News"
        description="Latest market news with sentiment analysis."
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={() => doRefresh()}
            disabled={refreshing}
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* filters */}
      <div className="flex items-center gap-3">
        <Newspaper className="h-4 w-4 text-muted-foreground shrink-0" />
        <Input
          placeholder="Filter by symbol (e.g. RELIANCE)"
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          className="max-w-xs"
        />
        {!isLoading && (
          <span className="ml-auto text-xs text-muted-foreground">
            {data.length} article{data.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* content */}
      {isLoading ? (
        <NewsSkeleton />
      ) : data.length === 0 ? (
        <EmptyState
          icon={Newspaper}
          title="No news found"
          description={
            symbolFilter
              ? `No articles found for "${symbolFilter}". Try a different symbol or clear the filter.`
              : "No news articles are available. Click Refresh to fetch the latest news."
          }
        />
      ) : (
        <div className="space-y-3">
          {data.map((item) => (
            <NewsCard key={item.item_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
