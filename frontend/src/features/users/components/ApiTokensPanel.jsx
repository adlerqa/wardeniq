import { useCallback, useEffect, useId, useRef, useState } from "react";

import { SkeletonLine, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { api } from "../../../lib/api.js";
import { toast, uiConfirm, uiModalHTML } from "../../../lib/compatBridge.js";
import {
  EMPTY_TEXT,
  NO_PROJECTS_TEXT,
  buildCreateBody,
  formatTimestamp,
  revokeConfirmMessage,
  scopeFromForm,
  tokenAccess,
  tokenCreatedHtml,
  validateTokenForm,
} from "../lib/apiTokens.js";

const BADGE =
  "rounded-[20px] border border-solid border-transparent px-[11px] py-1 text-[10.5px] font-medium";

function LoadingTable() {
  const cols = [0, 1, 2, 3];
  return (
    <SkeletonState label="Loading API tokens">
      <div className="overflow-auto">
        <table>
          <tbody>
            <tr>
              {cols.map((c) => (
                <th key={c}>
                  <SkeletonLine size="sm" className="!my-0 !w-[70%]" />
                </th>
              ))}
            </tr>
            {[0, 1, 2, 3, 4, 5].map((r) => (
              <tr key={r}>
                {cols.map((c) => (
                  <td key={c}>
                    <SkeletonLine className="!my-0" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SkeletonState>
  );
}

function AccessCell({ token, projects }) {
  const access = tokenAccess(token, projects);
  const cls = "text-[11.5px] text-muted";
  if (access.kind === "all") return <span className={cls}>All projects</span>;
  if (access.kind === "none")
    return <span className={`${cls} !text-red`}>No projects</span>;
  return (
    <span className={cls}>
      {access.names.map((n, i) => (
        <span
          key={`${n}-${i}`}
          className="mx-0.5 my-px inline-block rounded-xl border border-solid border-line bg-white/[0.06] px-2 py-px text-text"
        >
          {n}
        </span>
      ))}
    </span>
  );
}

function TokenTable({ tokens, projects, onRevoke }) {
  if (!tokens.length)
    return <div className="py-4 text-[12px] text-muted">{EMPTY_TEXT}</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Role</th>
          <th>Access</th>
          <th>Status</th>
          <th>Last used</th>
          <th>Expires</th>
          <th>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {tokens.map((t) => (
          <tr key={t.id}>
            <td>{t.name}</td>
            <td>{t.role}</td>
            <td>
              <AccessCell token={t} projects={projects} />
            </td>
            <td>
              {t.active ? (
                <span className={`${BADGE} bg-[rgba(52,211,153,0.16)] text-[#7eecc0]`}>
                  active
                </span>
              ) : (
                <span className={`${BADGE} bg-white/[0.06] text-muted`}>revoked</span>
              )}
            </td>
            <td className="text-[12px] text-muted">{formatTimestamp(t.last_used_at)}</td>
            <td className="text-[12px] text-muted">{formatTimestamp(t.expires_at)}</td>
            <td>
              <div className="flex flex-nowrap justify-end gap-1.5">
                {t.active && (
                  <button
                    type="button"
                    onClick={() => onRevoke(t)}
                    className="inline-flex cursor-pointer items-center gap-[5px] whitespace-nowrap rounded-[9px] border-none bg-transparent bg-[linear-gradient(135deg,#fb7185,#ef4444)] px-[13px] py-2 text-[12px] font-medium text-[#f4a3a3] transition-[background,border-color] duration-[120ms] hover:bg-none hover:bg-[rgba(239,68,68,0.14)] hover:text-[#fca5a5]"
                  >
                    Revoke
                  </button>
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * API tokens panel on the Users screen (admin only): create and revoke
 * service-account bearer tokens. Data loads when the Users screen opens:
 * navigateTo("users") in the compatibility runtime calls window.loadApiTokens(),
 * which this component registers while it is mounted. It does not load on
 * mount, because the panel is mounted (hidden) for every role and the API is
 * admin-only.
 */
export default function ApiTokensPanel() {
  const uid = useId();
  const [projects, setProjects] = useState([]);
  const [tokens, setTokens] = useState([]);
  // idle (never loaded) | loading | ready | error
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [expiresDays, setExpiresDays] = useState("");
  const [scopeMode, setScopeMode] = useState("all");
  const [selected, setSelected] = useState([]);
  const loadSeq = useRef(0);
  const mounted = useRef(false);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    const current = () => mounted.current && seq === loadSeq.current;
    setStatus("loading");
    setError("");
    // Project names are optional context: a failure here still shows the tokens.
    let projectList = [];
    try {
      const pr = await api("/api/projects");
      projectList = pr.projects || [];
    } catch {
      projectList = [];
    }
    if (!current()) return;
    setProjects(projectList);
    setSelected([]);
    try {
      const r = await api("/api/api-tokens");
      if (!current()) return;
      setTokens(r.tokens || []);
      setStatus("ready");
    } catch (e) {
      if (!current()) return;
      setError(e.message);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const hook = () => load();
    window.loadApiTokens = hook;
    return () => {
      mounted.current = false;
      if (window.loadApiTokens === hook) delete window.loadApiTokens;
    };
  }, [load]);

  async function createToken() {
    const scope = scopeFromForm(scopeMode, selected);
    const invalid = validateTokenForm({ name, scope });
    if (invalid) {
      toast(invalid, true);
      return;
    }
    try {
      const r = await api("/api/api-tokens", {
        method: "POST",
        json: buildCreateBody({ name, role, expiresDays, scope }),
      });
      setName("");
      setExpiresDays("");
      await uiModalHTML("Token created — copy it now", tokenCreatedHtml(r.plaintext), "Done");
      load();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function revokeToken(t) {
    if (!(await uiConfirm(revokeConfirmMessage(t.name), "Revoke Token", "Revoke", true)))
      return;
    try {
      await api(`/api/api-tokens/${t.id}`, { method: "DELETE" });
      toast("Token revoked");
      load();
    } catch (e) {
      toast(e.message, true);
    }
  }

  function toggleProject(id, checked) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  }

  const ids = {
    name: `${uid}-name`,
    role: `${uid}-role`,
    expires: `${uid}-expires`,
  };

  return (
    <div className="card">
      <h2>API tokens</h2>
      <div className="sub">
        Service accounts for CI jobs and other machine callers. An API token authenticates with{" "}
        <code>Authorization: Bearer &lt;token&gt;</code>{" "}
        instead of a login — no password, no invite flow.
      </div>
      <div className="flex items-end gap-2.5">
        <div className="flex-[2]">
          <label htmlFor={ids.name}>Name</label>
          <input
            id={ids.name}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. GitHub Actions — coverage check"
          />
        </div>
        <div className="flex-[0_0_140px]">
          <label htmlFor={ids.role}>Role</label>
          <select id={ids.role} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
          </select>
        </div>
        <div className="flex-[0_0_140px]">
          <label htmlFor={ids.expires}>Expires (days)</label>
          <input
            id={ids.expires}
            type="number"
            min="1"
            placeholder="never"
            value={expiresDays}
            onChange={(e) => setExpiresDays(e.target.value)}
          />
        </div>
        <button type="button" className="go m-0 flex-1" onClick={createToken}>
          Create token
        </button>
      </div>
      <div className="mt-3.5" role="group" aria-labelledby={`${uid}-access`}>
        <label id={`${uid}-access`} className="mb-1.5 block">
          Project access
        </label>
        <div className="mb-2 flex gap-[18px]">
          {[
            ["all", "All projects"],
            ["some", "Specific projects"],
          ].map(([value, text]) => (
            <label
              key={value}
              className="inline-flex cursor-pointer items-center gap-1.5 text-[13px] text-text"
            >
              <input
                type="radio"
                name={`${uid}-scope`}
                value={value}
                checked={scopeMode === value}
                onChange={() => setScopeMode(value)}
                className="m-0 w-auto"
              />
              {text}
            </label>
          ))}
        </div>
        {scopeMode === "some" && (
          <div className="flex max-h-[180px] flex-wrap gap-2 overflow-auto rounded-lg border border-solid border-line bg-panel2 p-2.5">
            {projects.length ? (
              projects.map((p) => (
                <label
                  key={p.id}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-solid border-line bg-white/[0.04] px-[9px] py-[5px] text-[12.5px] hover:border-accent2"
                >
                  <input
                    type="checkbox"
                    value={p.id}
                    checked={selected.includes(p.id)}
                    onChange={(e) => toggleProject(p.id, e.target.checked)}
                    className="m-0 w-auto"
                  />{" "}
                  {p.name || p.id}
                </label>
              ))
            ) : (
              <span className="text-[12px] text-muted">{NO_PROJECTS_TEXT}</span>
            )}
          </div>
        )}
      </div>
      <div className="mt-3.5">
        {status === "loading" && <LoadingTable />}
        {status === "error" && <div className="mt-2 text-[12.5px] text-red">{error}</div>}
        {status === "ready" && (
          <TokenTable tokens={tokens} projects={projects} onRevoke={revokeToken} />
        )}
      </div>
    </div>
  );
}
