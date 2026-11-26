import BrandMark from "../components/brand/BrandMark.jsx";

function NavItem({ view, title, admin, children }) {
  return (
    <button data-view={view} title={title} data-admin={admin ? "1" : undefined}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {children}
      </svg>
      <span className="nav-label">{title}</span>
    </button>
  );
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="logo-row">
        <div className="sidebar-logo">
          <BrandMark size={36} centerFill="#121826" />
          <div className="logo-text">
            <span className="logo-title">Warden<span>IQ</span></span>
            <span className="logo-subtitle">Engineering Intelligence</span>
          </div>
        </div>
        <button className="sidebar-toggle" id="sidebar-toggle" title="Collapse sidebar" aria-label="Collapse sidebar">‹</button>
      </div>
      <div className="muted brand-subtitle" style={{ fontSize: "10.5px", padding: "0 10px 10px" }}>Test Intelligence Platform</div>

      <div className="sidebar-project-context" id="sidebar-project-context">
        <div className="sidebar-section-label">Current project</div>
        <div className="sidebar-project-picker">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
          </svg>
          <select id="sidebar-project-switcher" aria-label="Current project">
            <option value="">No project selected</option>
          </select>
        </div>
        <button type="button" id="sidebar-project-collapsed" className="sidebar-project-collapsed" title="No project selected" aria-label="Current project: none">—</button>
      </div>

      <nav>
        <div className="nav-section" data-nav-section="workspace">
          <div className="sidebar-section-label">Workspace</div>
          <NavItem view="dashboard" title="Dashboard">
            <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>
          </NavItem>
          <NavItem view="projects" title="Projects & Repos">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          </NavItem>
        </div>

        <div className="nav-section" data-nav-section="project">
          <div className="sidebar-section-label">Project</div>
          <NavItem view="cases" title="Test Cases">
            <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="m9 14 2 2 4-4" /></>
          </NavItem>
          <NavItem view="cycles" title="Code Analysis">
            <><path d="m9 9-2 2 2 2M13 13l2-2-2-2" /><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></>
          </NavItem>
          <NavItem view="mindmap" title="Mind Map">
            <><circle cx="12" cy="5" r="2" /><circle cx="6" cy="19" r="2" /><circle cx="18" cy="19" r="2" /><path d="M12 7v4M12 11l-6 6M12 11l6 6" /></>
          </NavItem>
          <NavItem view="testcycles" title="Test Cycles">
            <><path d="m17 2 4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3" /></>
          </NavItem>
          <NavItem view="steps" title="Step Library">
            <><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="3.5" cy="6" r="1" /><circle cx="3.5" cy="12" r="1" /><circle cx="3.5" cy="18" r="1" /></>
          </NavItem>
        </div>

        <div className="nav-section" data-nav-section="admin" data-admin-section>
          <div className="sidebar-section-label">Admin</div>
          <NavItem view="usage" title="Usage & Cost">
            <><path d="M3 3v18h18M7 14l4-4 3 3 5-6" /></>
          </NavItem>
          <NavItem view="users" title="Users" admin>
            <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0M16 5.5a3 3 0 0 1 0 5.5M21 20a5.5 5.5 0 0 0-4-5.3" /></>
          </NavItem>
          <NavItem view="config" title="Configuration" admin>
            <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82V15A1.65 1.65 0 0 0 4.09 14H4a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 5.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9.92 4H10a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 5.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1.01H21a2 2 0 0 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z" /></>
          </NavItem>
        </div>
      </nav>
    </aside>
  );
}
