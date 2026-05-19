import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bot, Send, TrendingDown, TrendingUp, Minus } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AdvisorApiResponse {
  answer: string;
  recommended_actions: string[];
  risk_level: "Low" | "Medium" | "High";
  confidence: number;
  sources: string[];
}

interface SentimentApiResponse {
  score: number;
  label: string;
  vix: number;
  pcr: number;
  fii_net_cr: number;
  dii_net_cr: number;
  advance_decline: number;
  regime: string;
  signals: Record<string, number>;
  as_of: string;
}

interface RegimeApiResponse {
  regime: string;
  confidence: number;
  sentiment_score: number;
  sentiment_label: string;
  suggested_equity_pct: number;
  suggested_cash_pct: number;
  regime_description: string;
}

interface DailyBriefingApiResponse {
  briefing: string;
  regime: string;
  sentiment_score: number;
  sentiment_label: string;
}

type MessageRole = "user" | "assistant" | "system";

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  recommended_actions?: string[];
  risk_level?: "Low" | "Medium" | "High";
  confidence?: number;
  sources?: string[];
  timestamp: Date;
}

interface AiAdvisorPanelProps {
  accountId: string;
}

// ---------------------------------------------------------------------------
// Constants & helpers
// ---------------------------------------------------------------------------

const API_BASE = "/api/v1/ai-advisor";

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function regimeBadgeClass(regime: string): string {
  switch (regime) {
    case "Bull":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "Euphoria":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-400/40";
    case "Neutral":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "Bear":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    case "Crash":
      return "bg-red-600/20 text-red-300 border-red-500/40";
    default:
      return "bg-zinc-700 text-zinc-300";
  }
}

function riskBadgeClass(risk: "Low" | "Medium" | "High"): string {
  switch (risk) {
    case "Low":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "Medium":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "High":
      return "bg-red-500/15 text-red-400 border-red-500/30";
  }
}

function sentimentGaugeColor(score: number): string {
  if (score <= -60) return "text-red-400";
  if (score <= -20) return "text-orange-400";
  if (score <= 20)  return "text-amber-400";
  if (score <= 60)  return "text-lime-400";
  return "text-emerald-400";
}

function SentimentBar({ score }: { score: number }) {
  // Map score from [-100, 100] to [0, 100]% for CSS
  const pct = ((score + 100) / 200) * 100;
  const clampedPct = Math.max(0, Math.min(100, pct));
  const color =
    score <= -60 ? "bg-red-500"
    : score <= -20 ? "bg-orange-500"
    : score <= 20  ? "bg-amber-500"
    : score <= 60  ? "bg-lime-500"
    : "bg-emerald-500";

  return (
    <div className="relative h-2 w-full rounded-full bg-zinc-700">
      <div
        className={`absolute left-0 top-0 h-2 rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${clampedPct}%` }}
      />
      {/* Center marker */}
      <div className="absolute left-1/2 top-0 h-2 w-px -translate-x-px bg-zinc-500" />
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block h-2 w-2 rounded-full bg-amber-400 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  );
}

