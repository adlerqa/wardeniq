import LoginGate from "../features/auth/components/LoginGate.jsx";
import InviteGate from "../features/auth/components/InviteGate.jsx";
import ApplicationFrame from "../layouts/ApplicationFrame.jsx";
import AppOverlays from "../components/overlays/AppOverlays.jsx";
import AppErrorBoundary from "../components/feedback/AppErrorBoundary.jsx";
import { useSharedGlobals } from "../lib/useSharedGlobals.js";
import { useBoot } from "./useBoot.js";

/**
 * Root composition only. Business screens live under features/, permanent
 * chrome under layouts/, overlays under components/, start-up and navigation
 * under app/.
 */
export default function App() {
  useSharedGlobals();
  useBoot();
  return (
    <AppErrorBoundary>
      <LoginGate />
      <InviteGate />
      <ApplicationFrame />
      <AppOverlays />
    </AppErrorBoundary>
  );
}
