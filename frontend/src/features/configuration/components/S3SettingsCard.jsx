import { useState } from "react";

import { api } from "../../../lib/api.js";
import { toast } from "../../../lib/compatBridge.js";
import { useBusy, useCardStatus, useSectionSave, useSettingsForm } from "../hooks/useCardState.js";
import { s3SaveBody, s3SecretPlaceholder } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const initS3 = (s, loaded) => ({
  bucket: s.s3_bucket || "",
  region: s.s3_region || "",
  key: s.s3_access_key_id || "",
  prefix: loaded ? s.s3_prefix || "documents" : "",
  enabled: s.s3_enabled !== false && !!s.s3_bucket,
});

/** Amazon S3 storage for uploaded documents, with a connection test (card 6). */
export default function S3SettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initS3);
  const [secret, setSecret] = useState("");
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? s.s3_configured
        ? {
            tone: "ok",
            text: `S3 configured for bucket '${s.s3_bucket}'${s.s3_secret_access_key_set ? " (secret key saved)" : ""}`,
          }
        : { tone: "muted", text: "not configured — document storage using default local mode" }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);
  const [testing, runTest] = useBusy();

  const onSave = async () => {
    const b = s3SaveBody({ ...form, secret });
    try {
      await save(b, b.s3_bucket ? "AWS S3 settings saved" : "Settings saved");
      setSecret("");
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save AWS S3 settings" });
    }
  };

  const onTest = async () => {
    const bucket = form.bucket.trim();
    if (!bucket) {
      setStatus({ tone: "err", text: "Enter an S3 bucket name to test connection" });
      return;
    }
    await runTest(async () => {
      setStatus({ tone: "", text: "Testing S3 bucket connection...", saving: true });
      try {
        const res = await api("/api/settings/s3/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            bucket,
            region: form.region.trim(),
            access_key_id: form.key.trim(),
            secret_access_key: secret.trim(),
          }),
        });
        setStatus({ tone: "ok", text: res.message || "Connected to AWS S3 bucket successfully" });
      } catch (e) {
        setStatus({ tone: "err", text: e.message });
      }
    });
  };

  return (
    <div className="card cfg-card cfg-card-wide">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">6</span>
          <h2>AWS S3 Document Storage</h2>
        </div>
        <span className="cfg-badge opt">Optional</span>
      </div>
      <div className="sub">Persist uploaded requirement documents (PDFs, DOCX, CSVs, etc.) directly into an Amazon S3 Bucket in AWS. Leave credentials blank to use standard AWS environment variables or instance IAM roles.</div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            S3 Bucket Name
            <span className="fi" tabIndex="0" data-tip="The target Amazon S3 bucket name (e.g. my-wardeniq-docs-bucket).">i</span>
          </label>
          <input
            id="cfg-s3-bucket"
            placeholder="my-wardeniq-docs-bucket"
            value={form.bucket}
            onChange={(e) => update({ bucket: e.target.value })}
          />
        </div>
        <div className="cfg-field" style={{ flex: "1" }}>
          <label>
            AWS Region
            <span className="fi" tabIndex="0" data-tip="The AWS region where your bucket resides (e.g. us-east-1, us-west-2, eu-west-1).">i</span>
          </label>
          <input
            id="cfg-s3-region"
            placeholder="us-east-1"
            value={form.region}
            onChange={(e) => update({ region: e.target.value })}
          />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field">
          <label>
            AWS Access Key ID
            <span className="fi" tabIndex="0" data-tip="Optional. Required if not using IAM roles or environment variables.">i</span>
          </label>
          <input
            id="cfg-s3-key"
            placeholder="AKIA... (optional)"
            value={form.key}
            onChange={(e) => update({ key: e.target.value })}
          />
        </div>
        <div className="cfg-field">
          <label>
            AWS Secret Access Key
            <span className="fi" tabIndex="0" data-tip="Stored encrypted. Leave blank to keep current secret key or use IAM role.">i</span>
          </label>
          <input
            type="password"
            id="cfg-s3-secret"
            placeholder={s3SecretPlaceholder(s)}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            Storage Prefix (Subfolder)
            <span className="fi" tabIndex="0" data-tip="Prefix folder within the S3 bucket. Defaults to 'documents'.">i</span>
          </label>
          <input
            id="cfg-s3-prefix"
            placeholder="documents"
            value={form.prefix}
            onChange={(e) => update({ prefix: e.target.value })}
          />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 auto", alignSelf: "flex-end" }}>
          <div style={{ display: "flex", gap: "14px", alignItems: "center", padding: "8px 0" }}>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input
                type="checkbox"
                id="cfg-s3-enabled"
                style={{ width: "auto" }}
                checked={form.enabled}
                onChange={(e) => update({ enabled: e.target.checked })}
              />
              Enable S3 Storage
            </label>
          </div>
        </div>
      </div>
      <CardStatus id="cfg-s3-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-s3-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save S3 Settings"}
        </button>
        <button className="ghost" id="cfg-s3-test" disabled={testing} onClick={onTest}>
          {testing ? "Testing..." : "Test S3 Connection"}
        </button>
      </div>
    </div>
  );
}
