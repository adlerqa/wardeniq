import { useEffect, useRef, useState } from "react";
import { toastSettings } from "../../../lib/toast.js";

const ICONS = { ok: "✓", err: "!", info: "i", warn: "⚠" };

function Toast({ t, onGone }) {
  const [leaving, setLeaving] = useState(false);
  const timer = useRef(null);
  const el = useRef(null);
  const gone = useRef(false);
  const remove = () => {
    if (gone.current) return;
    gone.current = true;
    setLeaving(true);
    setTimeout(() => onGone(t.id), 220);
  };
  const removeRef = useRef(remove);
  removeRef.current = remove;
  useEffect(() => {
    timer.current = setTimeout(() => removeRef.current(), t.duration);
    // Hovering keeps the toast: stop the timer and freeze the countdown bar.
    const node = el.current;
    const hold = () => {
      clearTimeout(timer.current);
      const bar = node.querySelector(".t-timer");
      if (bar) bar.style.animationPlayState = "paused";
    };
    node.addEventListener("mouseenter", hold);
    return () => {
      clearTimeout(timer.current);
      node.removeEventListener("mouseenter", hold);
    };
  }, [t.duration]);
  return (
    <div ref={el} className={`toastmsg ${t.type}${leaving ? " leaving" : ""}`}>
      <div className="t-ico">{ICONS[t.type]}</div>
      <div className="t-body">
        <div className="t-title">{t.title}</div>
        <div className="t-msg">{t.msg}</div>
      </div>
      <button className="t-close" aria-label="Dismiss" onClick={remove}>
        ×
      </button>
      <div className="t-timer" style={{ animation: `toastTimer ${t.duration}ms linear forwards` }} />
    </div>
  );
}

/**
 * Shared toast stack (was 00-core.js toast). Registers window.toast(message, options):
 * hovering a toast keeps it, × dismisses it.
 */
export default function ToastHost() {
  const [toasts, setToasts] = useState([]);
  const seq = useRef(0);
  useEffect(() => {
    const fn = (msg, opt) => {
      const t = { id: ++seq.current, ...toastSettings(msg, opt) };
      setToasts((list) => [...list, t]);
    };
    window.toast = fn;
    return () => {
      if (window.toast === fn) delete window.toast;
    };
  }, []);
  const gone = (id) => setToasts((list) => list.filter((t) => t.id !== id));
  return (
    <div id="toast" style={{ position: "fixed", bottom: "20px", right: "20px", zIndex: "50", display: "flex", flexDirection: "column", gap: "8px" }}>
      {toasts.map((t) => (
        <Toast key={t.id} t={t} onGone={gone} />
      ))}
    </div>
  );
}
