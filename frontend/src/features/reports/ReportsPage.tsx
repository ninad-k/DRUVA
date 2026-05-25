import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { generateReport, listReports } from "@/api/rest/endpoints";
import { formatDateTime } from "@/utils/format";

const REPORT_TYPES = [
  { type: "strategy_performance", label: "Strategy Performance" },
  { type: "portfolio_risk", label: "Portfolio Risk" },
  { type: "trade_journal", label: "Trade Journal" },
];

export function ReportsPage() {
  const qc = useQueryClient();
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: listReports,
  });

  const generate = useMutation({
    mutationFn: generateReport,
    onSuccess: () => {
      toast.success("Report queued");
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: () => toast.error("Failed to generate report"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Generate and download portfolio, strategy, and trade reports."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            {REPORT_TYPES.map((report) => (
              <Button
                key={report.type}
                size="sm"
                variant="outline"
                onClick={() => generate.mutate(report.type)}
                disabled={generate.isPending}
              >
                <RefreshCw className="h-4 w-4" />
                {report.label}
              </Button>
            ))}
          </div>
        }
      />

      <Card>
        <CardContent className="p-4">
          {reports.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (reports.data ?? []).length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No reports yet"
              description="Generate a report to track exports and downloads here."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Generated</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.data!.map((report) => (
                  <TableRow key={report.id}>
                    <TableCell className="font-medium">{labelFor(report.type)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDateTime(report.generated_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={report.status === "failed" ? "destructive" : "secondary"}>
                        {report.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {report.url && report.status === "ready" ? (
                        <Button size="sm" variant="outline" asChild>
                          <a href={report.url} target="_blank" rel="noreferrer">
                            <Download className="h-4 w-4" />
                            Download
                          </a>
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">Unavailable</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function labelFor(type: string): string {
  return REPORT_TYPES.find((report) => report.type === type)?.label ?? type;
}
