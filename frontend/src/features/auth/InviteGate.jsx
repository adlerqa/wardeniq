import { useState } from "react";
import { api } from "../../lib/api";

// After a successful sign-in, the backend may return `pending_invite: true`
// when the user was invited to one or more projects but hasn't accepted yet.
// This gate intercepts the app until the invite is accepted or declined.
export default function InviteGate({ me, onDone }) {
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const invite = me?.pending_invite || {};
  const inviteEntries = Object.entries(invite).filter(
    ([k]) => !["projects", "invited_by", "email"].includes(k)
  );

  const act = async (accept) => {
    setBusy(true);
    setErr("");
    try {
      await api(accept ? "/api/auth/invite/accept" : "/api/auth/invite/decline", {
        method: "POST",
      });
      onDone?.();
    } catch (e) {
      setErr(e.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div id="invite-gate">
      <div className="box invite-box">
        <div className="invite-icon">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M3 7l9 6 9-6"
              stroke="#1ce5b2"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="#1ce5b2" strokeWidth="1.8" />
          </svg>
        </div>
        <h2 style={{ margin: "6px 0 2px" }}>You&apos;ve been invited</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          You&apos;ve been invited to join <b>{invite.workspace || "WardenIQ"}</b>.
        </p>

        {invite.projects?.length > 0 && (
          <div className="invite-meta">
            <div className="row">
              <span>Projects</span>
              <span>{invite.projects.map((p) => p.name || p).join(", ")}</span>
            </div>
            {inviteEntries.map(([k, v]) => (
              <div className="row" key={k}>
                <span style={{ textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                <span>{String(v)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="invite-actions">
          <button className="go" disabled={busy} onClick={() => act(true)}>
            {busy ? "Working…" : "Accept invitation"}
          </button>
          <button className="ghost" disabled={busy} onClick={() => act(false)}>
            Decline
          </button>
        </div>
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  );
}
