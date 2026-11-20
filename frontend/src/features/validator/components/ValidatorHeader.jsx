/**
 * Back-links to the feature workspace and its test cases. The buttons are wired
 * by class in 03-features-and-usage.js when the compat runtime starts, so they
 * must stay mounted and keep these class names.
 */
export default function ValidatorHeader() {
  return (
    <div className="mb-3 flex gap-2">
      <button className="ghost feature-workspace-back">Feature workspace</button>
      <button className="ghost feature-workspace-cases">Test Cases</button>
    </div>
  );
}
