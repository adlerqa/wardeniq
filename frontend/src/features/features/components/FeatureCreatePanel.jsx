/** FeatureCreatePanel for features. */
export default function FeatureCreatePanel() {
  return (
    <div id="feature-create-page" className="stage-page create-feature-form" hidden>
      <div className="stage-header">
        <button className="ghost" id="feature-create-back">All features</button>
      </div>
      <div className="card">
        <h2>New feature</h2>
        <div className="sub">Upload requirement, design, API, or architecture docs and/or paste text. All sources are embedded for RAG; the pipeline generates business, end-to-end, API, UI-validation, and edge/reliability coverage.</div>
        <select id="f-project" hidden></select>
        <div className="feature-create-fields">
          <div>
            <label>Feature name</label>
            <input id="f-name" placeholder="e.g: Login" />
          </div>
          <div>
            <label>Ticket key (optional)</label>
            <select id="f-key">
              <option value="">No Jira ticket</option>
            </select>
          </div>
          <div>
            <label>PR match tag (optional)</label>
            <input id="f-match-key" placeholder="e.g. HOLDS" />
          </div>
        </div>
        <div className="feature-create-jira-status" id="f-key-status">A linked Jira ticket lets PRs auto-link by branch/title.</div>
        <label>
          Upload documents
          <span className="muted" style={{ fontWeight: "400" }}>(PRD, HLD, LLD, architecture — PDF, DOCX, MD, TXT · you can select several)</span>
        </label>
        <input type="file" id="f-file" accept=".pdf,.docx,.md,.txt,.markdown" multiple />
        <div className="muted" id="f-filelist" style={{ fontSize: "11px" }}></div>
        <div className="muted" style={{ fontSize: "11px", marginTop: "4px" }}>Links inside PDFs (and their sub-links) are fetched automatically — public web only.</div>
        <label>
          Or paste requirement text
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
        </label>
        <textarea id="f-text" placeholder="Paste requirements, acceptance criteria, or extra context here…"></textarea>
        <label style={{ marginTop: "14px" }}>
          Confluence page link
          <span className="muted" style={{ fontWeight: "400" }}>(optional · one URL per line · uses your Jira/Atlassian token; child pages included)</span>
        </label>
        <textarea id="f-confluence" rows="2" placeholder={`https://your-org.atlassian.net/wiki/spaces/…/pages/123456/…
https://your-org.atlassian.net/wiki/spaces/…/pages/789012/…`}></textarea>
        <label style={{ marginTop: "10px" }}>
          Figma design link
          <span className="muted" style={{ fontWeight: "400" }}>(optional · one URL per line · needs a Figma token in Configuration)</span>
        </label>
        <textarea id="f-figma" rows="2" placeholder={`https://www.figma.com/file/<key>/…
https://www.figma.com/design/<key>/…`}></textarea>
        <label style={{ marginTop: "14px" }}>
          Import test sheet
          <span className="muted" style={{ fontWeight: "400" }}>(optional · CSV / XLSX)</span>
        </label>
        <input type="file" id="f-sheet" accept=".csv,.xlsx,.xlsm,.tsv" />
        <div className="muted" style={{ fontSize: "11px", marginTop: "4px" }}>
          Already keep test cases in a spreadsheet? Attach it — wardenIQ scores every row against this feature, promotes matches into the generated suite, and keeps the rest in your project library for other features to reuse.
          <a href="#" id="f-sheet-template">Download template</a>
        </div>
        <label style={{ marginTop: "10px" }}>
          Test type mix
          <span className="muted" style={{ fontWeight: "400" }}>— how much emphasis each category gets (not a fixed count)</span>
        </label>
        <div id="focus-ctrl" className="focus-panel">
          <div className="focus-row">
            <span>Functional</span>
            <input className="focus-range" type="range" min="0" max="100" defaultValue="20" id="foc-functional" />
            <b className="focus-value" id="foc-functional-v">20%</b>
          </div>
          <div className="focus-row">
            <span>UI validations</span>
            <input className="focus-range" type="range" min="0" max="100" defaultValue="20" id="foc-ui" />
            <b className="focus-value" id="foc-ui-v">20%</b>
          </div>
          <div className="focus-row">
            <span>End-to-end</span>
            <input className="focus-range" type="range" min="0" max="100" defaultValue="20" id="foc-e2e" />
            <b className="focus-value" id="foc-e2e-v">20%</b>
          </div>
          <div className="focus-row">
            <span>API</span>
            <input className="focus-range" type="range" min="0" max="100" defaultValue="20" id="foc-api" />
            <b className="focus-value" id="foc-api-v">20%</b>
          </div>
          <div className="focus-row">
            <span>Edge &amp; reliability</span>
            <input className="focus-range" type="range" min="0" max="100" defaultValue="20" id="foc-nfr" />
            <b className="focus-value" id="foc-nfr-v">20%</b>
          </div>
          <div className="focus-total">
            <span>Changing one category adjusts the largest other category first.</span>
            <span>
              Total
              <b id="foc-total">100%</b>
            </span>
          </div>
        </div>
        <div className="muted" id="f-cost-estimate" style={{ fontSize: "11px", marginTop: "10px" }}></div>
        <button className="go" id="f-go" style={{ marginTop: "12px" }}>Generate test cases</button>
        <div className="feature-create-live">
          <div className="muted" id="f-status"></div>
          <div className="job-log" id="f-log"></div>
        </div>
      </div>
    </div>
  );
}
