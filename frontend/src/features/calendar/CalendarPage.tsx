import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { listCalendarEvents } from "@/api/rest/endpoints";
import type { CalendarEvent, CalendarEventKind } from "@/types/api";

function toDateString(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function defaultSince(): string {
  return toDateString(new Date());
}

function defaultUntil(): string {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  return toDateString(d);
}

type BadgeVariant = "default" | "secondary" | "destructive" | "outline";

interface KindStyle {
  label: string;
  className: string;
  variant: BadgeVariant;
}

const KIND_STYLES: Record<CalendarEventKind, KindStyle> = {
  rbi_policy:           { label: "RBI Policy",       className: "bg-blue-100 text-blue-800 border-blue-200",   variant: "outline" },
  earnings:             { label: "Earnings",          className: "bg-green-100 text-green-800 border-green-200", variant: "outline" },
  dividend_ex_date:     { label: "Dividend",          className: "bg-yellow-100 text-yellow-800 border-yellow-200", variant: "outline" },
  fno_expiry:           { label: "F&O Expiry",        className: "bg-red-100 text-red-800 border-red-200",      variant: "outline" },
  ipo:                  { label: "IPO",               className: "bg-purple-100 text-purple-800 border-purple-200", variant: "outline" },
  bonus:                { label: "Bonus",             className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  split:                { label: "Split",             className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  agm:                  { label: "AGM",               className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  index_rebalance:      { label: "Index Rebalance",   className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  buyback:              { label: "Buyback",           className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  result_announcement:  { label: "Result",            className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
  circuit_filter_change:{ label: "Circuit Filter",    className: "bg-gray-100 text-gray-700 border-gray-200",   variant: "outline" },
};

function KindBadge({ kind }: { kind: CalendarEventKind }) {
  const style = KIND_STYLES[kind] ?? {
    label: kind,
    className: "bg-gray-100 text-gray-700 border-gray-200",
    variant: "outline" as BadgeVariant,
  };
  return (
    <Badge variant={style.variant} className={style.className}>
      {style.label}
    </Badge>
  );
}

function EventCard({ event }: { event: CalendarEvent }) {
  return (
    <div className="flex flex-wrap items-start gap-3 rounded-md border border-border bg-card px-4 py-3">
      <div className="mt-0.5 shrink-0">
        <KindBadge kind={event.kind} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium leading-snug">{event.title}</p>
        {event.symbol && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            {event.symbol}
            {event.exchange ? <span className="ml-1">· {event.exchange}</span> : null}
          </p>
        )}
        {event.detail && (
          <p className="mt-1 text-sm text-muted-foreground">{event.detail}</p>
        )}
      </div>
    </div>
  );
}

function formatDisplayDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function CalendarPage() {
  const [since, setSince] = useState<string>(defaultSince);
  const [until, setUntil] = useState<string>(defaultUntil);
  const [symbol, setSymbol] = useState<string>("");

  const params = useMemo(
    () => ({
      since: since || undefined,
      until: until || undefined,
      symbol: symbol.trim() || undefined,
    }),
    [since, until, symbol],
  );

  const { data, isLoading, error } = useQuery({
    queryKey: ["calendar-events", params.since, params.until, params.symbol],
    queryFn: () => listCalendarEvents(params),
  });

  const isProviderNull =
    error != null &&
    (error as { response?: { status?: number } })?.response?.status === 501;

  const grouped = useMemo<Map<string, CalendarEvent[]>>(() => {
    if (!data) return new Map();
    const map = new Map<string, CalendarEvent[]>();
    for (const ev of data) {
      const bucket = map.get(ev.occurs_on) ?? [];
      bucket.push(ev);
      map.set(ev.occurs_on, bucket);
    }
    return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
  }, [data]);

  const totalCount = data?.length ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Economic & Corporate Calendar"
        description="Upcoming market events, results, policy meetings and expiries."
      />

      <Card>
        <CardContent className="p-4">
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="flex items-center gap-1 text-primary">
              <CalendarDays className="h-4 w-4" />
            </div>
            <div>
              <Label htmlFor="cal-since">From</Label>
              <input
                id="cal-since"
                type="date"
                value={since}
                onChange={(e) => setSince(e.target.value)}
                className="mt-1 block rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <Label htmlFor="cal-until">To</Label>
              <input
                id="cal-until"
                type="date"
                value={until}
                onChange={(e) => setUntil(e.target.value)}
                className="mt-1 block rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="w-44">
              <Label htmlFor="cal-symbol">Symbol (optional)</Label>
              <Input
                id="cal-symbol"
                placeholder="e.g. RELIANCE"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </div>
            {!isLoading && data && (
              <span className="ml-auto text-xs text-muted-foreground">
                {totalCount} event{totalCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {isProviderNull ? (
            <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
              <p className="font-medium">Calendar provider not configured.</p>
              <p className="mt-1 text-blue-700">
                Set <code className="font-mono">DHRUVA_CALENDAR_PROVIDER=http</code> or{" "}
                <code className="font-mono">static</code> in <code className="font-mono">.env</code> to enable.
              </p>
            </div>
          ) : isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : grouped.size === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No events found"
              description="No calendar events match the selected date range and filters."
            />
          ) : (
            <div className="space-y-6">
              {Array.from(grouped.entries()).map(([date, events]) => (
                <div key={date}>
                  <p className="mb-2 text-sm font-semibold text-foreground">
                    {formatDisplayDate(date)}
                  </p>
                  <div className="space-y-2">
                    {events.map((ev) => (
                      <EventCard key={ev.event_id} event={ev} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
