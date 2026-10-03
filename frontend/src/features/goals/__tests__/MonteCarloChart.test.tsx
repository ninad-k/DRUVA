import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { MonteCarloChart } from "../MonteCarloChart";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SIM_RESULT = {
  p10: 800000,
  p25: 1200000,
  p50: 1800000,
  p75: 2400000,
  p90: 3200000,
  probability_of_success: 0.72,
  expected_final_value: 1900000,
  worst_case: 700000,
  best_case: 3500000,
  horizon_months: 120,
  target_corpus: 2000000,
  total_invested: 1200000,
  fan_data: [
    { month: 0, p10: 500000, p25: 500000, p50: 500000, p75: 500000, p90: 500000 },
    { month: 120, p10: 800000, p25: 1200000, p50: 1800000, p75: 2400000, p90: 3200000 },
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  } as Response;
}

function renderChart(goalId = "goal-1", targetCorpus = 2000000) {
  return render(<MonteCarloChart goalId={goalId} targetCorpus={targetCorpus} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("MonteCarloChart", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    // jsdom lacks ResizeObserver, which recharts' ResponsiveContainer requires.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the heading and an enabled Run Simulation button", () => {
    renderChart();

    expect(screen.getByText("Monte Carlo Goal Projection")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Simulation" })).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows no result badge or summary before a simulation is run", () => {
    renderChart();

    expect(screen.queryByText(/success$/)).not.toBeInTheDocument();
    expect(screen.queryByText("Median (P50)")).not.toBeInTheDocument();
  });

  it("POSTs default params to /api/v1/goals/{goalId}/simulate", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIM_RESULT));
    renderChart("goal-42");

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/goals/goal-42/simulate");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      annual_return_pct: 12,
      annual_volatility_pct: 18,
      sip_step_up_pct: 10,
      n_simulations: 1000,
      regime_return_adj_pct: 0,
    });
  });

  it("disables the button and shows progress text while loading", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    const busy = await screen.findByRole("button", { name: /Running 1,000 paths/ });
    expect(busy).toBeDisabled();

    resolve(jsonResponse(SIM_RESULT));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run Simulation" })).toBeEnabled(),
    );
  });

  it("shows the success probability badge after the fetch resolves", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIM_RESULT));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("72.0% success")).toBeInTheDocument();
  });

  it("renders summary values formatted in lakhs", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIM_RESULT));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("Median (P50)")).toBeInTheDocument();
    expect(screen.getByText("₹18.00L")).toBeInTheDocument(); // P50
    expect(screen.getByText("₹8.00L")).toBeInTheDocument(); // P10
    expect(screen.getByText("₹32.00L")).toBeInTheDocument(); // P90
    expect(screen.getByText("₹12.00L")).toBeInTheDocument(); // total invested
  });

  it("formats values >= 1 crore with Cr suffix", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...SIM_RESULT, p90: 25000000 }));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("₹2.50Cr")).toBeInTheDocument();
  });

  it("renders the chart without crashing when a target corpus is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIM_RESULT));
    const { container } = renderChart("goal-1", 2000000);

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    await screen.findByText("72.0% success");
    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });

  it.each([
    [0.8, "text-green-500"],
    [0.6, "text-amber-500"],
    [0.3, "text-red-500"],
  ])("colours the badge for probability %s with %s", async (p, cls) => {
    fetchMock.mockResolvedValue(jsonResponse({ ...SIM_RESULT, probability_of_success: p }));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    const badge = await screen.findByText(/% success$/);
    expect(badge).toHaveClass(cls);
  });

  it("sends edited parameters and caps simulations at 5000", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIM_RESULT));
    renderChart();

    const ret = screen.getByDisplayValue("12");
    await userEvent.clear(ret);
    await userEvent.type(ret, "15");
    const sims = screen.getByDisplayValue("1000");
    await userEvent.clear(sims);
    await userEvent.type(sims, "9000");

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.annual_return_pct).toBe(15);
    expect(body.n_simulations).toBe(5000);
  });

  it("shows the server error text when the response is not ok", async () => {
    fetchMock.mockResolvedValue(jsonResponse("Goal not found", false, 404));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("Goal not found")).toBeInTheDocument();
    expect(screen.queryByText(/% success$/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Simulation" })).toBeEnabled();
  });

  it("shows the thrown error message when fetch rejects", async () => {
    fetchMock.mockRejectedValue(new Error("Network down"));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("Network down")).toBeInTheDocument();
  });

  it("clears a previous error on a successful retry", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce(jsonResponse(SIM_RESULT));
    renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    await screen.findByText("Network down");

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("72.0% success")).toBeInTheDocument();
    expect(screen.queryByText("Network down")).not.toBeInTheDocument();
  });

  it("renders the badge but no chart or summary when fan_data is empty", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...SIM_RESULT, fan_data: [] }));
    const { container } = renderChart();

    await userEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("72.0% success")).toBeInTheDocument();
    expect(screen.queryByText("Median (P50)")).not.toBeInTheDocument();
    expect(container.querySelector(".recharts-responsive-container")).not.toBeInTheDocument();
  });
});
