import { useState } from "react";

import { SkeletonBlockLines, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { api } from "../../../lib/api.js";
import { confirmModal, formatBootStatus, watchJob } from "../../../lib/compatBridge.js";
import { isBusyRefusal, isTargetNotEmpty } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const SWITCH_LABEL = "Switch to this database";

function Connection({ data }) {
  const boot = data.boot || {};
  const msg = formatBootStatus(boot);
  let value;
  if (boot.stage === "error")
    value = (
      <>
        <span className="err">⚠ {msg.summary || "not ready"}</span>
        {msg.raw ? (
          <details className="boot-banner-details">
            <summary>Details</summary>
            <pre className="boot-banner-raw">{msg.raw}</pre>
          </details>
        ) : null}
      </>
    );
  else if (boot.ready) value = <span className="ok">● connected</span>;
  else value = <span className="warn">● {boot.stage || "starting"}</span>;
  return (
    <div className="db-table">
      <div className="db-r">
        <span className="db-k">Connection</span>
        <span className="db-v">{value}</span>
      </div>
    </div>
  );
}

function DbBody({ db }) {
  if (db.status === "idle") return <span className="muted">Loading database status…</span>;
  if (db.status === "loading")
    return (
      <SkeletonState label="Loading database status">
        <SkeletonBlockLines count={3} />
      </SkeletonState>
    );
  if (db.status === "error") return <span className="err">{db.error}</span>;
  return <Connection data={db.data} />;
}

/**
 * Database status and "switch to another database" (card 7). The switch
 * copies the data into the target, then asks for a restart; a target that
 * already has data, or a busy wardenIQ, gets one yes / no question (#111).
 */
export default function DatabaseSettingsCard({ db, loadDbStatus }) {
  const [uri, setUri] = useState("");
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const runDbSwitch = async (target, overwrite, overrideBusy) => {
    setBusy(true);
    setStatus({ tone: "", text: "Checking the database…", saving: true });
    let r;
    try {
      r = await api("/api/db-migrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_uri: target, overwrite: !!overwrite, override_busy: !!overrideBusy }),
      });
    } catch (e) {
      setBusy(false);
      // A target that already has data: one clear yes / no.
      if (!overwrite && isTargetNotEmpty(e.message)) {
        const yes = await confirmModal({
          title: "Replace existing data?",
          body: "That database already has data in it.\n\nReplace it with your current data?",
          confirmText: "Replace data",
          danger: true,
        });
        if (yes) return runDbSwitch(target, true, overrideBusy);
        setStatus({ tone: "muted", text: "Cancelled — pick an empty database, or confirm replacing it." });
        return;
      }
      // Copying a live database can capture it half-written, so the server
      // refuses unless the user accepts a best-effort snapshot.
      if (!overrideBusy && isBusyRefusal(e.message)) {
        const yes = await confirmModal({
          title: "wardenIQ is busy",
          body: `${e.message}\n\nCopying while it is busy is a best-effort snapshot: changes made during the copy may not be included. Start anyway?`,
          confirmText: "Start anyway",
          danger: true,
        });
        if (yes) return runDbSwitch(target, overwrite, true);
        setStatus({ tone: "muted", text: "Cancelled — try again once wardenIQ is idle." });
        return;
      }
      setStatus({ tone: "err", text: e.message });
      return;
    }
    watchJob(r.job_id, (j) => {
      if (j.status === "running") {
        setStatus({ tone: "", text: `Transferring your data…${j.progress ? ` ${j.progress}%` : ""}`, saving: true });
      } else if (j.status === "succeeded") {
        const res = j.result || {};
        // A best-effort copy can pass with warnings: never hide them.
        setStatus({
          tone: "",
          node: (
            <>
              <span className="ok">Your data has been copied to the new database.</span>
              {(res.warnings || []).map((w, i) => (
                <div key={i} className="warn">
                  {w}
                </div>
              ))}{" "}
              Run <code>{res.apply_cmd || "docker compose up -d"}</code> to finish switching.
              {res.post_restart_check ? <div className="muted">{res.post_restart_check}</div> : null}
            </>
          ),
        });
        setUri("");
        setBusy(false);
      } else {
        setStatus({ tone: "err", text: `Couldn't switch: ${j.error || "unknown error"}` });
        setBusy(false);
      }
    });
  };

  const onSwitch = async () => {
    const target = uri.trim();
    if (!target) {
      setStatus({ tone: "warn", text: "Enter a database connection string." });
      return;
    }
    const yes = await confirmModal({
      title: "Switch database?",
      body: "Copy your data to this database and switch wardenIQ to it?\n\nYour current database stays intact until you restart, so nothing is lost. The copy is a best-effort snapshot taken while wardenIQ is idle, and it is verified before wardenIQ is switched.",
      confirmText: "Switch database",
    });
    if (yes) runDbSwitch(target, false, false);
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">7</span>
          <h2>Database</h2>
        </div>
        <span className="cfg-badge glob">Global</span>
      </div>
      <div className="sub">
        Connect wardenIQ to a search-capable MongoDB (Atlas, or self-managed with mongot). Enter the connection string below. It is saved to{" "}
        <code>.env</code>{" "}
        and never shown again.
      </div>
      <div id="cfg-db-body" className="db-panel">
        <DbBody db={db} />
      </div>
      <div id="cfg-db-switch" style={{ marginTop: "16px", borderTop: "1px solid rgba(255,255,255,.06)", paddingTop: "14px", display: db.shown ? "block" : "none" }}>
        <div className="muted" style={{ fontSize: "12px", lineHeight: "1.55", marginBottom: "12px" }}>Enter the database you&apos;d like to use. wardenIQ copies your data into it and switches over — your current database is left untouched until you restart, so nothing is lost.</div>
        <div className="cfg-field">
          <label>
            Database connection string
            <span className="fi" tabIndex="0" data-tip="A search-capable MongoDB URI (Atlas mongodb+srv://… or a self-managed replica set with mongot). wardenIQ copies your data into it and switches over. Saved to .env, encrypted, and never shown again.">i</span>
          </label>
          <input
            type="password"
            id="cfg-db-uri"
            placeholder="mongodb+srv://user:pass@cluster…"
            autoComplete="off"
            value={uri}
            onChange={(e) => setUri(e.target.value)}
          />
        </div>
        <CardStatus id="cfg-db-status" status={status} />
        <div className="cfg-actions" style={{ border: "none", padding: "0", margin: "0" }}>
          <button className="go" id="cfg-db-switch-go" disabled={busy} onClick={onSwitch}>
            {busy ? "Starting…" : SWITCH_LABEL}
          </button>
        </div>
      </div>
      <div className="cfg-actions">
        <button className="ghost" id="cfg-db-refresh" onClick={loadDbStatus}>
          Refresh
        </button>
      </div>
    </div>
  );
}
