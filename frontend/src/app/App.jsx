import LoginGate from "../features/auth/components/LoginGate.jsx";
import InviteGate from "../features/auth/components/InviteGate.jsx";
import ApplicationFrame from "../layouts/ApplicationFrame.jsx";
import AppOverlays from "../components/overlays/AppOverlays.jsx";
import RuntimeBridge from "../compat/runtime/RuntimeBridge.jsx";
import AppErrorBoundary from "../components/feedback/AppErrorBoundary.jsx";
import SelectDropdownLayer from "../components/forms/SelectDropdownLayer.jsx";

/**
 * Root composition only. Business screens live under features/, permanent
 * chrome under layouts/, overlays under components/, and temporary imperative
 * compatibility code under compat/.
 */
export default function App() {
  return (
    <AppErrorBoundary>
      <LoginGate />
      <InviteGate />
      <ApplicationFrame />
      <AppOverlays />
      <RuntimeBridge />
      <SelectDropdownLayer />
    </AppErrorBoundary>
  );
}
