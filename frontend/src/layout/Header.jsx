import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

// Top-of-page header — idiomatic React port of the <header> block in
// app/static/index.html. Left: current view title; right: live service/status
// counts + the user menu. Styling is inline Tailwind (matches the frosted
// translucent header from the index.html theme glow-up).

const ROLE_BADGE = {
  admin: "bg-[rgba(19,112,171,.18)] text-[#8fd0ff]",
  editor: "bg-[rgba(88,166,255,.16)] text-[#9cc7ff]",
  viewer: "bg-white/[.08] text-muted",
};

function StatusDot({ ok }) {
  return (
    <span
      className={
        "mr-[5px] inline-block h-2 w-2 rounded-full " +
        (ok
          ? "bg-green shadow-[0_0_9px_rgba(52,211,153,.6)]"
          : "bg-red shadow-[0_0_9px_rgba(248,113,113,.5)]")
      }
    />
  );
}

export default function Header({ title, me, onSignOut }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const s = await api("/api/status");
        if (alive) setStatus(s);
      } catch {
        if (alive) setStatus(null);
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const counts = status?.counts || {};
  const services = status?.services || {};
  const role = me?.role || "viewer";

  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-[rgba(18,24,34,.72)] px-[26px] py-4 backdrop-blur-[10px]">
      <h1 className="m-0 text-[17px] font-semibold tracking-tight">{title}</h1>
      <div className="flex items-center gap-4">
        <div className="flex flex-wrap gap-3 text-xs">
          {status ? (
            <>
              <span className="text-muted">
                <StatusDot ok={services.mongo} />
                Mongo
              </span>
              <span className="text-muted">
                <StatusDot ok={services.mongot} />
                mongot
              </span>
              <span className="text-muted">
                <StatusDot ok={services.ollama} />
                LLM
              </span>
              {typeof counts.features === "number" && (
                <span className="text-muted">
                  <b className="text-text">{counts.features}</b> features
                </span>
              )}
              {typeof counts.cases === "number" && (
                <span className="text-muted">
                  <b className="text-text">{counts.cases}</b> cases
                </span>
              )}
            </>
          ) : (
            <span className="text-muted">loading…</span>
          )}
        </div>
        {me && (
          <div className="flex items-center gap-2.5">
            <span className="text-xs text-muted">{me.email}</span>
            <span
              className={
                "rounded-full px-[9px] py-0.5 text-[10.5px] font-semibold uppercase tracking-[.4px] " +
                (ROLE_BADGE[role] || ROLE_BADGE.viewer)
              }
            >
              {me.role}
            </span>
            <button
              type="button"
              onClick={onSignOut}
              className="rounded-[9px] border border-line px-2.5 py-1 text-sm text-muted transition-colors hover:border-accent hover:bg-[rgba(19,112,171,.08)] hover:text-text"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
