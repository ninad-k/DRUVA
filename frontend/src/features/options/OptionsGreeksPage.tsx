import { PageHeader } from "@/components/common/PageHeader";
import { GreeksDashboard } from "./GreeksDashboard";
import type { OptionPosition } from "./GreeksDashboard";

// Placeholder — replace with a real live-positions query (useQuery from
// /api/v1/options/positions) when the backend endpoint is available.
const EMPTY_POSITIONS: OptionPosition[] = [];

export function OptionsGreeksPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Options Greeks"
        description="Real-time portfolio Greeks — Delta, Gamma, Theta, and Vega across all open option positions."
      />
      <GreeksDashboard positions={EMPTY_POSITIONS} />
    </div>
  );
}
