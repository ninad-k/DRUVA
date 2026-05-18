import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { InstrumentSearch } from "../InstrumentSearch";
import type { InstrumentSearchResult } from "@/types/api";

// ── Module-level mocks ────────────────────────────────────────────────────────

vi.mock("@/api/rest/endpoints", () => ({
  searchInstruments: vi.fn(),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const RESULTS: InstrumentSearchResult[] = [
  { symbol: "RELIANCE", exchange: "NSE", name: "Reliance Industries Ltd", segment: "EQ" },
  { symbol: "RELIANCEX", exchange: "BSE", name: "Reliance (BSE)", segment: "EQ" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderSearch(props: Partial<React.ComponentProps<typeof InstrumentSearch>> = {}) {
  const client = makeClient();
  return render(
    <QueryClientProvider client={client}>
      <InstrumentSearch {...props} />
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("InstrumentSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a search input with default placeholder", () => {
    renderSearch();
    expect(screen.getByPlaceholderText("Search NSE/BSE…")).toBeInTheDocument();
  });

  it("renders with a custom placeholder", () => {
    renderSearch({ placeholder: "Find a stock…" });
    expect(screen.getByPlaceholderText("Find a stock…")).toBeInTheDocument();
  });

  it("does not show results when query is shorter than 2 characters", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    const user = userEvent.setup();
    renderSearch();

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "R");
    // searchInstruments should NOT be called because enabled: debouncedQ.length >= 2
    expect(searchInstruments).not.toHaveBeenCalled();
    expect(screen.queryByText("RELIANCE")).not.toBeInTheDocument();
  });

  it("shows search results after typing at least 2 characters", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue(RESULTS);

    const user = userEvent.setup();
    renderSearch();

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "RE");

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    });
  });

  it("shows all returned result items", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue(RESULTS);

    const user = userEvent.setup();
    renderSearch();

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "REL");

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
      expect(screen.getByText("RELIANCEX")).toBeInTheDocument();
    });
  });

  it("calls onSelect with symbol and exchange when a result is clicked", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue(RESULTS);

    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderSearch({ onSelect });

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "REL");

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    });

    await user.click(screen.getByText("RELIANCE"));

    expect(onSelect).toHaveBeenCalledWith("RELIANCE", "NSE");
  });

  it("clears the input after selecting an instrument", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue(RESULTS);

    const user = userEvent.setup();
    renderSearch({ onSelect: vi.fn() });

    const input = screen.getByPlaceholderText("Search NSE/BSE…");
    await user.type(input, "REL");

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    });

    await user.click(screen.getByText("RELIANCE"));

    expect(input).toHaveValue("");
  });

  it("shows 'No matches.' when search returns empty results", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    const user = userEvent.setup();
    renderSearch();

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "XYZ");

    await waitFor(() => {
      expect(screen.getByText("No matches.")).toBeInTheDocument();
    });
  });

  it("shows exchange label alongside each result", async () => {
    const { searchInstruments } = await import("@/api/rest/endpoints");
    (searchInstruments as ReturnType<typeof vi.fn>).mockResolvedValue([RESULTS[0]]);

    const user = userEvent.setup();
    renderSearch();

    await user.type(screen.getByPlaceholderText("Search NSE/BSE…"), "REL");

    await waitFor(() => {
      // Exchange label appears as a separate span
      expect(screen.getByText("NSE")).toBeInTheDocument();
    });
  });
});
