import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { AiAdvisorPanel } from "../AiAdvisorPanel";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SENTIMENT = {
  score: 42,
  label: "Cautiously Bullish",
  vix: 14.2,
  pcr: 0.9,
  fii_net_cr: 25000,
  dii_net_cr: 10000,
  advance_decline: 0.6,
  regime: "Bull",
  signals: { vix: 0.6, fii: 0.5, pcr: 0.4, regime: 0.8, ad_ratio: 0.6 },
  as_of: "2024-06-01T10:00:00Z",
};

const REGIME = {
  regime: "Bull",
  confidence: 0.8,
  sentiment_score: 42,
  sentiment_label: "Cautiously Bullish",
  suggested_equity_pct: 80,
  suggested_cash_pct: 20,
  regime_description: "Trend is up; stay invested.",
};

const ASK = {
  answer: "Based on current Bull regime, maintain 80% equity allocation.",
  recommended_actions: ["Hold NIFTYBEES", "Add GOLDBEES on dips"],
  risk_level: "Medium",
  confidence: 0.85,
  sources: ["regime", "sentiment"],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function res(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

type Routes = Record<string, () => Response | Promise<Response>>;

// Routes keyed by "METHOD path-suffix"; defaults give a healthy backend.
function installFetch(overrides: Routes = {}) {
  const routes: Routes = {
    "GET /sentiment": () => res(SENTIMENT),
    "GET /regime-status": () => res(REGIME),
    "POST /ask": () => res(ASK),
    "GET /daily-briefing": () =>
      res({ briefing: "Markets opened flat.", regime: "Bull", sentiment_score: 42, sentiment_label: "x" }),
    "POST /rebalance-suggest": () => res(ASK),
    ...overrides,
  };
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = url.replace("/api/v1/ai-advisor", "");
    const handler = routes[`${method} ${path}`];
    if (!handler) throw new Error(`Unmocked ${method} ${url}`);
    return handler();
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const callsTo = (fn: ReturnType<typeof installFetch>, method: string, path: string) =>
  fn.mock.calls.filter(
    ([u, i]) => u === `/api/v1/ai-advisor${path}` && ((i as RequestInit | undefined)?.method ?? "GET") === method,
  );

const input = () => screen.getByPlaceholderText(/Ask about your portfolio/);
const sendButton = () => {
  // The send button is the only icon button (no accessible name) in the input row.
  const buttons = screen.getAllByRole("button");
  return buttons[buttons.length - 1];
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AiAdvisorPanel", () => {
  beforeEach(() => {
    // jsdom does not implement scrollIntoView; the panel auto-scrolls on new messages.
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the title, greeting and quick actions", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    expect(screen.getByText("AI Portfolio Advisor")).toBeInTheDocument();
    expect(screen.getByText(/I'm DRUVA's AI Portfolio Advisor/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Daily Briefing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suggest Rebalance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check Sentiment" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
  });

  it("shows a loading indicator until sentiment resolves", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    expect(screen.getByText("Loading…")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
  });

  it("fetches sentiment and regime on mount and renders the gauge", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    expect(await screen.findByText("+42 Cautiously Bullish")).toBeInTheDocument();
    expect(callsTo(fetchFn, "GET", "/sentiment")).toHaveLength(1);
    expect(callsTo(fetchFn, "GET", "/regime-status")).toHaveLength(1);
  });

  it("shows the Bull regime badge", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    expect(await screen.findByText("Bull")).toBeInTheDocument();
  });

  it("falls back to placeholders when the sentiment endpoints return errors", async () => {
    installFetch({
      "GET /sentiment": () => res({}, false, 500),
      "GET /regime-status": () => res({}, false, 500),
    });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
    expect(screen.getByText("0 —")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("falls back to placeholders when the sentiment fetch rejects", async () => {
    installFetch({
      "GET /sentiment": () => Promise.reject(new Error("offline")),
    });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
    expect(screen.getByText("AI Portfolio Advisor")).toBeInTheDocument();
  });

  it("uses the sentiment regime when regime-status is unavailable", async () => {
    installFetch({ "GET /regime-status": () => res({}, false, 503) });
    render(<AiAdvisorPanel accountId="acc-1" />);

    expect(await screen.findByText("Bull")).toBeInTheDocument();
  });

  it("disables Send for empty input and enables it once text is typed", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());

    expect(sendButton()).toBeDisabled();
    await userEvent.type(input(), "   ");
    expect(sendButton()).toBeDisabled();
    await userEvent.type(input(), "hi");
    expect(sendButton()).toBeEnabled();
  });

  it("POSTs the question to /ask when Send is clicked", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Should I rebalance?");
    await userEvent.click(sendButton());

    await waitFor(() => expect(callsTo(fetchFn, "POST", "/ask")).toHaveLength(1));
    const init = callsTo(fetchFn, "POST", "/ask")[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ question: "Should I rebalance?" });
  });

  it("shows the user message and the assistant response in the thread", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Should I rebalance?");
    await userEvent.click(sendButton());

    expect(screen.getByText("Should I rebalance?")).toBeInTheDocument();
    expect(await screen.findByText(ASK.answer)).toBeInTheDocument();
    expect(screen.getByText("Recommended Actions")).toBeInTheDocument();
    expect(screen.getByText("Hold NIFTYBEES")).toBeInTheDocument();
    expect(screen.getByText("Risk: Medium")).toBeInTheDocument();
    expect(screen.getByText("Confidence: 85%")).toBeInTheDocument();
    expect(screen.getByText("Sources: regime, sentiment")).toBeInTheDocument();
  });

  it("clears the input after sending", async () => {
    installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Hello");
    await userEvent.click(sendButton());

    expect(input()).toHaveValue("");
    await screen.findByText(ASK.answer);
  });

  it("sends on Enter", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Via enter{Enter}");

    await waitFor(() => expect(callsTo(fetchFn, "POST", "/ask")).toHaveLength(1));
    await screen.findByText(ASK.answer);
  });

  it("shows a thinking state and blocks input while awaiting a response", async () => {
    let resolve!: (r: Response) => void;
    installFetch({ "POST /ask": () => new Promise<Response>((r) => (resolve = r)) });
    const { container } = render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Slow question");
    await userEvent.click(sendButton());

    await waitFor(() => expect(container.querySelectorAll(".animate-bounce")).toHaveLength(3));
    expect(input()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Daily Briefing" })).toBeDisabled();

    resolve(res(ASK));
    await screen.findByText(ASK.answer);
    expect(container.querySelectorAll(".animate-bounce")).toHaveLength(0);
    expect(input()).toBeEnabled();
  });

  it("shows the server's detail message as a system error on ask failure", async () => {
    installFetch({ "POST /ask": () => res({ detail: "Rate limited" }, false, 429) });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Question");
    await userEvent.click(sendButton());

    expect(await screen.findByText("Error: Rate limited")).toBeInTheDocument();
    expect(input()).toBeEnabled();
  });

  it("falls back to the HTTP status when the error body has no detail", async () => {
    installFetch({
      "POST /ask": () =>
        ({ ok: false, status: 500, json: async () => { throw new Error("bad json"); } }) as unknown as Response,
    });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.type(input(), "Question");
    await userEvent.click(sendButton());

    expect(await screen.findByText("Error: HTTP 500")).toBeInTheDocument();
  });

  it("Daily Briefing posts a user message and renders the briefing", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Daily Briefing" }));

    expect(screen.getByText("Give me today's market briefing.")).toBeInTheDocument();
    expect(await screen.findByText("Markets opened flat.")).toBeInTheDocument();
    expect(callsTo(fetchFn, "GET", "/daily-briefing")).toHaveLength(1);
  });

  it("Daily Briefing shows an error message on HTTP failure", async () => {
    installFetch({ "GET /daily-briefing": () => res({}, false, 502) });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Daily Briefing" }));

    expect(await screen.findByText("Error: HTTP 502")).toBeInTheDocument();
  });

  it("Suggest Rebalance POSTs to /rebalance-suggest and renders the answer", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Suggest Rebalance" }));

    expect(screen.getByText("Suggest a rebalancing plan for my portfolio.")).toBeInTheDocument();
    expect(await screen.findByText(ASK.answer)).toBeInTheDocument();
    expect(callsTo(fetchFn, "POST", "/rebalance-suggest")).toHaveLength(1);
  });

  it("Suggest Rebalance shows an error message on HTTP failure", async () => {
    installFetch({ "POST /rebalance-suggest": () => res({}, false, 500) });
    render(<AiAdvisorPanel accountId="acc-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Suggest Rebalance" }));

    expect(await screen.findByText("Error: HTTP 500")).toBeInTheDocument();
  });

  it("Check Sentiment refetches data and renders a summary message", async () => {
    const fetchFn = installFetch();
    render(<AiAdvisorPanel accountId="acc-1" />);
    await screen.findByText("+42 Cautiously Bullish");

    await userEvent.click(screen.getByRole("button", { name: "Check Sentiment" }));

    expect(await screen.findByText(/Market Sentiment: Cautiously Bullish \(\+42\.0\)/)).toBeInTheDocument();
    expect(screen.getByText(/India VIX: 14\.2 \| PCR: 0\.90/)).toBeInTheDocument();
    expect(screen.getByText(/Suggested equity: 80%, cash: 20%/)).toBeInTheDocument();
    expect(callsTo(fetchFn, "GET", "/sentiment")).toHaveLength(2);
    expect(callsTo(fetchFn, "GET", "/regime-status")).toHaveLength(2);
  });

  it("Check Sentiment shows an error message when the fetch rejects", async () => {
    let calls = 0;
    installFetch({
      "GET /sentiment": () => (++calls === 1 ? res(SENTIMENT) : Promise.reject(new Error("offline"))),
    });
    render(<AiAdvisorPanel accountId="acc-1" />);
    await screen.findByText("+42 Cautiously Bullish");

    await userEvent.click(screen.getByRole("button", { name: "Check Sentiment" }));

    expect(await screen.findByText("Error: offline")).toBeInTheDocument();
  });
});
