import { useState } from "react";

import { toast } from "../../../lib/compatBridge.js";
import { useCardStatus, useSectionSave } from "../hooks/useCardState.js";
import { figmaTokenPlaceholder } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

/** Figma personal access token (card 4). */
export default function FigmaSettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [token, setToken] = useState("");
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? s.figma_token_set
        ? { tone: "ok", text: "Figma token configured" }
        : { tone: "muted", text: "no Figma token set" }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);

  const onSave = async () => {
    if (!token) {
      toast("Enter a Figma token", true);
      return;
    }
    try {
      await save({ figma_api_token: token }, "Figma token saved");
      setToken("");
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save Figma token" });
    }
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">4</span>
          <h2>Figma</h2>
        </div>
        <span className="cfg-badge opt">Optional</span>
      </div>
      <div className="sub">
        A Figma{" "}
        <b>personal access token</b>{" "}
        lets features extract design screens &amp; text from a Figma link (Figma&apos;s API requires a token).{" "}
        <a href="https://www.figma.com/developers/api#access-tokens" target="_blank" rel="noopener noreferrer">Create one</a>
        . Stored encrypted.
      </div>
      <div className="cfg-field">
        <label>
          Access token
          <span className="fi" tabIndex="0" data-tip="A Figma personal access token (figma.com → Settings → Personal access tokens). Lets features pull screens and text from a Figma link. Stored encrypted; leave blank to keep the current one.">i</span>
        </label>
        <input
          type="password"
          id="cfg-figma-token"
          placeholder={figmaTokenPlaceholder(s)}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
      </div>
      <CardStatus id="cfg-figma-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-figma-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
