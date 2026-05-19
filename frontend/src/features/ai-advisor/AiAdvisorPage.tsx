import { Bot } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { useAccountStore } from "@/store/account";
import { AiAdvisorPanel } from "./AiAdvisorPanel";

export function AiAdvisorPage() {
  const accountId = useAccountStore((s) => s.activeAccountId);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Portfolio Advisor"
        description="Claude-powered chat advisor with live sentiment, regime detection, and rebalancing suggestions."
      />
      {accountId ? (
        <AiAdvisorPanel accountId={accountId} />
      ) : (
        <EmptyState
          icon={Bot}
          title="No broker account connected"
          description="Connect a broker account in Settings to use the AI Portfolio Advisor."
        />
      )}
    </div>
  );
}
