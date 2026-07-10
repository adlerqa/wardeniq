/* eslint-disable react-refresh/only-export-components --
   Provider module: intentionally co-locates the <ToastProvider> component with
   the `toast()` helper and `useToast()` hook (they share module-level state and
   the same React context). Splitting them would break the global-callable
   `toast()` fast-path, so Fast Refresh's component-only export rule is waived
   for this file. */
import { createContext, useCallback, useContext, useEffect, useState } from "react";

// Global toast queue implemented as a lightweight React context. Mirrors the
// legacy `toast(msg, isErr)` helper (see app/static/index.html) so ported code
// can call `toast("message")` without worrying about a provider ref.
//
// Usage:
//   import { toast, ToastProvider } from "./lib/toast";
//   toast("Saved!");             // success
//   toast("Failed", true);       // error
//   <ToastProvider>{app}</ToastProvider>

const TOAST_TTL_MS = 3800;

const ToastContext = createContext(null);

let externalPush = null;

/** Global-callable toast — safe to invoke before/without a React tree. */
export function toast(msg, isErr = false) {
  if (typeof externalPush === "function") {
    externalPush(msg, isErr);
  } else if (typeof window !== "undefined") {
    // Fallback for very early boot before the provider mounts.
     
    (isErr ? console.error : console.log)(`[toast] ${msg}`);
  }
}

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);

  const push = useCallback((msg, isErr) => {
    const id = Math.random().toString(36).slice(2);
    setItems((prev) => [...prev, { id, msg, isErr: !!isErr }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, TOAST_TTL_MS);
  }, []);

  useEffect(() => {
    externalPush = push;
    return () => {
      if (externalPush === push) externalPush = null;
    };
  }, [push]);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div id="toast" className="toast-host" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={"toastmsg" + (t.isErr ? " err" : "")}>
            {t.msg}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Hook variant, for components that prefer explicit access. */
export function useToast() {
  const ctx = useContext(ToastContext);
  return ctx || toast;
}
