import { navigateTo, openFeatureTestCases } from "../../../lib/compatBridge.js";

/** GapHeader for gap-analysis. */
export default function GapHeader() {
  return (
    <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
      <button className="ghost feature-workspace-back" onClick={() => navigateTo("features")}>
        Feature workspace
      </button>
      <button className="ghost feature-workspace-cases" onClick={() => openFeatureTestCases()}>
        Test Cases
      </button>
    </div>
  );
}
