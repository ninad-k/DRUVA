import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchInstruments } from "@/api/rest/endpoints";
import { cn } from "@/utils/cn";

/** Debounce helper that doesn't pull in lodash. */
function useDebounced<T>(value: T, delay = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

interface Props {
  onSelect?: (sym: string, exchange: string) => void;
  placeholder?: string;
  className?: string;
}

export function InstrumentSearch({ onSelect, placeholder = "Search NSE/BSE…", className }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const debouncedQ = useDebounced(q, 250);
  const ref = useRef<HTMLDivElement>(null);

  const { data = [], isFetching } = useQuery({
    queryKey: ["instruments-search", debouncedQ],
    queryFn: () => searchInstruments({ q: debouncedQ, exchange: "NSE", limit: 10 }),
    enabled: debouncedQ.length >= 2,
    staleTime: 60_000,
  });

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={ref} className={cn("relative w-full max-w-sm", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="pl-9"
      />
      {open && debouncedQ.length >= 2 && (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-md border border-border bg-popover shadow-lg">
          {isFetching && (
            <div className="px-3 py-2 text-xs text-muted-foreground">Searching…</div>
          )}
          {!isFetching && data.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">No matches.</div>
          )}
          {data.map((it) => (
            <button
              key={`${it.exchange}:${it.symbol}`}
              type="button"
              onClick={() => {
                onSelect?.(it.symbol, it.exchange);
                setQ("");
                setOpen(false);
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted/50"
            >
              <div>
                <p className="font-medium">{it.symbol}</p>
                <p className="text-xs text-muted-foreground">{it.name ?? it.segment}</p>
              </div>
              <span className="text-xs text-muted-foreground">{it.exchange}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
