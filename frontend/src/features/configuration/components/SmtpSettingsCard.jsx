/** SmtpSettingsCard configuration section. */
export default function SmtpSettingsCard() {
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
          <input id="cfg-smtp-host" placeholder="smtp.example.com" />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 130px" }}>
          <label>
            Port
            <span className="fi" tabIndex="0" data-tip="587 for STARTTLS (most common) or 465 for SSL. Match the checkbox on the right.">i</span>
          </label>
          <input id="cfg-smtp-port" type="number" placeholder="587" />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field">
          <label>
            Username
            <span className="fi" tabIndex="0" data-tip="The SMTP login. For Gmail use your full address; for SendGrid it is literally the word 'apikey'. Some relays allow blank.">i</span>
          </label>
          <input id="cfg-smtp-user" placeholder="apikey / user (optional)" />
        </div>
        <div className="cfg-field">
          <label>
            Password
            <span className="fi" tabIndex="0" data-tip="The SMTP password or app password. Gmail needs a 16-character App Password (2-Step Verification on). Stored encrypted; leave blank to keep the current one.">i</span>
          </label>
          <input type="password" id="cfg-smtp-pass" placeholder="API token is required" />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            From address
            <span className="fi" tabIndex="0" data-tip="The sender shown on sign-in emails, e.g. wardenIQ <no-reply@example.com>. Must be a sender your SMTP account is allowed to send as.">i</span>
          </label>
          <input id="cfg-smtp-from" placeholder="wardenIQ <no-reply@example.com>" />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 auto", alignSelf: "flex-end" }}>
          <label style={{ visibility: "hidden" }}>_</label>
          <div style={{ display: "flex", gap: "14px", alignItems: "center", padding: "8px 0" }}>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input type="checkbox" id="cfg-smtp-tls" style={{ width: "auto" }} />
              STARTTLS
            </label>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input type="checkbox" id="cfg-smtp-ssl" style={{ width: "auto" }} />
              SSL
            </label>
            <span className="fi" tabIndex="0" data-tip="STARTTLS = upgrade a plaintext connection to TLS (port 587). SSL = TLS from the start (port 465). Pick the one matching your port; don't enable both.">i</span>
          </div>
        </div>
      </div>
      <div className="cfg-status muted" id="cfg-smtp-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-smtp-save">Save</button>
        <button className="ghost" id="cfg-smtp-test">Send test email</button>
      </div>
    </div>
  );
}
