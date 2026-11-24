import { useState } from "react";

import { api } from "../../../lib/api.js";
import { currentUser, toast, uiPrompt } from "../../../lib/compatBridge.js";
import { useBusy, useCardStatus, useSectionSave, useSettingsForm } from "../hooks/useCardState.js";
import { smtpPasswordPlaceholder, smtpSaveBody } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const initSmtp = (s, loaded) => ({
  host: s.smtp_host || "",
  port: s.smtp_port || "",
  user: s.smtp_user || "",
  from: s.smtp_from || "",
  tls: loaded ? s.smtp_tls !== false : false,
  ssl: !!s.smtp_ssl,
});

/** SMTP server for sign-in codes, with a test send (card 5). */
export default function SmtpSettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initSmtp);
  const [pass, setPass] = useState("");
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? s.smtp_configured
        ? { tone: "ok", text: `SMTP configured${s.smtp_pass_set ? " (password saved)" : ""}` }
        : { tone: "warn", text: "not configured — email sign-in unavailable" }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);
  const [testing, runTest] = useBusy();

  const onSave = async () => {
    const b = smtpSaveBody({ ...form, pass });
    try {
      await save(b, b.smtp_host ? "SMTP settings saved" : "Settings saved");
      setPass("");
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save SMTP settings" });
    }
  };

  const onTest = async () => {
    const def = form.user.trim() || currentUser()?.email || "";
    const to = ((await uiPrompt("Send test email", "Send a test sign-in email to:", def)) || "").trim();
    if (!to) return;
    await runTest(async () => {
      setStatus({ tone: "", text: "Sending test email (uses saved settings)...", saving: true });
      try {
        await api("/api/smtp/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: to }),
        });
        setStatus({ tone: "ok", text: `Test email sent to ${to} — check the inbox (and spam).` });
      } catch (e) {
        setStatus({ tone: "err", text: e.message });
      }
    });
  };

  return (
    <div className="card cfg-card cfg-card-wide">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">5</span>
          <h2>Email (SMTP)</h2>
        </div>
        <span className="cfg-badge opt">Optional</span>
      </div>
      <div className="sub">
        Used to deliver sign-in codes. Until this is configured, the first admin&apos;s one-time code is printed to the server log (e.g.{" "}
        <code>docker logs wardeniq</code>
        ) so you can sign in and set it up here. Password stored encrypted.
      </div>
      <div className="sub" style={{ marginTop: "-2px" }}>
        <b>Gmail:</b>{" "}
        host{" "}
        <code>smtp.gmail.com</code>
        , port{" "}
        <code>587</code>{" "}
        (STARTTLS){" "}
        <i>or</i>{" "}
        <code>465</code>{" "}
        (SSL), username = your full Gmail address, password = a 16-character{" "}
        <b>App Password</b>{" "}
        (needs 2-Step Verification; spaces are optional). Save first, then use{" "}
        <b>Send test email</b>{" "}
        to confirm.
      </div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            SMTP host
            <span className="fi" tabIndex="0" data-tip="Your mail server's hostname, e.g. smtp.gmail.com or smtp.sendgrid.net. Until SMTP is set, the first admin's sign-in code is printed to the server log.">i</span>
          </label>
          <input
            id="cfg-smtp-host"
            placeholder="smtp.example.com"
            value={form.host}
            onChange={(e) => update({ host: e.target.value })}
          />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 130px" }}>
          <label>
            Port
            <span className="fi" tabIndex="0" data-tip="587 for STARTTLS (most common) or 465 for SSL. Match the checkbox on the right.">i</span>
          </label>
          <input
            id="cfg-smtp-port"
            type="number"
            placeholder="587"
            value={form.port}
            onChange={(e) => update({ port: e.target.value })}
          />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field">
          <label>
            Username
            <span className="fi" tabIndex="0" data-tip="The SMTP login. For Gmail use your full address; for SendGrid it is literally the word 'apikey'. Some relays allow blank.">i</span>
          </label>
          <input
            id="cfg-smtp-user"
            placeholder="apikey / user (optional)"
            value={form.user}
            onChange={(e) => update({ user: e.target.value })}
          />
        </div>
        <div className="cfg-field">
          <label>
            Password
            <span className="fi" tabIndex="0" data-tip="The SMTP password or app password. Gmail needs a 16-character App Password (2-Step Verification on). Stored encrypted; leave blank to keep the current one.">i</span>
          </label>
          <input
            type="password"
            id="cfg-smtp-pass"
            placeholder={smtpPasswordPlaceholder(s)}
            value={pass}
            onChange={(e) => setPass(e.target.value)}
          />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            From address
            <span className="fi" tabIndex="0" data-tip="The sender shown on sign-in emails, e.g. wardenIQ <no-reply@example.com>. Must be a sender your SMTP account is allowed to send as.">i</span>
          </label>
          <input
            id="cfg-smtp-from"
            placeholder="wardenIQ <no-reply@example.com>"
            value={form.from}
            onChange={(e) => update({ from: e.target.value })}
          />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 auto", alignSelf: "flex-end" }}>
          <label style={{ visibility: "hidden" }}>_</label>
          <div style={{ display: "flex", gap: "14px", alignItems: "center", padding: "8px 0" }}>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input
                type="checkbox"
                id="cfg-smtp-tls"
                style={{ width: "auto" }}
                checked={form.tls}
                onChange={(e) => update({ tls: e.target.checked })}
              />
              STARTTLS
            </label>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input
                type="checkbox"
                id="cfg-smtp-ssl"
                style={{ width: "auto" }}
                checked={form.ssl}
                onChange={(e) => update({ ssl: e.target.checked })}
              />
              SSL
            </label>
            <span className="fi" tabIndex="0" data-tip="STARTTLS = upgrade a plaintext connection to TLS (port 587). SSL = TLS from the start (port 465). Pick the one matching your port; don't enable both.">i</span>
          </div>
        </div>
      </div>
      <CardStatus id="cfg-smtp-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-smtp-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save"}
        </button>
        <button className="ghost" id="cfg-smtp-test" disabled={testing} onClick={onTest}>
          {testing ? "Sending..." : "Send test email"}
        </button>
      </div>
    </div>
  );
}
