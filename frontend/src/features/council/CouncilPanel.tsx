/**
 * Council panel — runs all investor personas in parallel against a single
 * symbol and shows the consensus verdict + per-persona signals + intrinsic
 * value (when fundamentals are available).
 *
 * API:
 *   GET  /api/v1/council/personas
 *   POST /api/v1/council/council               { symbol, question, personas? }
 *   POST /api/v1/council/dcf                   { symbol, ...assumptions }
 */

import { useEffect, useState } from "react";

import { SymbolPicker, type PickedSymbol } from "./SymbolPicker";

const API_BASE = "/api/v1/council";

type PersonaOut = {
  slug: string;
  display_name: string;
  style: string;
  checklist: string[];
};

type PersonaSignalOut = {
  persona_slug: string;
  persona_display_name: string;
  signal: "bullish" | "bearish" | "neutral";
  confidence: number;
  reasoning: string;
  answer: string;
  risk_level: string;
};

type CouncilOut = {
  symbol: string;
  consensus: "bullish" | "bearish" | "neutral";
  consensus_confidence: number;
  vote_distribution: Record<string, number>;
  verdicts: PersonaSignalOut[];
  fundamentals: Record<string, unknown>;
  intrinsic_value: {
    intrinsic_value_total: number;
    intrinsic_value_per_share: number | null;
    margin_of_safety_pct: number | null;
    owner_earnings: number;
    degraded: boolean;
  } | null;
  notes: string;
  as_of: string;
};

const SIGNAL_COLORS: Record<string, string> = {
  bullish: "text-emerald-600 dark:text-emerald-400",
  bearish: "text-rose-600 dark:text-rose-400",
  neutral: "text-amber-600 dark:text-amber-400",
};

const SIGNAL_BG: Record<string, string> = {
  bullish: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-300 dark:border-emerald-800",
  bearish: "bg-rose-50 dark:bg-rose-950/40 border-rose-300 dark:border-rose-800",
  neutral: "bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-800",
};

export function CouncilPanel() {
  const [picked, setPicked] = useState<PickedSymbol | null>(null);
  const [question, setQuestion] = useState(
    "Should we own this stock in the current market regime?",
  );
  const [personas, setPersonas] = useState<PersonaOut[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<CouncilOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/personas`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: PersonaOut[]) => {
        setPersonas(data);
        setSelected(new Set(data.map((p) => p.slug)));
      })
      .catch(() => setPersonas([]));
  }, []);

  async function run() {
    if (!picked) {
      setError("Pick a symbol first — start typing to search NSE/BSE instruments.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await fetch(`${API_BASE}/council`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: picked.symbol,
          exchange: picked.exchange,
          question,
          personas: Array.from(selected),
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Council request failed (${resp.status}): ${text}`);
      }
      const data: CouncilOut = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function togglePersona(slug: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-6 shadow-sm dark:border-amber-900/40 dark:bg-slate-900">
      <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
        Investor Council
      </h2>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
        Ask the same question to multiple legendary investors. See where they agree, where they
        diverge, and what the weighted consensus signal is.
      </p>

      {/* Inputs */}
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_2fr_auto]">
        <SymbolPicker
          value={picked}
          onChange={setPicked}
          placeholder="Symbol (e.g. HDFCBANK)"
        />
        <input
          type="text"
          placeholder="Question for the Council"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <button
          onClick={run}
          disabled={loading || !picked}
          className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {loading ? "Asking…" : "Convene Council"}
        </button>
      </div>

      {/* Persona toggles */}
      {personas.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {personas.map((p) => {
            const on = selected.has(p.slug);
            return (
              <button
                key={p.slug}
                onClick={() => togglePersona(p.slug)}
                title={p.style}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  on
                    ? "border-amber-500 bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100"
                    : "border-slate-300 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
                }`}
              >
                {p.display_name}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Consensus card */}
      {result && (
        <div className="mt-6 space-y-4">
          <div className={`rounded-xl border p-4 ${SIGNAL_BG[result.consensus]}`}>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Consensus for {result.symbol}
                </div>
                <div className={`mt-1 text-2xl font-bold capitalize ${SIGNAL_COLORS[result.consensus]}`}>
                  {result.consensus} · {result.consensus_confidence.toFixed(0)}% confidence
                </div>
              </div>
              <div className="text-right text-xs text-slate-600 dark:text-slate-400">
                <div>Bullish: {result.vote_distribution.bullish ?? 0}</div>
                <div>Bearish: {result.vote_distribution.bearish ?? 0}</div>
                <div>Neutral: {result.vote_distribution.neutral ?? 0}</div>
              </div>
            </div>
            {result.notes && (
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">{result.notes}</p>
            )}
          </div>

          {/* Intrinsic value */}
          {result.intrinsic_value && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Three-stage DCF intrinsic value
                {result.intrinsic_value.degraded && " (degraded — only ratios available)"}
              </div>
              <div className="mt-1 grid grid-cols-2 gap-2 text-sm text-slate-700 dark:text-slate-300 md:grid-cols-4">
                <div>
                  <div className="font-medium">Total</div>
                  <div>₹{Math.round(result.intrinsic_value.intrinsic_value_total).toLocaleString("en-IN")}</div>
                </div>
                {result.intrinsic_value.intrinsic_value_per_share != null && (
                  <div>
                    <div className="font-medium">Per share</div>
                    <div>₹{result.intrinsic_value.intrinsic_value_per_share.toFixed(2)}</div>
                  </div>
                )}
                {result.intrinsic_value.margin_of_safety_pct != null && (
                  <div>
                    <div className="font-medium">Margin of safety</div>
                    <div
                      className={
                        result.intrinsic_value.margin_of_safety_pct >= 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-rose-600 dark:text-rose-400"
                      }
                    >
                      {result.intrinsic_value.margin_of_safety_pct.toFixed(1)}%
                    </div>
                  </div>
                )}
                <div>
                  <div className="font-medium">Owner earnings</div>
                  <div>₹{Math.round(result.intrinsic_value.owner_earnings).toLocaleString("en-IN")}</div>
                </div>
              </div>
            </div>
          )}

          {/* Per-persona verdicts */}
          <div className="grid gap-3 md:grid-cols-2">
            {result.verdicts.map((v) => (
              <div
                key={v.persona_slug}
                className={`rounded-xl border p-4 ${SIGNAL_BG[v.signal]}`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    {v.persona_display_name}
                  </div>
                  <div className={`text-sm font-medium capitalize ${SIGNAL_COLORS[v.signal]}`}>
                    {v.signal} · {v.confidence}%
                  </div>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
                  {v.reasoning}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
