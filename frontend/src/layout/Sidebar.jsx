import { NavLink } from "react-router-dom";

// Sidebar navigation — idiomatic React port of the <aside class="sidebar"> block
// in app/static/index.html. Styling is expressed as inline Tailwind utilities
// (no dependency on global.css sidebar rules) so this component matches the
// current "reference restyle" look: icon + label rows, slate palette, a soft
// gradient panel, and a white/10 active pill. Admin-only routes are hidden for
// viewer/editor roles. Collapsed mode centers the icons and hides the labels.

// Each nav item carries its lucide-style icon as SVG children (same paths the
// legacy markup uses) so the icon set stays identical across both frontends.
const NAV_ITEMS = [
  {
    to: "/dashboard",
    label: "Dashboard",
    icon: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
  },
  {
    to: "/projects",
    label: "Projects & Repos",
    icon: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  },
  {
    to: "/cases",
    label: "Test Cases",
    icon: (
      <>
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </>
    ),
  },
  {
    to: "/cycles",
    label: "Code Analysis & Cycles",
    icon: <path d="M3 12a9 9 0 1 0 9-9 9 9 0 0 0-7 3.5M3 4v4h4" />,
  },
  {
    to: "/mindmap",
    label: "Mind Map",
    icon: (
      <>
        <circle cx="6" cy="12" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="18" cy="18" r="2.5" />
        <path d="M8.2 10.9l7.6-3.8M8.2 13.1l7.6 3.8" />
      </>
    ),
  },
  {
    to: "/steps",
    label: "Step Library",
    icon: (
      <>
        <path d="M8 6h13M8 12h13M8 18h13" />
        <circle cx="3.5" cy="6" r="1" />
        <circle cx="3.5" cy="12" r="1" />
        <circle cx="3.5" cy="18" r="1" />
      </>
    ),
  },
  {
    to: "/usage",
    label: "Usage & Cost",
    icon: (
      <>
        <path d="M3 3v18h18" />
        <path d="M7 14l4-4 3 3 5-6" />
      </>
    ),
  },
  {
    to: "/users",
    label: "Users",
    adminOnly: true,
    icon: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20a6 6 0 0 1 12 0" />
        <path d="M16 5.5a3 3 0 0 1 0 5.5M21 20a5.5 5.5 0 0 0-4-5.3" />
      </>
    ),
  },
  {
    to: "/config",
    label: "Configuration",
    adminOnly: true,
    icon: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </>
    ),
  },
];

function NavIcon({ children, collapsed }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={"h-5 w-5 flex-[0_0_20px] " + (collapsed ? "" : "")}
    >
      {children}
    </svg>
  );
}

export default function Sidebar({ role, collapsed, onToggle }) {
  const isAdmin = role === "admin";

  return (
    <aside
      className={
        "flex flex-col border-r border-[#1e293b] bg-gradient-to-b from-[#0b1622] to-[#0e1c2a] backdrop-blur-md transition-[width,flex-basis] duration-200 " +
        (collapsed ? "w-16 flex-[0_0_4rem] px-2.5 py-[22px]" : "w-60 flex-[0_0_15rem] px-3.5 py-[22px]")
      }
    >
      {/* Logo row */}
      <div className={"mb-1 flex items-center " + (collapsed ? "justify-center" : "justify-between")}>
        <div className="flex min-w-0 items-center gap-2.5">
          <svg
            width="36"
            height="36"
            viewBox="0 0 100 80"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="shrink-0"
          >
            <rect x="22" y="10" width="12" height="60" fill="#1c7ec2" />
            <rect x="44" y="10" width="12" height="60" fill="#1c7ec2" />
            <rect x="66" y="10" width="12" height="60" fill="#1c7ec2" />
            <path
              d="M 5,38 C 15,38 15,48 25,48 H 36 C 44,48 44,40 50,40 C 56,40 56,48 64,48 H 75 C 85,48 85,62 95,62"
              stroke="#1ce5b2"
              strokeWidth="5"
              fill="none"
              strokeLinecap="round"
            />
            <circle cx="5" cy="38" r="5" fill="#1ce5b2" />
            <circle cx="5" cy="38" r="2.2" fill="#121826" />
            <circle cx="95" cy="62" r="5" fill="#1ce5b2" />
            <circle cx="95" cy="62" r="2.2" fill="#121826" />
            <circle cx="50" cy="40" r="10" fill="#121826" stroke="#1ce5b2" strokeWidth="5" />
          </svg>
          {!collapsed && (
            <div className="flex min-w-0 flex-col leading-tight">
              <span className="text-[19px] font-semibold tracking-tight text-text">
                Warden
                <span className="bg-gradient-to-r from-accent to-accent2 bg-clip-text text-transparent">IQ</span>
              </span>
              <span className="truncate text-[10.5px] text-muted">Engineering Intelligence</span>
            </div>
          )}
        </div>
        <button
          type="button"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggle}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] border border-white/10 bg-white/[.03] text-[#94a3b8] transition-colors hover:border-white/20 hover:bg-white/[.06] hover:text-[#e2e8f0]"
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      {!collapsed && (
        <div className="px-2.5 pb-2.5 text-[10.5px] text-muted">Test Intelligence Platform</div>
      )}

      <nav className="flex flex-col gap-1.5">
        {NAV_ITEMS.filter((it) => !it.adminOnly || isAdmin).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={item.label}
            className={({ isActive }) =>
              "flex w-full items-center rounded-xl text-left text-sm font-medium transition-colors " +
              (collapsed ? "justify-center gap-0 px-0 py-[11px]" : "gap-3 px-3 py-2.5") +
              " " +
              (isActive
                ? "bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,.10)] [&_svg]:text-white"
                : "text-[#cbd5e1] [&_svg]:text-[#94a3b8] hover:bg-white/5 hover:text-white [&:hover_svg]:text-[#e2e8f0]")
            }
          >
            <NavIcon collapsed={collapsed}>{item.icon}</NavIcon>
            {!collapsed && (
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
