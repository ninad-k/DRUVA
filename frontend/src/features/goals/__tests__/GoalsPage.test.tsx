import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsPage } from "../GoalsPage";
import type { Goal, GoalProgress } from "@/api/rest/endpoints";

// ── Module-level mocks ────────────────────────────────────────────────────────

vi.mock("@/api/rest/endpoints", () => ({
  listAccounts: vi.fn(),
  listGoals: vi.fn(),
  createGoal: vi.fn(),
  getGoalProgress: vi.fn(),
  pauseGoal: vi.fn(),
  resumeGoal: vi.fn(),
  createStpPlan: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const ACCOUNT = {
  id: "acc-1",
  broker: "zerodha" as const,
  display_name: "Zerodha Paper",
  is_paper: true,
  is_connected: true,
  created_at: "2024-01-01T00:00:00Z",
};

const makeGoal = (overrides: Partial<Goal> = {}): Goal => ({
  id: "goal-1",
  account_id: "acc-1",
  name: "Retirement",
  target_amount: "10000000",
  target_date: "2035-01-01",
  current_value: "2000000",
  monthly_sip_amount: "30000",
  arbitrage_buffer_pct: "5",
  equity_allocation_pct: "80",
  status: "active",
  target_symbols: ["NIFTYBEES"],
  ...overrides,
});

const makeProgress = (pct = "20.0"): GoalProgress => ({
  goal_id: "goal-1",
  name: "Retirement",
  target_amount: "10000000",
  target_date: "2035-01-01",
  current_value: "2000000",
  progress_pct: pct,
  months_remaining: 108,
  projected_value: "8000000",
  required_monthly: "28000",
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderPage() {
  const client = makeClient();
  return render(
    <QueryClientProvider client={client}>
      <GoalsPage />
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("GoalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders 'No goals yet' empty state when goals list is empty", async () => {
    const { listAccounts, listGoals } = await import("@/api/rest/endpoints");
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No goals yet")).toBeInTheDocument();
    });
  });

  it("renders goal cards when goals data is present", async () => {
    const { listAccounts, listGoals, getGoalProgress } = await import(
      "@/api/rest/endpoints"
    );
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([makeGoal()]);
    (getGoalProgress as ReturnType<typeof vi.fn>).mockResolvedValue(makeProgress("20.0"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Retirement")).toBeInTheDocument();
    });
  });

  it("shows the goal's target amount and date in the card", async () => {
    const { listAccounts, listGoals, getGoalProgress } = await import(
      "@/api/rest/endpoints"
    );
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([makeGoal()]);
    (getGoalProgress as ReturnType<typeof vi.fn>).mockResolvedValue(makeProgress("20.0"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/2035-01-01/)).toBeInTheDocument();
    });
  });

  it("progress bar reflects the goal progress percentage", async () => {
    const { listAccounts, listGoals, getGoalProgress } = await import(
      "@/api/rest/endpoints"
    );
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([makeGoal()]);
    (getGoalProgress as ReturnType<typeof vi.fn>).mockResolvedValue(makeProgress("42.5"));

    renderPage();

    await waitFor(() => {
      // Progress percentage text is rendered as "42.5%"
      expect(screen.getByText("42.5%")).toBeInTheDocument();
    });
  });

  it("'New goal' button is disabled when no account is available", async () => {
    const { listAccounts, listGoals } = await import("@/api/rest/endpoints");
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /new goal/i })).toBeDisabled();
    });
  });

  it("'New goal' button opens the create dialog when account exists", async () => {
    const { listAccounts, listGoals } = await import("@/api/rest/endpoints");
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /new goal/i })).not.toBeDisabled();
    });

    await user.click(screen.getByRole("button", { name: /new goal/i }));

    await waitFor(() => {
      expect(screen.getByText("Create goal")).toBeInTheDocument();
    });
  });

  it("renders multiple goal cards when multiple goals exist", async () => {
    const { listAccounts, listGoals, getGoalProgress } = await import(
      "@/api/rest/endpoints"
    );
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeGoal({ id: "g1", name: "Retirement" }),
      makeGoal({ id: "g2", name: "House Fund" }),
    ]);
    (getGoalProgress as ReturnType<typeof vi.fn>).mockResolvedValue(makeProgress("10.0"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Retirement")).toBeInTheDocument();
      expect(screen.getByText("House Fund")).toBeInTheDocument();
    });
  });

  it("goal card shows active badge for active goals", async () => {
    const { listAccounts, listGoals, getGoalProgress } = await import(
      "@/api/rest/endpoints"
    );
    (listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
    (listGoals as ReturnType<typeof vi.fn>).mockResolvedValue([makeGoal({ status: "active" })]);
    (getGoalProgress as ReturnType<typeof vi.fn>).mockResolvedValue(makeProgress());

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("active")).toBeInTheDocument();
    });
  });
});
