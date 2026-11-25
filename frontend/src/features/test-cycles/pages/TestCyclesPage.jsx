import AddCaseOverlays from "../components/AddCaseOverlays.jsx";
import CreateTestCyclePanel from "../components/CreateTestCyclePanel.jsx";
import CycleTemplatesPanel from "../components/CycleTemplatesPanel.jsx";
import TestCyclesListPanel from "../components/TestCyclesListPanel.jsx";
import TestCycleDetailPanel from "../components/TestCycleDetailPanel.jsx";
import useTestCycles from "../hooks/useTestCycles.js";

/** Test Cycles: create, templates, saved cycles and the open cycle (useTestCycles). */
export default function TestCyclesPage() {
  const tc = useTestCycles();
  return (
    <section id="view-testcycles" className="view" hidden>
      <CreateTestCyclePanel tc={tc} />
      <CycleTemplatesPanel tc={tc} />
      <TestCyclesListPanel tc={tc} />
      <TestCycleDetailPanel tc={tc} />
      <AddCaseOverlays tc={tc} />
    </section>
  );
}
