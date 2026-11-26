import FeatureCreatePanel from "../components/FeatureCreatePanel.jsx";
import FeatureListPanel from "../components/FeatureListPanel.jsx";
import FeatureWorkspacePanel from "../components/FeatureWorkspacePanel.jsx";
import useFeatureCreate from "../hooks/useFeatureCreate.js";
import useFeatures from "../hooks/useFeatures.js";
import useWorkspace from "../hooks/useWorkspace.js";

/** Features: the feature cards, the "New feature" page and the feature workspace. */
export default function FeaturesPage() {
  const fs = useFeatures();
  const cf = useFeatureCreate(fs);
  const ws = useWorkspace(fs);
  return (
    <section id="view-features" className="view" hidden>
      <FeatureListPanel fs={fs} cf={cf} />
      <FeatureCreatePanel fs={fs} cf={cf} />
      <FeatureWorkspacePanel fs={fs} ws={ws} />
    </section>
  );
}
