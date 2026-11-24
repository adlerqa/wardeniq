import { useState } from "react";

import { toast } from "../../../lib/compatBridge.js";
import { useCardStatus, useSectionSave, useSettingsForm } from "../hooks/useCardState.js";
import { jiraTokenPlaceholder } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const initJira = (s) => ({ base: s.jira_base_url || "", email: s.jira_email || "" });

/** Atlassian Cloud account used for Jira and Confluence (card 3). */
export default function AtlassianSettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initJira);
  const [token, setToken] = useState("");
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? s.jira_token_readable
        ? { tone: "ok", text: "Jira token configured" }
        : s.jira_token_set
          ? { tone: "warn", text: "saved token can't be read — re-enter it below" }
          : { tone: "muted", text: "no Jira token set" }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);

  const onSave = async () => {
    const b = { jira_base_url: form.base.trim(), jira_email: form.email.trim() };
    if (token) b.jira_api_token = token;
    // Nothing entered and nothing stored: the backend would accept the empty
    // values and report success, which reads as "Jira is now configured".
    if (!b.jira_base_url && !b.jira_email && !token && !s.jira_token_set) {
      toast("Enter Base URL, Email and API token to configure Jira", true);
      return;
    }
    // A stored token that can no longer be decrypted cannot be kept.
    if (!token && s.jira_token_set && !s.jira_token_readable) {
      toast("Your saved Jira API token can no longer be read — re-enter it to save", true);
      return;
    }
    try {
      await save(b, "Jira settings saved");
      setToken("");
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save Jira settings" });
    }
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">3</span>
          <h2>Jira &amp; Confluence (Atlassian Cloud)</h2>
        </div>
        <span className="cfg-badge opt">Optional</span>
      </div>
      <div className="sub">
        One Atlassian account for the whole workspace. wardenIQ uses it to read issues, list Jira projects/Confluence spaces when you create a project, and write coverage updates as comments. Create an API token at{" "}
        <code>id.atlassian.com → Security → API tokens</code>
        .
      </div>
      <div className="cfg-field">
        <label>
          Base URL
          <span className="fi" tabIndex="0" data-tip="Your Atlassian Cloud site URL, e.g. https://your-org.atlassian.net (no trailing path).">i</span>
        </label>
        <input
          id="cfg-jira-base"
          placeholder="https://your-org.atlassian.net"
          value={form.base}
          onChange={(e) => update({ base: e.target.value })}
        />
      </div>
      <div className="cfg-field">
        <label>
          Email
          <span className="fi" tabIndex="0" data-tip="The Atlassian account email that owns the API token below. Used with the token for Basic auth.">i</span>
        </label>
        <input
          id="cfg-jira-email"
          placeholder="you@org.com"
          value={form.email}
          onChange={(e) => update({ email: e.target.value })}
        />
      </div>
      <div className="cfg-field">
        <label>
          API token
          <span className="fi" tabIndex="0" data-tip="An Atlassian API token (not your password). Create one at id.atlassian.com → Security → API tokens. Stored encrypted; leave blank to keep the current one.">i</span>
        </label>
        <input
          type="password"
          id="cfg-jira-token"
          placeholder={jiraTokenPlaceholder(s)}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
      </div>
      <CardStatus id="cfg-jira-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-jira-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save"}
        </button>
      </div>
      <div className="muted" style={{ fontSize: "11px", marginTop: "10px" }}>
        Webhook:{" "}
        <code>/api/integrations/jira/webhook?token=&lt;WEBHOOK_SECRET&gt;</code>{" "}
        auto-creates features from new issues.
      </div>
    </div>
  );
}
