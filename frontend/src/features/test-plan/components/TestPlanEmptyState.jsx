/** Shown on the Test Plan screen when no feature is open. */
export default function TestPlanEmptyState() {
  return (
    <div className="card">
      <h2>Test Plan</h2>
      <div className="text-[12px] text-muted">
        Please select a feature first to generate a test plan.
      </div>
    </div>
  );
}
