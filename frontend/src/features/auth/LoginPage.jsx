import { useState } from "react";
import { api } from "../../lib/api";

// Passwordless email-OTP login (idiomatic React + Tailwind). Backend flow:
//   1. POST /api/auth/request-otp { email } → sends 6-digit code
//   2. POST /api/auth/verify-otp  { email, code } → sets signed session cookie
//
// This is the reference implementation showing how *new* views are styled:
// utility-first Tailwind classes with design tokens (bg-panel, text-muted,
// border-line) bridged from the CSS variables in src/styles/global.css. Every
// ported view under src/features/<name>/ should follow the same pattern.
//
// Not currently wired — the LegacyApp vessel handles login today. Swap this in
// from src/App.jsx when you're ready to retire the legacy login markup.
export default function LoginPage({ onAuthenticated }) {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const sendCode = async () => {
    setErr("");
    setMsg("");
    if (!email.trim()) {
      setErr("Email is required.");
      return;
    }
    setBusy(true);
    try {
      const r = await api("/api/auth/request-otp", {
        method: "POST",
        body: { email: email.trim() },
      });
      setMsg(
        r?.dev_code
          ? `Dev mode (no SMTP): your code is ${r.dev_code}`
          : "Code sent. Check your inbox."
      );
      setStep(2);
    } catch (e) {
      setErr(e.message || "Could not send code.");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setErr("");
    setMsg("");
    if (!code.trim()) {
      setErr("Enter the 6-digit code.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/auth/verify-otp", {
        method: "POST",
        body: { email: email.trim(), code: code.trim() },
      });
      onAuthenticated?.();
    } catch (e) {
      setErr(e.message || "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-bg">
      <div className="w-[360px] max-w-[92vw] rounded-2xl border border-line bg-panel p-6 shadow-2xl">
        <div className="mb-3 flex items-center gap-3 text-left">
          <svg
            width="42"
            height="42"
            viewBox="0 0 100 80"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="shrink-0"
          >
            <rect x="22" y="10" width="12" height="60" fill="#1c7ec2" />
            <rect x="44" y="10" width="12" height="60" fill="#1c7ec2" />
            <rect x="66" y="10" width="12" height="60" fill="#1c7ec2" />
            <path
              d="M 5,38 C 15,38 15,48 25,48 H 36 C 44,48 44,40 50,40 C 56,40 56,48 64,48 H 75 C 85,48 85,62 95,62"
              stroke="#1ce5b2"
              strokeWidth="5"
              fill="none"
              strokeLinecap="round"
            />
            <circle cx="5" cy="38" r="5" fill="#1ce5b2" />
            <circle cx="5" cy="38" r="2.2" fill="#141a24" />
            <circle cx="95" cy="62" r="5" fill="#1ce5b2" />
            <circle cx="95" cy="62" r="2.2" fill="#141a24" />
            <circle cx="50" cy="40" r="10" fill="#141a24" stroke="#1ce5b2" strokeWidth="5" />
          </svg>
          <div className="flex flex-col leading-tight">
            <span className="text-[26px] font-extrabold tracking-tight text-[#1c7ec2]">
              Warden<span className="text-[#1c7ec2]">IQ</span>
            </span>
            <span className="mt-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-[#1ce5b2]">
              Engineering Intelligence
            </span>
          </div>
        </div>
        <p className="mb-4 text-[12.5px] text-muted">
          Sign in with a one-time code sent to your email.
        </p>

        {step === 1 && (
          <div>
            <label className="mb-1 block text-xs text-muted">Email</label>
            <input
              type="email"
              placeholder="you@company.com"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendCode()}
              className="w-full rounded-md border border-line bg-panel2 px-3 py-2.5 text-sm text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            />
            <button
              onClick={sendCode}
              disabled={busy}
              className="mt-3 w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-[#1a1205] transition hover:brightness-110 disabled:opacity-50"
            >
              {busy ? "Sending…" : "Send code"}
            </button>
          </div>
        )}

        {step === 2 && (
          <div>
            <label className="mb-1 block text-xs text-muted">
              6-digit code sent to <b className="text-text">{email}</b>
            </label>
            <input
              inputMode="numeric"
              maxLength={6}
              placeholder="000000"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && verify()}
              className="w-full rounded-md border border-line bg-panel2 px-3 py-2.5 text-center text-lg tracking-[0.5em] text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            />
            <button
              onClick={verify}
              disabled={busy}
              className="mt-3 w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-[#1a1205] transition hover:brightness-110 disabled:opacity-50"
            >
              {busy ? "Verifying…" : "Verify & sign in"}
            </button>
            <button
              onClick={() => {
                setStep(1);
                setCode("");
                setErr("");
                setMsg("");
              }}
              className="mt-2 w-full border-none bg-transparent px-0 py-2 text-left text-xs text-accent2 hover:underline"
            >
              ← use a different email
            </button>
          </div>
        )}

        {msg && <div className="mt-2.5 text-xs text-green">{msg}</div>}
        {err && <div className="mt-2 min-h-[16px] text-xs text-red">{err}</div>}
      </div>
    </div>
  );
}
