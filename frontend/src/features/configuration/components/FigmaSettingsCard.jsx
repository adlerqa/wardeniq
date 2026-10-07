/** FigmaSettingsCard configuration section. */
export default function FigmaSettingsCard() {
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
        <input type="password" id="cfg-figma-token" placeholder="API token is required" />
      </div>
      <div className="cfg-status muted" id="cfg-figma-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-figma-save">Save</button>
      </div>
    </div>
  );
}
