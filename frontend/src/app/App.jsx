import LoginGate from "../features/auth/components/LoginGate.jsx";
import InviteGate from "../features/auth/components/InviteGate.jsx";
import ApplicationFrame from "../layouts/ApplicationFrame.jsx";
import AppOverlays from "../components/overlays/AppOverlays.jsx";
import RuntimeBridge from "../compat/runtime/RuntimeBridge.jsx";
import AppErrorBoundary from "../components/feedback/AppErrorBoundary.jsx";
import { useJobGlobals } from "../lib/useJobGlobals.js";
import { useBoot } from "./useBoot.js";

/**
 * Root composition only. Business screens live under features/, permanent
 * chrome under layouts/, overlays under components/, and temporary imperative
 * compatibility code under compat/.
 */
export default function App() {
  useJobGlobals();
  const boot = useBoot();
  return (
    <AppErrorBoundary>
      <LoginGate />
      <InviteGate />
      <ApplicationFrame />
      <AppOverlays />
      <RuntimeBridge onReady={boot} />
    </AppErrorBoundary>
  );
}
