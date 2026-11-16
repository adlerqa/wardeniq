import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/**
 * One-time welcome prompt on the Dashboard while setup is incomplete
 * (issue #254). Modal: focus is kept inside and returned afterwards.
 */
export default function WelcomeDialog({ role, setup, onStart, onDismiss }) {
  const dialogRef = useRef(null);
  const startRef = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    startRef.current && startRef.current.focus();
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onDismiss();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const items = dialogRef.current.querySelectorAll("button");
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous && previous.isConnected && typeof previous.focus === "function") previous.focus();
    };
  }, [onDismiss]);

  const readOnly = role === "viewer";
  const todo = [];
  if (role === "admin" && !(setup && setup.llm_configured)) todo.push("set up the AI model");
  if (!(setup && setup.has_project)) todo.push("create a project");
  if (!(setup && setup.has_test_cases)) todo.push("generate your first test cases");
  const list =
    todo.length > 1 ? `${todo.slice(0, -1).join(", ")} and ${todo[todo.length - 1]}` : todo[0];

  return createPortal(
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
      <div aria-hidden="true" className="absolute inset-0 bg-bg opacity-70" onClick={onDismiss} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="wq-welcome-title"
        aria-describedby="wq-welcome-body"
        className="relative w-[440px] max-w-full rounded-xl border border-solid border-line bg-panel p-6 text-text shadow-2xl"
      >
        <h2 id="wq-welcome-title" className="m-0 text-lg font-semibold text-text">
          Welcome to wardenIQ
        </h2>
        <p id="wq-welcome-body" className="m-0 mt-2 text-sm leading-relaxed text-muted">
          {readOnly
            ? "Take a one-minute tour of where projects, test cases and coverage live. You have read-only access, so an admin or editor handles setup."
            : list
              ? `Take a short guided tour: it shows you how to ${list}, on the real screens. It takes a few minutes, and you can leave at any time.`
              : "Take a short guided tour of where projects, test cases and coverage live. You can leave at any time."}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button type="button" className="ghost" onClick={onDismiss}>
            I&apos;ll explore myself
          </button>
          <button type="button" className="go" ref={startRef} onClick={onStart}>
            Start the tour
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
