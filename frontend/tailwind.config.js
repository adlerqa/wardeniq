/** @type {import('tailwindcss').Config} */
export default {
  // Scan every React source file for Tailwind class usage. The legacy vessel
  // (src/legacy/*.js) is deliberately EXCLUDED — it uses hand-written classes
  // from src/styles/global.css and will be deleted view-by-view during the
  // React refactor. Tailwind should only compile utilities that new
  // idiomatic-React components use.
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
    "!./src/legacy/**",
  ],
  // corePlugins.preflight = false — Tailwind's opinionated CSS reset resets
  // margins, list styles, form controls, headings, and more. The legacy stylesheet
  // in src/styles/global.css already establishes the app's visual baseline; if we
  // let Tailwind reset the world on top of it, the legacy vessel breaks (cards
  // lose padding, sidebar buttons lose alignment, etc.). Disabling preflight
  // means Tailwind only adds utility classes when we use them — no globals.
  //
  // When the legacy vessel is fully retired and every view is idiomatic React,
  // you can re-enable preflight and drop the ported bits of global.css.
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      // Bridge the CSS variables from src/styles/global.css so Tailwind
      // utilities can reference the same design tokens the legacy code uses
      // (bg-panel, text-muted, border-line, etc.). This is the migration path:
      // rewrite each view with these utilities, then drop the legacy classes.
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        panel2: "var(--panel2)",
        line: "var(--line)",
        text: "var(--text)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        accent2: "var(--accent2)",
        green: "var(--green)",
        blue: "var(--blue)",
        purple: "var(--purple)",
        red: "var(--red)",
        amber: "var(--amber)",
      },
      fontFamily: {
        sans: [
          "SF Pro Display",
          "SF Pro Text",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      // Keyframes/animations for the idiomatic-React feedback components
      // (Spinner, Skeleton, view transitions). Custom multi-step keyframes must
      // live in the Tailwind config — this is the idiomatic way to keep markup
      // class-driven (animate-shimmer, animate-view-in) instead of hand-written
      // CSS. The elaborate branded loaders (wql-*/aql-*) keep their keyframes in
      // global.css because they use ~30 staggered per-element animations that
      // don't map cleanly to utility classes.
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-320px 0" },
          "100%": { backgroundPosition: "320px 0" },
        },
        "view-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" },
        },
        "toast-in": {
          from: { opacity: "0", transform: "translateX(24px) scale(.98)" },
          to: { opacity: "1", transform: "none" },
        },
      },
      animation: {
        shimmer: "shimmer 1.25s ease-in-out infinite",
        "view-in": "view-in .26s ease both",
        "toast-in": "toast-in .28s cubic-bezier(.2,.8,.25,1)",
        // Built-in `animate-spin` covers the button/inline spinners.
      },
    },
  },
  plugins: [],
};
