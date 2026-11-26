import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api.js";
import { roleDescription, setCurrentUser, showLogin, toast, uiConfirm } from "../../../lib/compatBridge.js";
import { inviteRows } from "../lib/identity.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

/**
 * Pending-invitation gate shown after sign-in (was 10-auth.js maybeShowInvite).
 * Registers window.maybeShowInvite(), which resolves true while an invite is
 * shown (the caller must not start the app yet). Accept starts the app; Decline
 * signs out.
 */
export default function InviteGate() {
  const [invite, setInvite] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState({ accept: false, decline: false });
  const busyRef = useRef(busy);
  busyRef.current = busy;

  useEffect(() => {
    const fn = async () => {
      try {
        const r = await api("/api/auth/my-invite");
        const inv = r && r.invite;
        if (!inv || !inv.pending) {
          setInvite(null);
          return false;
        }
        setErr("");
        setInvite(inv);
        return true;
      } catch {
        setInvite(null);
        return false;
      }
    };
    window.maybeShowInvite = fn;
    return () => {
      if (window.maybeShowInvite === fn) delete window.maybeShowInvite;
    };
  }, []);

  const run = async (key, fn) => {
    setBusy((b) => ({ ...b, [key]: true }));
    setErr("");
    try {
      await fn();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  };
  const accept = () =>
    run("accept", async () => {
      const r = await api("/api/auth/invite/accept", { method: "POST" });
      if (r && r.user) setCurrentUser(r.user);
      setInvite(null);
      callWindow("applyRole");
      toast("Invitation accepted — welcome!");
      callWindow("startApp");
    });
  const decline = async () => {
    if (
      !(await uiConfirm(
        "Decline this invitation? You'll be signed out and won't have access.",
        "Decline invitation",
        "Decline",
        true,
      ))
    )
      return;
    await run("decline", async () => {
      await api("/api/auth/invite/decline", { method: "POST" });
      setInvite(null);
      setCurrentUser(null);
      showLogin();
      toast("Invitation declined.");
    });
  };

  const desc = invite ? roleDescription(invite.role) : "";
  return (
    <div id="invite-gate" hidden={!invite}>
      <div className="box invite-box">
        <div className="invite-icon">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 7l9 6 9-6" stroke="#1ce5b2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"></path>
            <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="#1ce5b2" strokeWidth="1.8"></rect>
          </svg>
        </div>
        <h2 style={{ margin: "6px 0 2px" }}>You&apos;ve been invited</h2>
        <p className="muted" id="invite-sub" style={{ marginTop: "0" }}>
          You&apos;ve been invited to join
          <b id="invite-workspace">{invite ? invite.workspace || "WardenIQ" : "WardenIQ"}</b>
          .
        </p>
        <div className="invite-meta" id="invite-meta">
          {invite
            ? inviteRows(invite).map(([k, v]) => (
                <div className="row" key={k}>
                  <span>{k}</span>
                  <span>{"role" in v ? <span className={`rolebadge ${v.role}`}>{v.role}</span> : v.text}</span>
                </div>
              ))
            : null}
          {desc ? <div className="row-desc">{desc}</div> : null}
        </div>
        <div className="invite-actions">
          <button className="go" id="invite-accept" disabled={busy.accept} onClick={accept}>
            Accept invitation
          </button>
          <button className="ghost" id="invite-decline" disabled={busy.decline} onClick={decline}>
            Decline
          </button>
        </div>
        <div className="err" id="invite-err">
          {err}
        </div>
      </div>
    </div>
  );
}
