import { useCallback, useEffect, useRef, useState } from "react";

import { SkeletonRows } from "../../../components/feedback/Skeleton.jsx";
import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  openCaseConfirmation,
  openFeature,
  toast,
} from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";
import {
  libraryChanges,
  libraryGroups,
  libraryKpis,
  priorityTone,
  sortLibrary,
  stepsText,
} from "../lib/imports.js";
import { SheetDetail, SheetKpis, SheetPill } from "./SheetParts.jsx";

const jsonPost = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/**
 * "Reuse imported sheets" dialog (was the library half of 15-imports.js):
 * every imported row of the project, grouped per sheet, with add / remove
 * toggles that are saved together.
 *
 * Opened by the feature workspace through window.openImportLibraryModal(fid)
 * (07-library-and-crud.js) / window.reuseImportsForFeature(fid).
 */
export default function ImportLibraryModal() {
  const [open, setOpen] = useState(false);
  const [fid, setFid] = useState(null);
  // status: loading (skeleton) | ready | error. `count` is the last loaded
  // row count: the old dialog kept showing it while reloading.
  const [lib, setLib] = useState({ status: "loading", items: [], error: "", seq: 0, loaded: false, count: 0 });
  const [desired, setDesired] = useState({});
  const [saving, setSaving] = useState(false);
  const [rescoring, setRescoring] = useState(false);
  const fidRef = useRef(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const f = fidRef.current || currentFeatureId();
    if (!f) return;
    const my = ++seq.current;
    try {
      const r = await api(`/api/features/${f}/imported-sheets`);
      if (my !== seq.current) return;
      const items = sortLibrary((r.data || {}).imported_sheet_tests || []);
      setDesired(Object.fromEntries(items.map((it) => [it.identity_hash, !!it.is_in_feature])));
      setLib({ status: "ready", items, error: "", seq: my, loaded: true, count: items.length });
    } catch (e) {
      if (my === seq.current) setLib((s) => ({ ...s, status: "error", error: e.message }));
    }
  }, []);

  const openFor = useCallback(
    async (featureId) => {
      const f = featureId || currentFeatureId() || null;
      if (!f) {
        toast("Open a feature first", true);
        return;
      }
      fidRef.current = f;
      setFid(f);
      setOpen(true);
      setLib((s) => ({ ...s, status: "loading", items: [], loaded: false }));
      setDesired({});
      await load();
    },
    [load],
  );

  useEffect(() => {
    const hooks = {
      openImportLibraryModal: (f) => openFor(f),
      reuseImportsForFeature: (f) => openFor(f),
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [openFor]);

  const close = () => setOpen(false);
  const items = lib.items;
  const groups = libraryGroups(items);
  const changes = libraryChanges(items, desired);
  const changed = changes.add.length > 0 || changes.remove.length > 0;

  const rescore = async () => {
    const f = fid || currentFeatureId();
    if (!f) {
      toast("No feature in scope", true);
      return;
    }
    setRescoring(true);
    try {
      const r = await api(`/api/features/${f}/imported-sheets/refresh`, { method: "POST" });
      const d = r.data || {};
      toast(`Rescored ${d.rescored || 0} rows · auto-promoted ${d.newly_promoted || 0}`);
      await load();
      if (currentFeatureId() === f) openFeature(f);
    } catch (e) {
      toast(e.message, true);
    } finally {
      setRescoring(false);
    }
  };

  const save = async () => {
    const f = fid || currentFeatureId();
    if (!f || !changed) return;
    setSaving(true);
    try {
      if (changes.add.length)
        await api(`/api/features/${f}/imported-sheets/add`, jsonPost({ identity_hashes: changes.add }));
      if (changes.remove.length)
        await api(`/api/features/${f}/imported-sheets/remove`, jsonPost({ identity_hashes: changes.remove }));
      toast("Imported sheet changes saved");
      await load();
      openFeature(f);
    } catch (e) {
      toast(e.message, true);
    } finally {
      setSaving(false);
    }
  };

  const setRows = (hashes, value) =>
    setDesired((d) => ({ ...d, ...Object.fromEntries(hashes.map((h) => [h, value])) }));

  const deleteSheet = (group) => {
    const f = fid || currentFeatureId();
    if (!f) return;
    const label = `${group.original_filename || "this upload"}${group.sheet ? ` · ${group.sheet}` : ""}`;
    openCaseConfirmation({
      title: "Delete imported sheet",
      copy: `Permanently delete ${label}?`,
      summary: `<div style="color:var(--red);font-weight:600;margin-top:4px">${escapeHtml(
        "This will delete all imported test cases from this sheet across every feature in this project.",
      )}</div>`,
      confirmLabel: "Delete sheet",
      danger: true,
      onConfirm: async () => {
        await api(
          `/api/features/${f}/imported-sheets/remove`,
          jsonPost({
            delete_from_system: true,
            feature_import_id: group.feature_import_id || null,
            original_filename: group.original_filename || null,
            sheet_name: group.sheet || null,
          }),
        );
        toast("Deleted imported sheet permanently");
        await load();
        openFeature(currentFeatureId());
      },
    });
  };

  let body;
  if (lib.status === "loading") body = <SkeletonRows count={4} label="Loading imported sheets" />;
  else if (lib.status === "error") body = <div className="err">{lib.error}</div>;
  else if (!items.length)
    body = (
      <div className="sheet-empty">No imported tests in this project yet. Upload a sheet from Import Sheet first.</div>
    );
  else
    body = groups.map((g, idx) => (
      <LibraryGroup
        key={`${lib.seq}:${g.key}`}
        group={g}
        defaultOpen={idx === 0}
        desired={desired}
        onToggle={(hash, value) => setRows([hash], value)}
        onRemoveAll={() =>
          setRows(
            g.rows.map((it) => it.identity_hash),
            false,
          )
        }
        onDelete={() => deleteSheet(g)}
      />
    ));

  return (
    <div
      className={open ? "modal sheet-modal show" : "modal sheet-modal"}
      id="implib-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="box">
        <div className="editor-head">
          <div className="sheet-head-left">
            <div className="sheet-icon">DOC</div>
            <div className="sheet-title">
              <h2>Reuse imported sheets</h2>
              <div className="muted">
                Expand an imported sheet and add rows into this feature. Existing rows are reused automatically, so
                duplicates stay out of the generated list.
              </div>
            </div>
          </div>
          <button className="ghost sheet-close" id="implib-close" onClick={close}>
            Close
          </button>
        </div>
        <div className="sheet-body">
          <div id="implib-stats">
            {lib.loaded ? <SheetKpis kpis={libraryKpis(items, desired, groups.length)} /> : null}
          </div>
          <div className="sheet-section-head">
            <div>
              <div className="typehdr">Project imported sheets</div>
              <div className="muted">Expand any uploaded sheet and toggle rows. Click Save changes when done.</div>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
                justifyContent: "flex-end",
              }}
            >
              <span className="badge" id="implib-loaded-count">
                {`${lib.count} row${lib.count === 1 ? "" : "s"} loaded`}
              </span>
              <button className="ghost" id="implib-refresh" type="button" disabled={rescoring} onClick={rescore}>
                {rescoring ? "Rescoring…" : "Refresh / rescore"}
              </button>
            </div>
          </div>
          <div id="implib-list" className="sheet-list">
            {body}
          </div>
        </div>
        <div className="sheet-footer">
          <button className="ghost" id="implib-cancel" type="button" onClick={close}>
            Cancel
          </button>
          <button
            className="go sheet-primary"
            id="implib-save"
            type="button"
            disabled={saving || !lib.loaded || !changed}
            onClick={save}
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LibraryGroup({ group: g, defaultOpen, desired, onToggle, onRemoveAll, onDelete }) {
  const included = g.rows.filter((it) => desired[it.identity_hash]).length;
  const total = g.rows.length;
  const act = (fn) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    fn();
  };
  return (
    <details className="sheet-group" open={defaultOpen}>
      <summary>
        <div className="sheet-group-main">
          <div className="sheet-icon">DOC</div>
          <div>
            <div className="sheet-group-title">
              {g.original_filename || "Imported sheet"} {g.sheet ? <SheetPill tone="blue">{g.sheet}</SheetPill> : null}
            </div>
            <div className="sheet-group-sub">
              {`${total} row${total === 1 ? "" : "s"} total · `}
              <span className="ok">{included} included</span>
            </div>
          </div>
        </div>
        <div className="sheet-group-actions">
          <button
            className="sheet-danger-ghost"
            data-implib-action="remove-all"
            data-group={g.key}
            type="button"
            title="Remove every row of this sheet from THIS feature. The rows stay in the project library."
            onClick={act(onRemoveAll)}
          >
            Remove all from feature
          </button>
          <button
            className="sheet-danger-ghost"
            data-implib-action="delete-sheet"
            data-feature-import-id={g.feature_import_id}
            data-filename={g.original_filename}
            data-sheet={g.sheet}
            type="button"
            title="Delete this sheet's rows from the WHOLE project library (all features). Cannot be undone."
            onClick={act(onDelete)}
          >
            Delete sheet from project
          </button>
          <span className="sheet-collapse">^</span>
        </div>
      </summary>
      <div className="sheet-group-body">
        {g.rows.map((it) => (
          <LibraryRow
            key={it.identity_hash}
            item={it}
            desired={!!desired[it.identity_hash]}
            onToggle={act(() => onToggle(it.identity_hash, !desired[it.identity_hash]))}
          />
        ))}
      </div>
    </details>
  );
}

