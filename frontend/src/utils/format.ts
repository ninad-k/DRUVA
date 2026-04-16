/**
 * Number / currency / date formatting helpers.
 *
 * Indian markets use INR (₹) and the Indian numbering system (lakh / crore).
 */

export function formatINR(value: number, opts: { compact?: boolean } = {}) {
  if (!Number.isFinite(value)) return "—";
  const { compact } = opts;
  if (compact) {
    const abs = Math.abs(value);
    if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)}Cr`;
    if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)}L`;
    if (abs >= 1e3) return `₹${(value / 1e3).toFixed(2)}K`;
  }
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function formatNumber(value: number, decimals = 2) {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPct(value: number, decimals = 2) {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

export function formatSignedINR(value: number) {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatINR(Math.abs(value))}`;
}

export function formatDateTime(iso: string) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function pnlColorClass(value: number) {
  if (value > 0) return "text-[hsl(var(--gain))]";
  if (value < 0) return "text-[hsl(var(--loss))]";
  return "text-muted-foreground";
}
