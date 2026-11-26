/** Green / red service dot. */
const Dot = ({ ok }) => <span className={`dot ${ok ? "ok" : "bad"}`} />;

/**
 * Header status content (was 00-core.js refreshStatus): "Checking services…"
 * until the first load, then the Mongo / embeddings / LLM chips and the
 * feature and case counts; "Status unavailable" if the first load fails.
 */
export default function ServiceChips({ status }) {
  if (status.phase === "loading")
    return (
      <span className="stat">
        <span className="spin-inline" />
        Checking services…
      </span>
    );
  if (status.phase === "unavailable")
    return (
      <span className="stat">
        <Dot ok={false} />
        Status unavailable
      </span>
    );
  const s = status.data;
  const c = s.counts || {};
  const emb = s.embedding;
  const llm = s.llm;
  return (
    <>
      <span className="status-group">
        <span className="stat" title="MongoDB connection">
          <Dot ok={s.mongo_connected} />
          Mongo
        </span>
        <span
          className="stat"
          title={`Embeddings: ${emb?.provider || ""}${emb?.dims ? " · " + emb.dims + "-d" : ""}${emb?.health?.error ? " · " + emb.health.error : ""}`}
        >
          <Dot ok={emb?.health?.ok} />
          {emb?.model}
        </span>
        <span className="stat" title={`LLM: ${llm?.health?.error || llm?.provider || ""}`}>
          <Dot ok={llm?.health?.ok} />
          {llm?.model}
        </span>
      </span>
      <span className="stat-metric" title="Features and test cases in scope">
        <span>
          <b>{c.features || 0}</b> features
        </span>
        <span className="sep" />
        <span>
          <b>{c.test_cases || 0}</b> cases
        </span>
      </span>
    </>
  );
}
