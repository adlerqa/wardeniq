import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { isSignedIn, loadEffectiveSetup, readRole } from "../appBridge.js";
import {
  getTourState,
  hasSeenTour,
  markTourSeen,
  requestTour,
  subscribeTour,
} from "../tourStore.js";
import WelcomeDialog from "./WelcomeDialog.jsx";

const CHECK_MS = 1000;
const GIVE_UP_MS = 60000; // stop trying if the app never settles

/** An app modal (e.g. the mandatory password change after the first sign-in) is open. */
function appModalOpen() {
  return Boolean(document.querySelector(".modal.show"));
}

/**
 * Shows the welcome prompt once per user, right after they sign in, on
 * whichever screen the app opens (it may restore the last-used screen or, for
 * an admin without a working LLM, Configuration). It waits until the setup
 * flags are known and no app modal is open, so it never covers the mandatory
 * password change. Rendered once from AppOverlays (issue #254).
 */
export default function WelcomeHost() {
  const tour = useSyncExternalStore(subscribeTour, getTourState);
  const [open, setOpen] = useState(false);
  const [setup, setSetup] = useState(null);
  const [role, setRole] = useState("viewer");
  const attempt = useRef({ timer: null, startedAt: 0, done: false });

  const stop = () => {
    clearTimeout(attempt.current.timer);
    attempt.current.timer = null;
  };

  const check = useCallback(async () => {
    const a = attempt.current;
    stop();
    if (a.done || !isSignedIn()) return;
    if (hasSeenTour()) {
      a.done = true;
      return;
    }
    if (Date.now() - a.startedAt > GIVE_UP_MS) return;
    const ready = getTourState().status === "idle" && !appModalOpen();
    const s = ready ? await loadEffectiveSetup() : null;
    if (ready && s && isSignedIn() && !hasSeenTour() && !appModalOpen()) {
      a.done = true;
      setRole(readRole());
      setSetup(s);
      setOpen(true);
      return;
    }
    a.timer = setTimeout(check, CHECK_MS);
  }, []);

  // Start checking on sign-in (#usermenu un-hidden by applyRole()); reset on sign-out.
  useEffect(() => {
    const onChange = () => {
      if (isSignedIn()) {
        if (!attempt.current.timer && !attempt.current.done) {
          attempt.current.startedAt = Date.now();
          check();
        }
      } else {
        stop();
        attempt.current.done = false;
        setOpen(false);
      }
    };
    onChange();
    const menu = document.getElementById("usermenu");
    const observer = new MutationObserver(onChange);
    if (menu) observer.observe(menu, { attributes: true, attributeFilter: ["hidden"] });
    return () => {
      observer.disconnect();
      stop();
    };
  }, [check]);

  // A tour started some other way (checklist, ? button) answers the prompt.
  useEffect(() => {
    if (tour.status !== "idle" && open) setOpen(false);
  }, [tour.status, open]);

  const start = useCallback(() => {
    setOpen(false);
    requestTour(null);
  }, []);
  const dismiss = useCallback(() => {
    setOpen(false);
    markTourSeen();
  }, []);

  if (!open) return null;
  return <WelcomeDialog role={role} setup={setup} onStart={start} onDismiss={dismiss} />;
}
