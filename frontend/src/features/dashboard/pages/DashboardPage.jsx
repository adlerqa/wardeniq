/**
 * DashboardPage
 *
 * Structural React port of the original static screen markup.
 * Data loading and mutation behavior is currently supplied by the domain
 * compatibility controllers under src/compat/runtime/controllers.
 * Keeping the DOM contract here lets the UI be migrated screen-by-screen
 * without a single monolithic HTML template.
 */

import "../styles/Dashboard.css";
import SetupChecklist from "../../onboarding/components/SetupChecklist.jsx";

export default function DashboardPage() {
  return (
    <section id="view-dashboard" className="view">
      {/* React-owned; sits above #dash-root, which the compat controller fills. */}
      <SetupChecklist />
      <div className="dash" id="dash-root"></div>
    </section>
  );
}
