/*
 * Status line under a settings card (`.cfg-status`). A message set by an
 * action belongs to the settings version it was set for; once the settings
 * reload, the card shows its settings-derived status again (as loadConfig
 * rewrote it).
 */

/** { tone: "ok" | "warn" | "err" | "muted" | "", text | node, saving } */
export function CardStatus({ id, status }) {
  const saving = status && status.saving;
  let content = null;
  if (status) {
    const body = status.node ?? status.text;
    content = status.tone ? <span className={status.tone}>{body}</span> : body;
  }
  return (
    <div className={saving ? "cfg-status muted is-saving" : "cfg-status muted"} id={id}>
      {content}
    </div>
  );
}