function UserMessage({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-amber-500/20 border border-amber-500/30 px-4 py-2.5">
        <p className="text-sm text-zinc-100">{msg.content}</p>
        <p className="mt-1 text-right text-[10px] text-zinc-500">
          {msg.timestamp.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}

function AssistantMessage({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex gap-2.5">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/20 border border-amber-500/30">
        <Bot className="h-4 w-4 text-amber-400" />
      </div>
      <div className="flex-1 space-y-2">
        <div className="rounded-2xl rounded-tl-sm bg-zinc-800 border border-zinc-700 px-4 py-3">
          <p className="text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap">{msg.content}</p>

          {msg.recommended_actions && msg.recommended_actions.length > 0 && (
            <div className="mt-3 space-y-1.5 border-t border-zinc-700 pt-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-400">
                Recommended Actions
              </p>
              <ul className="space-y-1">
                {msg.recommended_actions.map((action, idx) => (
                  <li key={idx} className="flex gap-2 text-sm text-zinc-300">
                    <span className="mt-0.5 shrink-0 text-amber-400">•</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(msg.risk_level || msg.confidence != null) && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-700 pt-3">
              {msg.risk_level && (
                <Badge
                  variant="outline"
                  className={`text-[10px] ${riskBadgeClass(msg.risk_level)}`}
                >
                  Risk: {msg.risk_level}
                </Badge>
              )}
              {msg.confidence != null && (
                <span className="text-[11px] text-zinc-500">
                  Confidence: {Math.round((msg.confidence ?? 0) * 100)}%
                </span>
              )}
              {msg.sources && msg.sources.length > 0 && (
                <span className="text-[11px] text-zinc-500">
                  Sources: {msg.sources.join(", ")}
                </span>
              )}
            </div>
          )}
        </div>
        <p className="pl-1 text-[10px] text-zinc-600">
          {msg.timestamp.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}

function SystemMessage({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex justify-center">
      <div className="rounded-full bg-zinc-800 border border-zinc-700 px-3 py-1">
        <p className="text-[11px] text-zinc-500 whitespace-pre-wrap">{msg.content}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function AiAdvisorPanel({ accountId }: AiAdvisorPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: genId(),
      role: "assistant",
      content:
        "Hello! I'm DRUVA's AI Portfolio Advisor — powered by Claude. I have full visibility into your current positions, market regime, and sentiment signals.\n\nAsk me anything about your portfolio, or use the quick actions below.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [sentiment, setSentiment] = useState<SentimentApiResponse | null>(null);
  const [regime, setRegime] = useState<RegimeApiResponse | null>(null);
  const [sentimentLoading, setSentimentLoading] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  // Load sentiment and regime on mount
  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/sentiment`).then((r) => (r.ok ? r.json() : null)),
      fetch(`${API_BASE}/regime-status`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([s, r]) => {
        if (s) setSentiment(s as SentimentApiResponse);
        if (r) setRegime(r as RegimeApiResponse);
      })
      .catch(() => {/* silently ignore — fallback UI shown */})
      .finally(() => setSentimentLoading(false));
  }, [accountId]);

  // ---------------------------------------------------------------------------
  // API calls
  // ---------------------------------------------------------------------------

  async function callAsk(question: string): Promise<AdvisorApiResponse> {
    const resp = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`);
    }
    return resp.json() as Promise<AdvisorApiResponse>;
  }

  async function callDailyBriefing(): Promise<DailyBriefingApiResponse> {
    const resp = await fetch(`${API_BASE}/daily-briefing`);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    return resp.json() as Promise<DailyBriefingApiResponse>;
  }

  async function callRebalanceSuggest(): Promise<AdvisorApiResponse> {
    const resp = await fetch(`${API_BASE}/rebalance-suggest`, { method: "POST" });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    return resp.json() as Promise<AdvisorApiResponse>;
  }

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function appendUserMessage(text: string): void {
    setMessages((prev) => [
      ...prev,
      {
        id: genId(),
        role: "user",
        content: text,
        timestamp: new Date(),
      },
    ]);
  }

  function appendAssistantMessage(data: AdvisorApiResponse): void {
    setMessages((prev) => [
      ...prev,
      {
        id: genId(),
        role: "assistant",
        content: data.answer,
        recommended_actions: data.recommended_actions,
        risk_level: data.risk_level,
        confidence: data.confidence,
        sources: data.sources,
        timestamp: new Date(),
      },
    ]);
  }

  function appendErrorMessage(error: string): void {
    setMessages((prev) => [
      ...prev,
      {
        id: genId(),
        role: "system",
        content: `Error: ${error}`,
        timestamp: new Date(),
      },
    ]);
  }

  async function handleSend(): Promise<void> {
    const text = input.trim();
    if (!text || isThinking) return;

    setInput("");
    appendUserMessage(text);
    setIsThinking(true);

    try {
      const response = await callAsk(text);
      appendAssistantMessage(response);
    } catch (err) {
      appendErrorMessage(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsThinking(false);
      inputRef.current?.focus();
    }
  }

  async function handleDailyBriefing(): Promise<void> {
    if (isThinking) return;
    appendUserMessage("Give me today's market briefing.");
    setIsThinking(true);

    try {
      const data = await callDailyBriefing();
      setMessages((prev) => [
        ...prev,
        {
          id: genId(),
          role: "assistant",
          content: data.briefing,
          timestamp: new Date(),
        },
      ]);
    } catch (err) {
      appendErrorMessage(err instanceof Error ? err.message : "Failed to fetch briefing");
    } finally {
      setIsThinking(false);
    }
  }

  async function handleSuggestRebalance(): Promise<void> {
    if (isThinking) return;
    appendUserMessage("Suggest a rebalancing plan for my portfolio.");
    setIsThinking(true);

    try {
      const response = await callRebalanceSuggest();
      appendAssistantMessage(response);
    } catch (err) {
      appendErrorMessage(err instanceof Error ? err.message : "Failed to fetch rebalance suggestions");
    } finally {
      setIsThinking(false);
    }
  }

  async function handleCheckSentiment(): Promise<void> {
    if (isThinking) return;
    appendUserMessage("What's the current market sentiment?");
    setIsThinking(true);

    try {
      // Refresh sentiment data and compose a message from it
      const [fresh, freshRegime] = await Promise.all([
        fetch(`${API_BASE}/sentiment`).then((r) => r.json() as Promise<SentimentApiResponse>),
        fetch(`${API_BASE}/regime-status`).then((r) => r.json() as Promise<RegimeApiResponse>),
      ]);
      setSentiment(fresh);
      setRegime(freshRegime);

      const content =
        `Market Sentiment: ${fresh.label} (${fresh.score > 0 ? "+" : ""}${fresh.score.toFixed(1)})\n\n` +
        `• India VIX: ${fresh.vix.toFixed(1)} | PCR: ${fresh.pcr.toFixed(2)}\n` +
        `• FII net: ₹${(fresh.fii_net_cr / 100).toFixed(0)}Cr | DII net: ₹${(fresh.dii_net_cr / 100).toFixed(0)}Cr\n` +
        `• Advance/Decline: ${(fresh.advance_decline * 100).toFixed(0)}% advances\n` +
        `• Regime: ${freshRegime.regime} — Suggested equity: ${freshRegime.suggested_equity_pct}%, cash: ${freshRegime.suggested_cash_pct}%\n\n` +
        freshRegime.regime_description;

      setMessages((prev) => [
        ...prev,
        {
          id: genId(),
          role: "assistant",
          content,
          timestamp: new Date(),
        },
      ]);
    } catch (err) {
      appendErrorMessage(err instanceof Error ? err.message : "Failed to fetch sentiment");
    } finally {
      setIsThinking(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const regimeLabel = regime?.regime ?? sentiment?.regime ?? "—";
  const sentimentScore = sentiment?.score ?? 0;
  const sentimentLabel = sentiment?.label ?? "—";

  return (
    <Card className="flex h-[700px] flex-col bg-zinc-900 border-zinc-800">
      {/* ---- Header ---- */}
      <CardHeader className="shrink-0 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/20 border border-amber-500/30">
              <Bot className="h-4.5 w-4.5 text-amber-400" />
            </div>
            <div>
              <CardTitle className="text-sm font-semibold text-zinc-100">
                AI Portfolio Advisor
              </CardTitle>
              <p className="text-[11px] text-zinc-500">Powered by Claude · Indian markets</p>
            </div>
          </div>

          {/* Regime + Sentiment badges */}
          <div className="flex items-center gap-2">
            {sentimentLoading ? (
              <span className="text-xs text-zinc-600">Loading…</span>
            ) : (
              <>
                <Badge
                  variant="outline"
                  className={`text-[11px] ${regimeBadgeClass(regimeLabel)}`}
                >
                  {regimeLabel === "Bull" && <TrendingUp className="mr-1 h-3 w-3" />}
                  {regimeLabel === "Bear" || regimeLabel === "Crash" ? (
                    <TrendingDown className="mr-1 h-3 w-3" />
                  ) : null}
                  {regimeLabel === "Neutral" && <Minus className="mr-1 h-3 w-3" />}
                  {regimeLabel}
                </Badge>
                <div className="flex flex-col items-end gap-1 min-w-[100px]">
                  <span
                    className={`text-[11px] font-mono font-semibold ${sentimentGaugeColor(sentimentScore)}`}
                  >
                    {sentimentScore > 0 ? "+" : ""}
                    {sentimentScore.toFixed(0)} {sentimentLabel}
                  </span>
                  <SentimentBar score={sentimentScore} />
                </div>
              </>
            )}
          </div>
        </div>
      </CardHeader>

      {/* ---- Chat area ---- */}
      <ScrollArea className="flex-1 px-4 py-3">
        <div className="space-y-4">
          {messages.map((msg) => {
            if (msg.role === "user") return <UserMessage key={msg.id} msg={msg} />;
            if (msg.role === "assistant") return <AssistantMessage key={msg.id} msg={msg} />;
            return <SystemMessage key={msg.id} msg={msg} />;
          })}

          {isThinking && (
            <div className="flex gap-2.5">
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/20 border border-amber-500/30">
                <Bot className="h-4 w-4 text-amber-400" />
              </div>
              <div className="rounded-2xl rounded-tl-sm bg-zinc-800 border border-zinc-700 px-4 py-3">
                <ThinkingIndicator />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* ---- Quick actions ---- */}
      <div className="shrink-0 border-t border-zinc-800 px-4 py-2">
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 border-zinc-700 bg-zinc-800/50 text-xs text-zinc-300 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-300"
            onClick={() => void handleDailyBriefing()}
            disabled={isThinking}
          >
            Daily Briefing
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 border-zinc-700 bg-zinc-800/50 text-xs text-zinc-300 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-300"
            onClick={() => void handleSuggestRebalance()}
            disabled={isThinking}
          >
            Suggest Rebalance
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 border-zinc-700 bg-zinc-800/50 text-xs text-zinc-300 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-300"
            onClick={() => void handleCheckSentiment()}
            disabled={isThinking}
          >
            Check Sentiment
          </Button>
        </div>
      </div>

      {/* ---- Input ---- */}
      <div className="shrink-0 border-t border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your portfolio, a stock, or market conditions…"
            className="flex-1 border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus-visible:ring-amber-500/30"
            disabled={isThinking}
          />
          <Button
            size="icon"
            onClick={() => void handleSend()}
            disabled={!input.trim() || isThinking}
            className="shrink-0 bg-amber-500 text-zinc-900 hover:bg-amber-400 disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-zinc-600">
          Not SEBI-registered investment advice. For informational purposes only.
        </p>
      </div>
    </Card>
  );
}
