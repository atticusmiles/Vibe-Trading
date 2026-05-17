import { Suspense, lazy, type ComponentType, type ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { isLoggedIn } from "@/lib/apiAuth";

const Home = lazy(() => import("@/pages/Home").then((m) => ({ default: m.Home })));
const Agent = lazy(() => import("@/pages/Agent").then((m) => ({ default: m.Agent })));
const Login = lazy(() => import("@/pages/Login").then((m) => ({ default: m.Login })));
const RunDetail = lazy(() =>
  import("@/pages/RunDetail").then((m) => ({ default: m.RunDetail })),
);
const Compare = lazy(() =>
  import("@/pages/Compare").then((m) => ({ default: m.Compare })),
);
const Settings = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const Tools = lazy(() =>
  import("@/pages/Tools").then((m) => ({ default: m.Tools })),
);
const Correlation = lazy(() =>
  import("@/pages/Correlation").then((m) => ({ default: m.Correlation })),
);
const Trends = lazy(() => import("@/pages/Trends").then((m) => ({ default: m.Trends })));
const Industries = lazy(() => import("@/pages/Industries").then((m) => ({ default: m.Industries })));
const Stocks = lazy(() => import("@/pages/Stocks").then((m) => ({ default: m.Stocks })));

function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
      Loading…
    </div>
  );
}

function wrap(Component: ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: wrap(Login),
  },
  {
    element: <Layout />,
    children: [
      { path: "/", element: <RequireAuth>{wrap(Home)}</RequireAuth> },
      { path: "/trends", element: <RequireAuth>{wrap(Trends)}</RequireAuth> },
      { path: "/industries", element: <RequireAuth>{wrap(Industries)}</RequireAuth> },
      { path: "/stocks", element: <RequireAuth>{wrap(Stocks)}</RequireAuth> },
      { path: "/agent", element: <RequireAuth>{wrap(Agent)}</RequireAuth> },
      { path: "/settings", element: <RequireAuth>{wrap(Settings)}</RequireAuth> },
      { path: "/tools", element: <RequireAuth>{wrap(Tools)}</RequireAuth> },
      { path: "/runs/:runId", element: <RequireAuth>{wrap(RunDetail)}</RequireAuth> },
      { path: "/compare", element: <RequireAuth>{wrap(Compare)}</RequireAuth> },
      { path: "/correlation", element: <Navigate to="/tools" replace /> },
    ],
  },
]);
