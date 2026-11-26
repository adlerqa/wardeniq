import { useState } from "react";
import BrandMark from "../components/brand/BrandMark.jsx";
import { navigateTo } from "../lib/compatBridge.js";

/**
 * Sidebar: navigation entries (navigateTo on click; the active entry is set by
 * app/navigation.js) and the collapse toggle (was 00-core.js).
 */
export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const toggle = () => {
    const shell = document.getElementById("app-shell");
    const now = shell ? shell.classList.toggle("sidebar-collapsed") : !collapsed;
    setCollapsed(now);
  };
  const go = (e) => {
    const b = e.target.closest("button[data-view]");
    if (b) navigateTo(b.dataset.view);
  };
  return (
    <aside className="sidebar">
      <div className="logo-row">
        <div className="sidebar-logo">
          <BrandMark size={36} centerFill="#121826" />
          <div className="logo-text">
            <span className="logo-title">
              Warden
              <span>IQ</span>
            </span>
            <span className="logo-subtitle">Engineering Intelligence</span>
          </div>
        </div>
        <button
          className="sidebar-toggle"
          id="sidebar-toggle"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={toggle}
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>
      <div className="muted brand-subtitle" style={{ fontSize: "10.5px", padding: "0 10px 10px" }}>Test Intelligence Platform</div>
      <nav onClick={go}>
        <button data-view="dashboard" title="Dashboard" className="active">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
          </svg>
          <span className="nav-label">Dashboard</span>
        </button>
        <button data-view="projects" title="Projects & Repos">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
          </svg>
          <span className="nav-label">Projects &amp; Repos</span>
        </button>
        <button data-view="cases" title="Test Cases">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="8" y="2" width="8" height="4" rx="1"></rect>
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
            <path d="m9 14 2 2 4-4"></path>
          </svg>
          <span className="nav-label">Test Cases</span>
        </button>
        <button data-view="cycles" title="Code Analysis">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="m9 9-2 2 2 2"></path>
            <path d="m13 13 2-2-2-2"></path>
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.3-4.3"></path>
          </svg>
          <span className="nav-label">Code Analysis</span>
        </button>
        <button data-view="mindmap" title="Mind Map">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="5" r="2"></circle>
            <circle cx="6" cy="19" r="2"></circle>
            <circle cx="18" cy="19" r="2"></circle>
            <path d="M12 7v4M12 11l-6 6M12 11l6 6"></path>
          </svg>
          <span className="nav-label">Mind Map</span>
        </button>
        <button data-view="testcycles" title="Test Cycles">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="m17 2 4 4-4 4"></path>
            <path d="M3 11v-1a4 4 0 0 1 4-4h14"></path>
            <path d="m7 22-4-4 4-4"></path>
            <path d="M21 13v1a4 4 0 0 1-4 4H3"></path>
          </svg>
          <span className="nav-label">Test Cycles</span>
        </button>
        <button data-view="steps" title="Step Library">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 6h13M8 12h13M8 18h13"></path>
            <circle cx="3.5" cy="6" r="1"></circle>
            <circle cx="3.5" cy="12" r="1"></circle>
            <circle cx="3.5" cy="18" r="1"></circle>
          </svg>
          <span className="nav-label">Step Library</span>
        </button>
        <button data-view="usage" title="LLM Usage & Cost">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18"></path>
            <path d="M7 14l4-4 3 3 5-6"></path>
          </svg>
          <span className="nav-label">Usage &amp; Cost</span>
        </button>
        <button data-view="users" title="Users" data-admin="1" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="9" cy="8" r="3"></circle>
            <path d="M3 20a6 6 0 0 1 12 0"></path>
            <path d="M16 5.5a3 3 0 0 1 0 5.5M21 20a5.5 5.5 0 0 0-4-5.3"></path>
          </svg>
          <span className="nav-label">Users</span>
        </button>
        <button data-view="config" title="Configuration" data-admin="1">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
          </svg>
          <span className="nav-label">Configuration</span>
        </button>
      </nav>
    </aside>
  );
}
