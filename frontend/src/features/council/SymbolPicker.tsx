import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { searchInstruments } from "@/api/rest/endpoints";
import type { InstrumentSearchResult } from "@/types/api";
import { cn } from "@/utils/cn";

function useDebounced<T>(value: T, delay = 200): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export interface PickedSymbol {
  symbol: string;
  exchange: string;
  name?: string;
  segment?: string;
}

interface Props {
  value: PickedSymbol | null;
  onChange: (s: PickedSymbol | null) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Symbol typeahead backed by /v1/instruments/search.
 *
 * Different from the topbar's InstrumentSearch in that it keeps the picked
 * value visible (as a chip) and emits both symbol + exchange so callers
 * don't have to guess the segment.
 */
export function SymbolPicker({ value, onChange, placeholder = "Search NSE/BSE…", className }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const debouncedQ = useDebounced(q, 200);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: results = [], isFetching } = useQuery({
    queryKey: ["symbol-picker", debouncedQ],
    queryFn: () => searchInstruments({ q: debouncedQ, limit: 12 }),
    enabled: debouncedQ.trim().length >= 1,
    staleTime: 60_000,
  });

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onMouseDown);
    return () => window.removeEventListener("mousedown", onMouseDown);
  }, []);

  useEffect(() => {
    setHighlight(0);
  }, [debouncedQ]);

  function pick(item: InstrumentSearchResult) {
    onChange({
      symbol: item.symbol,
      exchange: item.exchange,
      name: item.name,
      segment: item.segment,
    });
    setQ("");
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, Math.max(0, results.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && results[highlight]) {
      e.preventDefault();
      pick(results[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  if (value) {
    return (
      <div
        className={cn(
          "flex items-center justify-between gap-2 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-sm dark:border-amber-700/60 dark:bg-amber-950/30",
          className,
        )}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">
              {value.symbol}
            </span>
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              {value.exchange}
            </span>
          </div>
          {(value.name || value.segment) && (
            <p className="truncate text-xs text-slate-600 dark:text-slate-400">
              {value.name ?? value.segment}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => onChange(null)}
          className="rounded p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-slate-100"
          aria-label="Clear symbol"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div ref={boxRef} className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={inputRef}
        type="text"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-full rounded-md border border-slate-300 bg-white py-2 pl-9 pr-9 text-sm focus:border-amber-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
      />
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />

      {open && debouncedQ.trim().length >= 1 && (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {isFetching && (
            <div className="px-3 py-2 text-xs text-muted-foreground">Searching…</div>
          )}
          {!isFetching && results.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              No instrument matches “{debouncedQ}”. Try a longer prefix (e.g. HDFCBANK).
            </div>
          )}
          {results.map((it, idx) => (
            <button
              key={`${it.exchange}:${it.symbol}`}
              type="button"
              onMouseEnter={() => setHighlight(idx)}
              onClick={() => pick(it)}
              className={cn(
                "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm",
                idx === highlight
                  ? "bg-amber-100 dark:bg-amber-900/30"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800",
              )}
            >
              <div className="min-w-0">
                <p className="truncate font-mono font-medium text-slate-900 dark:text-slate-100">
                  {it.symbol}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {it.name ?? it.segment ?? it.instrument_type ?? ""}
                </p>
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                  {it.exchange}
                </span>
                {idx === highlight && <Check className="h-3 w-3" />}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
