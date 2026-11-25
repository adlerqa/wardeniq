import FeatureCreatePanel from "../components/FeatureCreatePanel.jsx";
import FeatureListPanel from "../components/FeatureListPanel.jsx";
import FeatureWorkspacePanel from "../components/FeatureWorkspacePanel.jsx";
import useFeatureCreate from "../hooks/useFeatureCreate.js";
import useFeatures from "../hooks/useFeatures.js";

/**
 * Features: the feature cards and the "New feature" page are React
 * (useFeatures / useFeatureCreate); the workspace is still drawn by
 * 03-features-and-usage.js openFeature (#257).
 */
export default function FeaturesPage() {
  const fs = useFeatures();
  const cf = useFeatureCreate(fs);
  return (
    <section id="view-features" className="view" hidden>
      <FeatureListPanel fs={fs} cf={cf} />
      <FeatureCreatePanel fs={fs} cf={cf} />
      <FeatureWorkspacePanel />
    </section>
  );
}
