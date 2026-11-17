/** S3SettingsCard configuration section. */
export default function S3SettingsCard() {
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
          <input id="cfg-s3-bucket" placeholder="my-wardeniq-docs-bucket" />
        </div>
        <div className="cfg-field" style={{ flex: "1" }}>
          <label>
            AWS Region
            <span className="fi" tabIndex="0" data-tip="The AWS region where your bucket resides (e.g. us-east-1, us-west-2, eu-west-1).">i</span>
          </label>
          <input id="cfg-s3-region" placeholder="us-east-1" />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field">
          <label>
            AWS Access Key ID
            <span className="fi" tabIndex="0" data-tip="Optional. Required if not using IAM roles or environment variables.">i</span>
          </label>
          <input id="cfg-s3-key" placeholder="AKIA... (optional)" />
        </div>
        <div className="cfg-field">
          <label>
            AWS Secret Access Key
            <span className="fi" tabIndex="0" data-tip="Stored encrypted. Leave blank to keep current secret key or use IAM role.">i</span>
          </label>
          <input type="password" id="cfg-s3-secret" autoComplete="off" placeholder="Secret Access Key (optional)" />
        </div>
      </div>
      <div className="cfg-row">
        <div className="cfg-field" style={{ flex: "2" }}>
          <label>
            Storage Prefix (Subfolder)
            <span className="fi" tabIndex="0" data-tip="Prefix folder within the S3 bucket. Defaults to 'documents'.">i</span>
          </label>
          <input id="cfg-s3-prefix" placeholder="documents" />
        </div>
        <div className="cfg-field" style={{ flex: "0 0 auto", alignSelf: "flex-end" }}>
          <div style={{ display: "flex", gap: "14px", alignItems: "center", padding: "8px 0" }}>
            <label style={{ display: "flex", gap: "5px", alignItems: "center", fontSize: "12px", margin: "0", color: "var(--muted)" }}>
              <input type="checkbox" id="cfg-s3-enabled" style={{ width: "auto" }} />
              Enable S3 Storage
            </label>
          </div>
        </div>
      </div>
      <div className="cfg-status muted" id="cfg-s3-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-s3-save">Save S3 Settings</button>
        <button className="ghost" id="cfg-s3-test">Test S3 Connection</button>
      </div>
    </div>
  );
}
