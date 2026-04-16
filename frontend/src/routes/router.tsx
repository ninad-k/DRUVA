import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { Shell } from "@/components/layout/Shell";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { OrdersPage } from "@/features/trading/OrdersPage";
import { PositionsPage } from "@/features/trading/PositionsPage";
import { PortfolioPage } from "@/features/portfolio/PortfolioPage";
import { AccountDetailPage } from "@/features/portfolio/AccountDetailPage";
import { StrategiesListPage } from "@/features/strategies/StrategiesListPage";
import { StrategyDetailPage } from "@/features/strategies/StrategyDetailPage";
import { ScannerPage } from "@/features/scanner/ScannerPage";
import { OptionsPage } from "@/features/options/OptionsPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { AccountsPage } from "@/features/settings/AccountsPage";
import { NotificationsPage } from "@/features/settings/NotificationsPage";
import { useAuthStore } from "@/store/auth";
import { useAuthBootstrap } from "@/features/auth/useAuth";

function RootComponent() {
  // Wire axios refresh + auth-failure handlers once for the whole app.
  useAuthBootstrap();
  return <Outlet />;
}

const rootRoute = createRootRoute({ component: RootComponent });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    const token = useAuthStore.getState().accessToken;
    throw redirect({ to: token ? "/dashboard" : "/login" });
  },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  component: RegisterPage,
});

const shellRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "shell",
  component: () => <Shell />,
});

const dashboardRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/dashboard",
  component: DashboardPage,
});

const ordersRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/trading/orders",
  component: OrdersPage,
});

const positionsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/trading/positions",
  component: PositionsPage,
});

const portfolioRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/portfolio",
  component: PortfolioPage,
});

const portfolioAccountRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/portfolio/$accountId",
  component: AccountDetailPage,
});

const strategiesRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/strategies",
  component: StrategiesListPage,
});

const strategyDetailRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/strategies/$id",
  component: StrategyDetailPage,
});

const scannerRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/scanner",
  component: ScannerPage,
});

const optionsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/options",
  component: OptionsPage,
});

const reportsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/reports",
  component: ReportsPage,
});

const settingsAccountsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/settings/accounts",
  component: AccountsPage,
});

const settingsNotificationsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/settings/notifications",
  component: NotificationsPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  registerRoute,
  shellRoute.addChildren([
    dashboardRoute,
    ordersRoute,
    positionsRoute,
    portfolioRoute,
    portfolioAccountRoute,
    strategiesRoute,
    strategyDetailRoute,
    scannerRoute,
    optionsRoute,
    reportsRoute,
    settingsAccountsRoute,
    settingsNotificationsRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
