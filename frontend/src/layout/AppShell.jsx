import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar.jsx";
import Header from "./Header.jsx";

const TITLES = {
  "/dashboard": "Dashboard",
  "/projects": "Projects & Repos",
  "/cases": "Test Cases",
  "/cycles": "Code Analysis & Cycles",
  "/mindmap": "Mind Map",
  "/steps": "Step Library",
  "/usage": "LLM Usage & Cost",
  "/config": "Configuration",
  "/users": "Users",
  "/validator": "Test Case Validator",
  "/testplan": "Test Plan Generator",
  "/gap": "Gap Analysis",
};

function titleFor(path) {
  // Match by longest prefix so nested routes still resolve to a parent title.
  const match = Object.keys(TITLES)
    .filter((p) => path.startsWith(p))
    .sort((a, b) => b.length - a.length)[0];
  return TITLES[match] || "wardenIQ";
}

export default function AppShell({ me, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false);
  const { pathname } = useLocation();

  return (
    <div className="flex min-h-screen">
      <Sidebar
        role={me?.role || "viewer"}
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
      />
      <div className="min-w-0 flex-1">
        <Header title={titleFor(pathname)} me={me} onSignOut={onSignOut} />
        <main className="w-full px-7 pb-8 pt-[26px]">
          {me?.role === "viewer" && (
            <div className="mb-3.5 flex items-center gap-2.5 rounded-[10px] border border-[rgba(88,166,255,.25)] bg-[rgba(88,166,255,.08)] px-3.5 py-2.5 text-[12.5px] text-[#cfe0f5]">
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="shrink-0 text-[#9cc7ff]"
              >
                <rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.8" />
                <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              <span>
                You&apos;re viewing in <b>read-only</b> mode. Your Viewer role can browse everything
                but can&apos;t create, edit, or delete. Ask an admin for Editor access to make
                changes.
              </span>
            </div>
          )}
          <Outlet context={{ me }} />
        </main>
      </div>
    </div>
  );
}
