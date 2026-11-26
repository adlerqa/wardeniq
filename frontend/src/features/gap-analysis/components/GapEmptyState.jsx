/** Shown until a feature is open (display set once initGap has run). */
export default function GapEmptyState({ hasFeature }) {
  return (
    <div className="card" id="gap-no-feature" style={hasFeature == null ? undefined : { display: hasFeature ? "none" : "block" }}>
      <h2>Gap Analysis</h2>
      <div className="muted">Please select a feature first to view gap analysis.</div>
    </div>
  );
}
