/** Shown on the MCQ Validator screen when no feature is open. */
export default function ValidatorEmptyState() {
  return (
    <div className="card">
      <h2>MCQ Validator</h2>
      <div className="text-[12px] text-muted">
        Please select a feature first to run the requirements validator.
      </div>
    </div>
  );
}
