import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
// Order matters: Tailwind base first (though preflight is disabled so this is
// mostly a no-op), then the legacy stylesheet establishes the visual baseline,
// then any additional resets we layer on top.
import "./styles/tailwind.css";
import "./styles/global.css";
import "./styles/reset.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