function LibraryRow({ item: it, desired, onToggle }) {
  return (
    <div className={`sheet-test-card ${desired ? "included" : "pending"}`}>
      <div className="sheet-card-top">
        <div>
          <div className="sheet-card-title">{it.title || "(no title)"}</div>
          <div className="muted">Source row {it.source_row_number || ""}</div>
        </div>
        <SheetPill tone={desired ? "green" : ""}>{desired ? "Included" : "Available"}</SheetPill>
      </div>
      <div className="sheet-card-meta">
        {it.category ? <SheetPill tone="blue">{it.category}</SheetPill> : null}
        {it.priority ? <SheetPill tone={priorityTone(it.priority)}>{it.priority}</SheetPill> : null}
        {it.endpoint ? <SheetPill>{`${it.method || ""} ${it.endpoint}`}</SheetPill> : null}
        <SheetPill>Score {(it.score || 0).toFixed(2)}</SheetPill>
      </div>
      <SheetDetail steps={stepsText(it)} expected={it.expected_result} />
      <div className="sheet-action-row">
        <button
          className={desired ? "sheet-danger-ghost" : "sheet-primary"}
          data-implib-action={desired ? "toggle-remove" : "toggle-add"}
          data-hash={it.identity_hash}
          type="button"
          title={
            desired
              ? "Remove this test case from this feature (it stays in the project library)"
              : "Add this row to this feature as a test case"
          }
          onClick={onToggle}
        >
          {desired ? "Remove from feature" : "Add to feature"}
        </button>
      </div>
    </div>
  );
}
