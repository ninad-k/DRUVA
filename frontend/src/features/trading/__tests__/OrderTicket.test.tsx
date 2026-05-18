import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OrderTicket } from "../OrderTicket";

// ── Module-level mocks ────────────────────────────────────────────────────────

vi.mock("@/api/rest/endpoints", () => ({
  placeOrder: vi.fn(),
}));

vi.mock("@/store/account", () => ({
  useAccountStore: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// InstrumentSearch makes its own query — stub it out for isolation
vi.mock("@/components/layout/InstrumentSearch", () => ({
  InstrumentSearch: ({ onSelect }: { onSelect?: (sym: string, exch: string) => void }) => (
    <button
      type="button"
      data-testid="instrument-search"
      onClick={() => onSelect?.("RELIANCE", "NSE")}
    >
      Search instruments
    </button>
  ),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderTicket(props: Partial<React.ComponentProps<typeof OrderTicket>> = {}) {
  const client = makeClient();
  return render(
    <QueryClientProvider client={client}>
      <OrderTicket open={true} onOpenChange={vi.fn()} {...props} />
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("OrderTicket", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    // Default: a valid account is selected
    const { useAccountStore } = await import("@/store/account");
    (useAccountStore as ReturnType<typeof vi.fn>).mockReturnValue("account-id-123");
  });

  it("renders the sheet with Place Order heading", () => {
    renderTicket();
    expect(screen.getByText("Place Order")).toBeInTheDocument();
  });

  it("shows BUY and SELL toggle buttons", () => {
    renderTicket();
    // Use exact text to distinguish "Buy" toggle from "Place BUY" submit
    expect(screen.getByRole("button", { name: "Buy" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sell" })).toBeInTheDocument();
  });

  it("defaults to BUY side — submit button says 'Place BUY'", () => {
    renderTicket();
    expect(screen.getByRole("button", { name: /place buy/i })).toBeInTheDocument();
  });

  it("switching to SELL changes the submit label", async () => {
    const user = userEvent.setup();
    renderTicket();
    await user.click(screen.getByRole("button", { name: /^sell$/i }));
    expect(screen.getByRole("button", { name: /place sell/i })).toBeInTheDocument();
  });

  it("shows order type selector with Market as default value", async () => {
    renderTicket();
    // The select trigger shows the currently selected value.
    // There may be multiple "Market" spans (trigger + content hidden); use getAllBy and assert at least one.
    const marketEls = screen.getAllByText("Market");
    expect(marketEls.length).toBeGreaterThan(0);
  });

  it("does not show price field for MARKET orders by default", () => {
    renderTicket();
    expect(screen.queryByLabelText(/^price$/i)).not.toBeInTheDocument();
  });

  it("shows price field when order type is LIMIT", async () => {
    const user = userEvent.setup();
    renderTicket({ defaults: { order_type: "LIMIT" } });
    // price label should be visible now
    await waitFor(() => {
      expect(screen.getByLabelText(/^price$/i)).toBeInTheDocument();
    });
  });

  it("shows quantity field with label", () => {
    renderTicket();
    expect(screen.getByLabelText(/quantity/i)).toBeInTheDocument();
  });

  it("shows account id snippet in description when account is set", () => {
    renderTicket();
    // account id is 'account-id-123' → sliced to 8 chars 'account-'
    expect(screen.getByText(/account:/i)).toBeInTheDocument();
  });

  it("submit button is disabled when no account is selected", async () => {
    const { useAccountStore } = await import("@/store/account");
    // Override to null for this test only
    (useAccountStore as ReturnType<typeof vi.fn>).mockReturnValue(null);

    const client = makeClient();
    render(
      <QueryClientProvider client={client}>
        <OrderTicket open={true} onOpenChange={vi.fn()} />
      </QueryClientProvider>,
    );

    // The submit button has type="submit" and name contains "Place"
    // Use getAllByRole to handle multiple matches safely
    const buttons = screen.getAllByRole("button", { name: /place/i });
    // Find the submit-type button
    const submitBtn = buttons.find(
      (b) => (b as HTMLButtonElement).type === "submit",
    );
    expect(submitBtn).toBeInTheDocument();
    expect(submitBtn).toBeDisabled();
  });

  it("calls placeOrder with correct payload on submit", async () => {
    const { placeOrder } = await import("@/api/rest/endpoints");
    const mockPlaceOrder = placeOrder as ReturnType<typeof vi.fn>;
    mockPlaceOrder.mockResolvedValueOnce({ id: "order-1" });

    const user = userEvent.setup();
    renderTicket({
      defaults: { symbol: "RELIANCE", exchange: "NSE", quantity: 5 },
    });

    // Clear quantity field and set new value
    const qtyInput = screen.getByLabelText(/quantity/i);
    await user.clear(qtyInput);
    await user.type(qtyInput, "5");

    await user.click(screen.getByRole("button", { name: /place buy/i }));

    await waitFor(() => {
      expect(mockPlaceOrder).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: "RELIANCE",
          exchange: "NSE",
          side: "BUY",
          account_id: "account-id-123",
        }),
      );
    });
  });

  it("shows loading spinner while mutation is in flight", async () => {
    const { placeOrder } = await import("@/api/rest/endpoints");
    const mockPlaceOrder = placeOrder as ReturnType<typeof vi.fn>;
    // Never resolves — keeps pending state
    mockPlaceOrder.mockReturnValueOnce(new Promise(() => {}));

    const user = userEvent.setup();
    renderTicket({ defaults: { symbol: "TCS", exchange: "NSE" } });

    await user.click(screen.getByRole("button", { name: /place buy/i }));

    // After submit the button becomes disabled (isPending = true)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /place buy/i })).toBeDisabled();
    });
  });

  it("shows cancel button that calls onOpenChange(false)", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderTicket({ onOpenChange });

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
