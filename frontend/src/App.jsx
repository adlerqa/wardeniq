import LegacyApp from "./legacy/LegacyApp.jsx";
import { ToastProvider } from "./lib/toast.jsx";
import { ModalProvider } from "./lib/modal.jsx";

// App root.
//
// Migration status:
//   ✅ Vite + React scaffold, HMR, /api proxy to FastAPI :8000
//   ✅ Global CSS extracted to src/styles/global.css
//   ✅ Idiomatic React shell components implemented and ready to swap in:
//        - src/features/auth/LoginPage.jsx
//        - src/features/auth/InviteGate.jsx
//        - src/layout/AppShell.jsx, Sidebar.jsx, Header.jsx
//        - src/hooks/useSession.js
//        - src/lib/api.js  (fetch wrapper matching the legacy `api()` helper)
//        - src/lib/toast.jsx, src/lib/modal.jsx
//   🚧 Per-view rewrites (dashboard, projects, cases, cycles, mindmap, steps,
//      usage, config, users, validator, testplan, gap) — placeholder folders
//      exist under src/features/, ready to be filled in.
//
// The <LegacyApp/> vessel below hosts the untouched legacy DOM + JS so the
// app runs at feature parity today. Once a view is rewritten in React, delete
// its markup from src/legacy/legacyShellHtml.js and its init logic from
// src/legacy/legacyApp.js, then wire the new component into a router here.
export default function App() {
  return (
    <ToastProvider>
      <ModalProvider>
        <LegacyApp />
      </ModalProvider>
    </ToastProvider>
  );
}
