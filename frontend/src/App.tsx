import { useEffect, useState } from "react";
import { Activity, BarChart3, Rocket, ShieldCheck } from "lucide-react";

/**
 * Placeholder landing shell.
 *
 * The real app will use TanStack Router with routes defined under `src/routes/`.
 * See docs/prompts/DHRUVA_Python_React_Master_Prompt.md §11 for the full spec.
 */
export default function App() {
  const [backendStatus, setBackendStatus] = useState<"unknown" | "ok" | "down">("unknown");

  useEffect(() => {
    fetch("/api/health/live")
      .then((r) => setBackendStatus(r.ok ? "ok" : "down"))
      .catch(() => setBackendStatus("down"));
  }, []);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground font-bold">
              ₹
            </div>
            <div>
              <p className="text-lg font-semibold tracking-tight">DHRUVA</p>
              <p className="text-xs text-muted-foreground">Pole Star of Algo Trading</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={
                "inline-block h-2 w-2 rounded-full " +
                (backendStatus === "ok"
                  ? "bg-[hsl(var(--gain))]"
                  : backendStatus === "down"
                    ? "bg-[hsl(var(--loss))]"
                    : "bg-muted-foreground")
              }
            />
            <span className="text-muted-foreground">
              Backend:{" "}
              {backendStatus === "ok" ? "Online" : backendStatus === "down" ? "Offline" : "…"}
            </span>
          </div>
        </div>
      </header>

      <section className="container py-16">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-4xl font-bold tracking-tight md:text-5xl">
            Ultra-fast algo trading for <span className="text-primary">Indian markets</span>.
          </h1>
          <p className="mt-4 text-lg text-muted-foreground">
            Multi-broker execution, AI/ML strategies, real-time portfolio analytics — in a single,
            open platform.
          </p>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            icon={<Rocket className="h-5 w-5" />}
            title="Multi-broker"
            body="Zerodha, Upstox, Dhan, Fyers, 5Paisa — extensible to 23+."
          />
          <FeatureCard
            icon={<Activity className="h-5 w-5" />}
            title="AI/ML strategies"
            body="Rule-based + ML (XGBoost, LSTM, RL) with hot-loadable models."
          />
          <FeatureCard
            icon={<BarChart3 className="h-5 w-5" />}
            title="Live dashboards"
            body="Per-account & overall equity curves, P&L, drawdown, VaR."
          />
          <FeatureCard
            icon={<ShieldCheck className="h-5 w-5" />}
            title="Enterprise-grade"
            body="JWT + refresh, encrypted credentials, full tracing & audit."
          />
        </div>
      </section>
    </main>
  );
}

function FeatureCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
        {icon}
      </div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
