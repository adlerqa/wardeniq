import { navigateTo, openFeatureTestCases } from "../../../lib/compatBridge.js";

/**
 * Back-links to the feature workspace and its test cases (was wired by class
 * in 03-features-and-usage.js).
 */
export default function ValidatorHeader() {
  return (
    <div className="mb-3 flex gap-2">
      <button className="ghost feature-workspace-back" onClick={() => navigateTo("features")}>
        Feature workspace
      </button>
      <button className="ghost feature-workspace-cases" onClick={() => openFeatureTestCases()}>
        Test Cases
      </button>
    </div>
  );
}
