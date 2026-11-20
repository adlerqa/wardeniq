import TestPlanHeader from "../components/TestPlanHeader.jsx";
import TestPlanEmptyState from "../components/TestPlanEmptyState.jsx";
import TestPlanWorkspace from "../components/TestPlanWorkspace.jsx";
import useTestPlan from "../hooks/useTestPlan.js";

export default function TestPlanPage() {
  const { state, generate } = useTestPlan();
  return (
    <section id="view-testplan" className="view" hidden>
      <TestPlanHeader />
      {!state.hasFeature && <TestPlanEmptyState />}
      <TestPlanWorkspace state={state} onGenerate={generate} />
    </section>
  );
}
