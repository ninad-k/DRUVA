import { useQuery } from "@tanstack/react-query";
import { getFundamentals } from "@/api/rest/endpoints";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  symbol: string | null;
  exchange?: string;
  onOpenChange: (v: boolean) => void;
}

export function FundamentalsDrawer({ symbol, exchange = "NSE", onOpenChange }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["fundamentals", symbol, exchange],
    queryFn: () => getFundamentals(symbol as string, exchange),
    enabled: !!symbol,
  });

  return (
    <Sheet open={!!symbol} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            {symbol} <span className="text-xs text-muted-foreground">{exchange}</span>
          </SheetTitle>
        </SheetHeader>
        {isLoading ? (
          <div className="mt-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : isError || !data ? (
          <p className="mt-6 text-sm text-muted-foreground">
            No fundamentals snapshot on file. Refresh via Screener.in to populate.
          </p>
        ) : (
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Row label="Sector" value={data.sector} />
            <Row label="Industry" value={data.industry} />
            <Row label="Market Cap" value={fmtNum(data.market_cap)} />
            <Row label="Current Price" value={fmtNum(data.current_price)} />
            <Row label="P/E" value={fmtNum(data.pe_ratio)} />
            <Row label="ROE" value={pct(data.roe)} />
            <Row label="ROCE" value={pct(data.roce)} />
            <Row label="D/E" value={fmtNum(data.debt_to_equity)} />
            <Row label="Promoter" value={pct(data.promoter_holding)} />
            <Row label="Sales Growth (3Y)" value={pct(data.sales_growth_3y)} />
            <Row label="Profit Growth (3Y)" value={pct(data.profit_growth_3y)} />
            <Row label="EPS" value={fmtNum(data.eps)} />
            <Row label="As of" value={data.as_of_date} />
            <Row label="Source" value={data.source} />
          </dl>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono tabular-nums">{value ?? "—"}</dd>
    </div>
  );
}

const fmtNum = (n: number | null): string =>
  n === null || n === undefined ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: 2 });

const pct = (n: number | null): string =>
  n === null || n === undefined ? "—" : `${n.toFixed(2)}%`;
