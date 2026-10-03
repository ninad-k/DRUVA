import { render, screen, within } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { VaRDashboard } from "../VaRDashboard";

// VaRDashboard is a presentational component: it receives a computed report
// via props rather than fetching it, so tests drive it with fixtures.

type Report = NonNullable<React.ComponentProps<typeof VaRDashboard>["report"]>;

const makeReport = (overrides: Partial<Report> = {}): Report => ({
  var_95: { var_pct: 2.3, cvar_pct: 3.1, var_inr: 11500, cvar_inr: 15500 },
  var_99: { var_pct: 3.8, cvar_pct: 4.6, var_inr: 19000, cvar_inr: 23000 },
  cvar_95: { var_pct: 2.3, cvar_pct: 3.1, var_inr: 11500, cvar_inr: 15500 },
  cvar_99: { var_pct: 3.8, cvar_pct: 4.6, var_inr: 19000, cvar_inr: 23000 },
  position_contributions: [
    { symbol: "GOLDBEES", weight_pct: 40, var_contribution_pct: 0.9, standalone_var_pct: 1.8 },
    { symbol: "NIFTYBEES", weight_pct: 60, var_contribution_pct: 1.4, standalone_var_pct: 2.5 },
  ],
  computed_at: "2024-06-01T10:30:00Z",
  ...overrides,
});

const withVar95 = (pct: number) =>
  makeReport({ var_95: { var_pct: pct, cvar_pct: pct + 1, var_inr: 1000, cvar_inr: 1500 } });

describe("VaRDashboard", () => {
  it("renders skeleton placeholders and no report content while loading", () => {
    const { container } = render(<VaRDashboard report={makeReport()} loading />);

    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
    expect(screen.queryByText(/VaR \/ CVaR/)).not.toBeInTheDocument();
  });

  it("shows loading skeleton even when report is null", () => {
    render(<VaRDashboard report={null} loading />);

    expect(screen.queryByText(/No VaR report available/)).not.toBeInTheDocument();
  });

  it("renders the empty state when there is no report", () => {
    render(<VaRDashboard report={null} />);

    expect(screen.getByText(/No VaR report available/)).toBeInTheDocument();
    expect(screen.queryByText(/VaR \/ CVaR/)).not.toBeInTheDocument();
  });

  it("renders the heading", () => {
    render(<VaRDashboard report={makeReport()} />);

    expect(screen.getByText(/Portfolio Risk/)).toBeInTheDocument();
    expect(screen.getByText(/VaR \/ CVaR/)).toBeInTheDocument();
  });

  it("displays the VaR 95% percentage and INR amount", () => {
    render(<VaRDashboard report={makeReport()} />);

    const label = screen.getByText("VaR 95%");
    const card = label.parentElement as HTMLElement;
    expect(within(card).getByText("2.30%")).toBeInTheDocument();
    expect(within(card).getByText("₹11,500")).toBeInTheDocument();
  });

  it("displays all four KPI cards", () => {
    render(<VaRDashboard report={makeReport()} />);

    expect(screen.getByText("VaR 95%")).toBeInTheDocument();
    expect(screen.getByText("CVaR 95% (ES)")).toBeInTheDocument();
    expect(screen.getByText("VaR 99%")).toBeInTheDocument();
    expect(screen.getByText("CVaR 99% (ES)")).toBeInTheDocument();

    const cvar99 = screen.getByText("CVaR 99% (ES)").parentElement as HTMLElement;
    expect(within(cvar99).getByText("4.60%")).toBeInTheDocument();
    expect(within(cvar99).getByText("₹23,000")).toBeInTheDocument();
  });

  it("renders a contribution row for each symbol", () => {
    render(<VaRDashboard report={makeReport()} />);

    expect(screen.getByText("Position Contribution to VaR (95%)")).toBeInTheDocument();
    expect(screen.getByText("NIFTYBEES")).toBeInTheDocument();
    expect(screen.getByText("GOLDBEES")).toBeInTheDocument();
  });

  it("sorts contributions descending and flags the top contributor", () => {
    render(<VaRDashboard report={makeReport()} />);

    const rows = screen.getAllByRole("row").slice(1); // skip header
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("NIFTYBEES")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Top")).toBeInTheDocument();
    expect(within(rows[1]).getByText("GOLDBEES")).toBeInTheDocument();
    expect(within(rows[1]).queryByText("Top")).not.toBeInTheDocument();
  });

  it("formats weight, standalone and contribution percentages", () => {
    render(<VaRDashboard report={makeReport()} />);

    const row = screen.getByText("NIFTYBEES").closest("tr") as HTMLElement;
    expect(within(row).getByText("60.00%")).toBeInTheDocument();
    expect(within(row).getByText("2.50%")).toBeInTheDocument();
    expect(within(row).getByText("1.40%")).toBeInTheDocument();
  });

  it("omits the contribution table when there are no positions", () => {
    render(<VaRDashboard report={makeReport({ position_contributions: [] })} />);

    expect(screen.queryByText("Position Contribution to VaR (95%)")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("VaR 95%")).toBeInTheDocument();
  });

  it("does not mutate the report's contribution order", () => {
    const report = makeReport();
    render(<VaRDashboard report={report} />);

    expect(report.position_contributions[0].symbol).toBe("GOLDBEES");
  });

  it.each([
    [1.49, "LOW RISK"],
    [1.5, "MEDIUM RISK"],
    [2.99, "MEDIUM RISK"],
    [3.0, "HIGH RISK"],
    [5.2, "HIGH RISK"],
  ])("labels VaR 95%% of %s as %s", (pct, label) => {
    render(<VaRDashboard report={withVar95(pct)} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
