import { loadSyncStatus, toast } from "../../../lib/compatBridge.js";
import { useCardStatus, useSectionSave, useSettingsForm } from "../hooks/useCardState.js";
import { minutesText, pollIntervalValue } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const initPoll = (s, loaded) => ({ interval: loaded ? String(pollIntervalValue(s)) : "" });

/** GitHub poll interval (card 8). */
export default function SyncSettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initPoll);
  const eff = s.poll_interval_s_effective || 1800;
  const min = settings ? s.poll_interval_min_s || 30 : 30;
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? {
          tone: "",
          node: (
            <>
              In use: <code>{`${eff}s`}</code> (≈ {minutesText(eff)} min).
              {s.poll_interval_env_writable ? (
                <>
                  {" "}
                  Saved values are also written to <code>.env</code>.
                </>
              ) : (
                <>
                  {" "}
                  Applies at runtime only — <code>.env</code> isn&apos;t writable in this deployment.
                </>
              )}
            </>
          ),
        }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);

  const onSave = async () => {
    const v = parseInt(form.interval, 10);
    if (!Number.isFinite(v) || v < min) {
      toast(`Enter a poll interval of at least ${min} seconds`, true);
      return;
    }
    try {
      await save({ poll_interval_s: v }, `Poll interval set to ${v}s (≈ ${minutesText(v)} min)`);
      loadSyncStatus();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save poll interval" });
    }
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">8</span>
          <h2>Sync &amp; polling</h2>
        </div>
        <span className="cfg-badge glob">Global</span>
      </div>
      <div className="sub">
        How often wardenIQ polls your watched GitHub repositories for new commits &amp; pull requests. GitLab is webhook-driven and unaffected. Applies on the next poll — no restart needed — and is also written to{" "}
        <code>.env</code>{" "}
        (
        <code>POLL_INTERVAL_SECONDS</code>
        ) so the config file stays in sync.
      </div>
      <div className="cfg-field" style={{ maxWidth: "320px" }}>
        <label>
          Poll interval (seconds)
          <span className="fi" tabIndex="0" data-tip="Seconds between GitHub polls of watched repos. Lower = fresher but more API calls; higher = fewer calls. Minimum 30s. Common values: 300 (5 min), 1800 (30 min), 3600 (1 hour).">i</span>
        </label>
        <input
          type="number"
          id="cfg-poll-interval"
          min={min}
          step="30"
          placeholder="1800"
          value={form.interval}
          onChange={(e) => update({ interval: e.target.value })}
        />
      </div>
      <CardStatus id="cfg-poll-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-poll-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
