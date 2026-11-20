import ValidatorHeader from "../components/ValidatorHeader.jsx";
import ValidatorEmptyState from "../components/ValidatorEmptyState.jsx";
import ValidatorWorkspace from "../components/ValidatorWorkspace.jsx";
import useValidator from "../hooks/useValidator.js";

export default function ValidatorPage() {
  const validator = useValidator();
  return (
    <section id="view-validator" className="view" hidden>
      <ValidatorHeader />
      {!validator.state.hasFeature && <ValidatorEmptyState />}
      <ValidatorWorkspace {...validator} />
    </section>
  );
}
