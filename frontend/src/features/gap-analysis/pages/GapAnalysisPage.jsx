import GapHeader from "../components/GapHeader.jsx";
import GapEmptyState from "../components/GapEmptyState.jsx";
import GapWorkspace from "../components/GapWorkspace.jsx";
import { useGap } from "../hooks/useGap.js";

export default function GapAnalysisPage() {
  const g = useGap();
  return (
    <section id="view-gap" className="view" hidden>
      <GapHeader />
      <GapEmptyState hasFeature={g.view.hasFeature} />
      <GapWorkspace g={g} />
    </section>
  );
}
