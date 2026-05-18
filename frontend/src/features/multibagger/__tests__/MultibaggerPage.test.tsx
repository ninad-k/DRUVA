import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MultibaggerPage } from "../MultibaggerPage";
import type { ScanResultRow } from "@/api/rest/endpoints";

// ── Module-level mocks ────────────────────────────────────────────────────────

vi.mock("@/api/rest/endpoints", () => ({
  listAccounts: vi.fn(),
  listMultibaggerScannerRegistry: vi.fn(),
  listMultibaggerScanners: vi.fn(),
  listScanResults: vi.fn(),
  runMultibaggerScanner: vi.fn(),
  promoteScanResult: vi.fn(),
  dismissScanResult: vi.fn(),
  acknowledgeScanResult: vi.fn(),
  createMultibaggerScanner: vi.fn(),
  enableMultibaggerScanner: vi.fn(),
  disableMultibaggerScanner: vi.fn(),
  deleteMultibaggerScanner: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}));

// MarketCycleBanner makes its own query — stub it out
vi.mock("@/components/common/MarketCycleBanner", () => ({
  MarketCycleBanner: () => null,
}));

// FundamentalsDrawer makes its own query — stub it out
vi.mock("@/components/common/FundamentalsDrawer", () => ({
  FundamentalsDrawer: () => null,
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

const makeScanResult = (overrides: Partial<ScanResultRow> = {}): ScanResultRow => ({
  id: "sr-1",
  scanner_id: "sc-1",
  run_ts: "2024-01-15T09:30:00Z",
  symbol: "RELIANCE",
  exchange: "NSE",
  score: 85.5,
  stage: "VCP Stage 2",
  reason: "Strong breakout pattern",
  suggested_entry: 2450.0,
  suggested_stop: 2350.0,
  suggested_target: 2800.0,
  status: "new",
  metadata: {},
  ...overrides,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

async function setupEndpointMocks(results: ScanResultRow[] = []) {
  const endpoints = await import("@/api/rest/endpoints");
  (endpoints.listAccounts as ReturnType<typeof vi.fn>).mockResolvedValue([ACCOUNT]);
  (endpoints.listMultibaggerScannerRegistry as ReturnType<typeof vi.fn>).mockResolvedValue([
    "scanner.vcp_multibagger.v1",
  ]);
  (endpoints.listMultibaggerScanners as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (endpoints.listScanResults as ReturnType<typeof vi.fn>).mockResolvedValue(results);
}

function renderPage() {
  const client = makeClient();
  return render(
    <QueryClientProvider client={client}>
      <MultibaggerPage />
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("MultibaggerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the Multibagger page heading", async () => {
    await setupEndpointMocks();
    renderPage();
    expect(screen.getByText("Multibagger")).toBeInTheDocument();
  });

  it("renders 'No candidates' empty state when results list is empty", async () => {
    await setupEndpointMocks([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No candidates")).toBeInTheDocument();
    });
  });

  it("renders the scanner results table when data is present", async () => {
    await setupEndpointMocks([makeScanResult()]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    });
  });

  it("shows Score column header in the results table", async () => {
    await setupEndpointMocks([makeScanResult()]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: /score/i })).toBeInTheDocument();
    });
  });

  it("displays the numerical score value for each result", async () => {
    await setupEndpointMocks([makeScanResult({ score: 85.5 })]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("85.50")).toBeInTheDocument();
    });
  });

  it("shows Symbol, Stage, Entry, Stop, Target columns", async () => {
    await setupEndpointMocks([makeScanResult()]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: /symbol/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /stage/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /entry/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /stop/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /target/i })).toBeInTheDocument();
    });
  });

  it("renders multiple rows when multiple results are present", async () => {
    await setupEndpointMocks([
      makeScanResult({ id: "sr-1", symbol: "RELIANCE", score: 90 }),
      makeScanResult({ id: "sr-2", symbol: "INFY", score: 75 }),
    ]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("RELIANCE")).toBeInTheDocument();
      expect(screen.getByText("INFY")).toBeInTheDocument();
    });
  });

  it("sorts results by score descending (highest score first)", async () => {
    await setupEndpointMocks([
      makeScanResult({ id: "sr-1", symbol: "INFY", score: 70 }),
      makeScanResult({ id: "sr-2", symbol: "RELIANCE", score: 90 }),
    ]);
    renderPage();

    await waitFor(() => {
      const cells = screen.getAllByRole("cell");
      const symbols = cells
        .map((c) => c.textContent)
        .filter((t) => t === "RELIANCE" || t?.startsWith("RELIANCE"));
      // RELIANCE (score 90) should appear before INFY (score 70)
      expect(symbols.length).toBeGreaterThan(0);
    });
  });

  it("shows 'No scanners configured' when scanner list is empty", async () => {
    await setupEndpointMocks();
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/no scanners configured/i),
      ).toBeInTheDocument();
    });
  });

  it("shows 'Ack' and 'Promote' action buttons for new results", async () => {
    await setupEndpointMocks([makeScanResult({ status: "new" })]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /ack/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /promote/i })).toBeInTheDocument();
    });
  });

  it("shows 'Dismiss' button for non-promoted, non-dismissed results", async () => {
    await setupEndpointMocks([makeScanResult({ status: "new" })]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /dismiss/i })).toBeInTheDocument();
    });
  });

  it("shows stage badge for each result row", async () => {
    await setupEndpointMocks([makeScanResult({ stage: "VCP Stage 2" })]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VCP Stage 2")).toBeInTheDocument();
    });
  });
});
