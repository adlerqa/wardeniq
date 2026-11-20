import "../styles/Dashboard.css";

import { SkeletonDashboard } from "../../../components/feedback/Skeleton.jsx";
import { DashboardError, DashboardOverview } from "../components/DashboardOverview.jsx";
import useDashboard from "../hooks/useDashboard.js";

/** Workspace overview. Data loads when the screen opens (navigateTo calls loadDashboard()). */
export default function DashboardPage() {
  const dash = useDashboard();
  return (
    <section id="view-dashboard" className="view">
      <div id="dash-root" className="flex flex-col gap-[22px]">
        {dash.status === "loading" && <SkeletonDashboard />}
        {dash.status === "ready" && <DashboardOverview data={dash.data} />}
        {dash.status === "error" && <DashboardError message={dash.error} onRetry={dash.reload} />}
      </div>
    </section>
  );
}
