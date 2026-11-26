import Sidebar from "./Sidebar.jsx";
import Header from "./Header.jsx";
import { useServiceStatus } from "./useServiceStatus.js";
import Backbar from "./Backbar.jsx";
import { useNavigation } from "../app/useNavigation.js";
import DashboardPage from "../features/dashboard/pages/DashboardPage.jsx";
import ProjectsPage from "../features/projects/pages/ProjectsPage.jsx";
import FeaturesPage from "../features/features/pages/FeaturesPage.jsx";
import TestCasesPage from "../features/test-cases/pages/TestCasesPage.jsx";
import CodeAnalysisPage from "../features/code-analysis/pages/CodeAnalysisPage.jsx";
import TestCyclesPage from "../features/test-cycles/pages/TestCyclesPage.jsx";
import MindMapPage from "../features/mind-map/pages/MindMapPage.jsx";
import StepLibraryPage from "../features/step-library/pages/StepLibraryPage.jsx";
import UsagePage from "../features/usage/pages/UsagePage.jsx";
import ConfigurationPage from "../features/configuration/pages/ConfigurationPage.jsx";
import UsersPage from "../features/users/pages/UsersPage.jsx";
import ValidatorPage from "../features/validator/pages/ValidatorPage.jsx";
import TestPlanPage from "../features/test-plan/pages/TestPlanPage.jsx";
import GapAnalysisPage from "../features/gap-analysis/pages/GapAnalysisPage.jsx";

export default function ApplicationFrame() {
  const { status, banner } = useServiceStatus();
  const backbar = useNavigation();
  return (
    <div className="app min-h-screen" id="app-shell">
      <Sidebar />
      <div className="content min-w-0">
        <div
          className="boot-banner"
          id="boot-banner"
          hidden={!banner.visible}
          data-kind={banner.visible ? banner.kind || "warn" : undefined}
          role="status"
          aria-live="polite"
        >
          {banner.visible ? (
            <>
              <span className="boot-banner-msg">
                {banner.kind === "error" ? "⚠" : "●"} {banner.summary}
              </span>
              {banner.raw ? (
                <details className="boot-banner-details">
                  <summary>Details</summary>
                  <pre className="boot-banner-raw">{banner.raw}</pre>
                </details>
              ) : null}
            </>
          ) : null}
        </div>
        <Header status={status} />
        <main>
      <div className="ro-banner" id="ro-banner" hidden>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.8"></rect>
          <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.8"></path>
        </svg>
        <span>
          You&apos;re viewing in{" "}
          <b>read-only</b>{" "}
          mode. Your Viewer role can browse everything but can&apos;t create, edit, or delete. Ask an admin for Editor access to make changes.
        </span>
      </div>
      <Backbar model={backbar} />
        <DashboardPage />
        <ProjectsPage />
        <FeaturesPage />
        <TestCasesPage />
        <CodeAnalysisPage />
        <TestCyclesPage />
        <MindMapPage />
        <StepLibraryPage />
        <UsagePage />
        <ConfigurationPage />
        <UsersPage />
        <ValidatorPage />
        <TestPlanPage />
        <GapAnalysisPage />
        </main>
      </div>
    </div>
  );
}
