import { useState } from "react";
import BrandMark from "../../../components/brand/BrandMark.jsx";

const inputClass = `
  mt-2 h-11 w-full rounded-lg
  border border-slate-700/80
  bg-[#0B121C]
  px-3.5
  text-[14px] text-slate-100
  outline-none
  transition-all duration-200
  placeholder:text-slate-600
  hover:border-slate-600
  focus:border-cyan-500/70
  focus:ring-2
  focus:ring-cyan-500/10
`;

const labelClass = "block text-[12.5px] font-medium leading-5 text-slate-300";

const primaryButtonClass = `
  go
  mt-5
  flex h-11 w-full
  items-center justify-center
  rounded-lg
  !border-0
  !bg-cyan-500
  px-4
  text-[13px] font-semibold
  text-white
  transition-all duration-200
  hover:!bg-cyan-400
  focus:outline-none
  focus:ring-2
  focus:ring-cyan-400/25
  disabled:cursor-not-allowed
  disabled:opacity-50
`;

const linkClass = `
  link
  !border-0
  !bg-transparent
  !p-0
  text-[12px]
  font-medium
  !text-slate-500
  transition-colors
  hover:!text-cyan-400
`;

function BackIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function AuthHeading({ title, description }) {
  return (
    <div className="mb-6">
      <h2 className="m-0 text-[20px] font-semibold tracking-[-0.02em] text-slate-100">
        {title}
      </h2>

      <p className="mt-2 text-[12.5px] leading-5 text-slate-500">
        {description}
      </p>
    </div>
  );
}

function PasswordInput({
  id,
  placeholder = "••••••••",
  autoComplete = "off",
  className,
}) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="relative mt-2">
      <input
        id={id}
        type={showPassword ? "text" : "password"}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className={`${className} !mt-0 !pr-11`}
      />

      <button
        type="button"
        onClick={() => setShowPassword((prev) => !prev)}
        className="
          absolute right-3 top-1/2
          flex -translate-y-1/2
          items-center justify-center
          border-0 bg-transparent p-1
          text-slate-500
          transition-colors
          hover:text-slate-200
          focus:outline-none
        "
        title={showPassword ? "Hide password" : "Show password"}
        aria-label={showPassword ? "Hide password" : "Show password"}
      >
        {showPassword ? (
          /* Eye off */
          <svg
            viewBox="0 0 24 24"
            width="17"
            height="17"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3l18 18" />
            <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
            <path d="M9.9 4.2A10.7 10.7 0 0 1 12 4c6.5 0 10 8 10 8a16.8 16.8 0 0 1-2.1 3.1" />
            <path d="M6.6 6.6C3.7 8.4 2 12 2 12s3.5 8 10 8a10.1 10.1 0 0 0 4.1-.9" />
          </svg>
        ) : (
          /* Eye */
          <svg
            viewBox="0 0 24 24"
            width="17"
            height="17"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  );
}

export default function LoginGate() {
  return (
    <div
      id="login"
      hidden
      className="
        fixed inset-0 z-[200]
        flex min-h-screen
        items-center justify-center
        overflow-y-auto
        bg-[#080D14]
        px-5 py-10
      "
    >
      {/* SINGLE LOGIN CARD */}
      <div
        className="
          box
          !m-0
          !w-full
          !max-w-[440px]
          !rounded-2xl
          !border
          !border-slate-800
          !bg-[#101720]
          !p-0
          shadow-[0_24px_70px_rgba(0,0,0,0.35)]
        "
      >
        <div className="px-7 pb-7 pt-8 sm:px-8">
          {/* Brand */}
          <div className="login-logo !mb-8 !flex !items-center !justify-center !gap-3">
            <BrandMark size={40} centerFill="#101720" />

            <div className="logo-text !flex !flex-col">
              <span className="logo-title !text-[21px] !font-bold !tracking-[-0.035em] !text-slate-100">
                Warden
                <span className="!text-cyan-400">IQ</span>
              </span>

              <span className="logo-subtitle !mt-0.5 !text-[8px] !font-semibold !uppercase !tracking-[0.16em] !text-cyan-500/70">
                Engineering Intelligence
              </span>
            </div>
          </div>

          <div
            id="login-boot-status"
            hidden
            role="status"
            aria-live="polite"
            className="mb-6 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-[12.5px] leading-5 text-amber-200 break-words"
          />

          {/* Main title */}
          <div className="mb-7 text-center">
            <h1 className="m-0 text-[22px] font-semibold tracking-[-0.025em] text-slate-100">
              Welcome back
            </h1>

            <p
              id="login-intro"
              className="mx-auto mt-2 max-w-[330px] text-[12.5px] leading-5 text-slate-500"
            >
              Sign in to continue to your WardenIQ workspace.
            </p>
          </div>

          {/* =========================
              EMAIL OTP - STEP 1
          ========================== */}
          <div id="login-step1">
            <label htmlFor="login-email" className={labelClass}>
              Work email
            </label>

            <input
              id="login-email"
              type="email"
              placeholder="you@company.com"
              autoComplete="off"
              className={inputClass}
            />

            <button
              type="button"
              className={primaryButtonClass}
              id="login-send"
            >
              Send verification code
            </button>

            <p className="mt-4 text-center text-[11px] leading-4 text-slate-600">
              A 6-digit verification code will be sent to your email.
            </p>
          </div>

          {/* =========================
              EMAIL OTP - STEP 2
          ========================== */}
          <div id="login-step2" hidden>
            <div
              id="login-sent-badge"
              className="
                login-sent-badge
                !mb-6
                !rounded-lg
                !border
                !border-slate-800
                !bg-[#0B121C]
                !px-4
                !py-3
                !text-center
              "
            >
              <span
                id="login-sent-text"
                className="block text-[11px] text-slate-500"
              >
                Verification code sent to
              </span>

              <b
                id="login-to"
                className="mt-1 block truncate text-[12.5px] font-medium text-slate-200"
              />
            </div>

            <label className={labelClass}>Enter verification code</label>

            <div
              id="login-code"
              className="otp-boxes !mt-2.5 !grid !grid-cols-6 !gap-2"
            >
              {[1, 2, 3, 4, 5, 6].map((digit) => (
                <input
                  key={digit}
                  className="
                    otp-box
                    !h-12
                    !min-w-0
                    !w-full
                    !rounded-lg
                    !border
                    !border-slate-700
                    !bg-[#0B121C]
                    !p-0
                    !text-center
                    !text-[17px]
                    !font-semibold
                    !text-slate-100
                    !outline-none
                    transition-all
                    focus:!border-cyan-500
                    focus:!ring-2
                    focus:!ring-cyan-500/10
                  "
                  type="text"
                  inputMode="numeric"
                  maxLength="1"
                  aria-label={`Digit ${digit}`}
                />
              ))}
            </div>

            <button
              type="button"
              className={primaryButtonClass}
              id="login-verify"
            >
              Verify &amp; sign in
            </button>

            <button
              type="button"
              className={`${linkClass} !mt-5 !flex !w-full !items-center !justify-center !gap-1.5`}
              id="login-back"
            >
              <BackIcon />
              Use a different email
            </button>
          </div>

          {/* =========================
              PASSWORD LOGIN
          ========================== */}
          <div id="login-password" hidden>
            <div>
              <label htmlFor="login-username" className={labelClass}>
                Username or email
              </label>

              <input
                id="login-username"
                type="text"
                placeholder="admin"
                autoComplete="off"
                className={inputClass}
              />
            </div>

            <div className="mt-5">
              <div className="flex items-center justify-between">
                <label htmlFor="login-pw" className={labelClass}>
                  Password
                </label>

                <button
                  className={linkClass}
                  id="login-forgot-btn"
                  type="button"
                >
                  Forgot password?
                </button>
              </div>

              <PasswordInput
                id="login-pw"
                placeholder="••••••••"
                autoComplete="off"
                className={inputClass}
              />
            </div>

            <button
              type="button"
              className={primaryButtonClass}
              id="login-signin"
            >
              Sign in
            </button>
          </div>

          {/* =========================
              RESET WITHOUT SMTP
          ========================== */}
          <div id="login-forgot-nosmtp" hidden>
            <AuthHeading
              title="Reset password"
              description="SMTP is not configured. Use your deployment APP_SECRET to reset the administrator password."
            />

            <div>
              <label htmlFor="reset-master-username" className={labelClass}>
                Username
              </label>

              <input
                id="reset-master-username"
                type="text"
                placeholder="admin"
                className={inputClass}
              />
            </div>

            <div className="mt-5">
              <label htmlFor="reset-master-secret" className={labelClass}>
                App Master Secret
              </label>

              <PasswordInput
                id="reset-master-secret"
                placeholder="APP_SECRET"
                className={inputClass}
              />
            </div>

            <div className="mt-5">
              <label htmlFor="reset-master-new-pw" className={labelClass}>
                New password
              </label>

              <PasswordInput
                id="reset-master-new-pw"
                placeholder="••••••••"
                autoComplete="off"
                className={inputClass}
              />
            </div>

            <button
              type="button"
              className={primaryButtonClass}
              id="reset-master-submit-btn"
            >
              Reset password
            </button>

            <button
              className={`${linkClass} !mt-5 !flex !w-full !items-center !justify-center !gap-1.5`}
              id="reset-nosmtp-back-btn"
              type="button"
            >
              <BackIcon />
              Back to sign in
            </button>
          </div>

          {/* =========================
              REQUEST RESET CODE
          ========================== */}
          <div id="login-forgot-step1" hidden>
            <AuthHeading
              title="Forgot password?"
              description="Enter your username or email and we'll send you a reset code."
            />

            <label htmlFor="reset-target" className={labelClass}>
              Username or email
            </label>

            <input
              id="reset-target"
              type="text"
              placeholder="you@company.com"
              className={inputClass}
            />

            <button
              type="button"
              className={primaryButtonClass}
              id="reset-request-btn"
            >
              Send reset code
            </button>

            <button
              className={`${linkClass} !mt-5 !flex !w-full !items-center !justify-center !gap-1.5`}
              id="reset-back-btn"
              type="button"
            >
              <BackIcon />
              Back to sign in
            </button>
          </div>

          {/* =========================
              SET NEW PASSWORD
          ========================== */}
          <div id="login-forgot-step2" hidden>
            <AuthHeading
              title="Create new password"
              description="Enter the reset code and choose a new password."
            />

            <div>
              <label htmlFor="reset-code" className={labelClass}>
                Reset code
              </label>

              <input
                id="reset-code"
                type="text"
                inputMode="numeric"
                maxLength="6"
                placeholder="000000"
                className={`
                  ${inputClass}
                  text-center
                  !text-[17px]
                  font-semibold
                  tracking-[0.3em]
                `}
              />
            </div>

            <div className="mt-5">
              <label htmlFor="reset-new-pw" className={labelClass}>
                New password
              </label>

              <PasswordInput
                id="reset-new-pw"
                placeholder="••••••••"
                autoComplete="off"
                className={inputClass}
              />
            </div>

            <button
              type="button"
              className={primaryButtonClass}
              id="reset-submit-btn"
            >
              Set new password
            </button>

            <button
              className={`${linkClass} !mt-5 !flex !w-full !items-center !justify-center !gap-1.5`}
              id="reset-cancel-btn"
              type="button"
            >
              <BackIcon />
              Cancel &amp; sign in
            </button>
          </div>

          {/* =========================
              STATUS / ERROR
          ========================== */}
          <div
            className="
              muted ok
              !mt-4
              !text-center
              !text-[12px]
              !leading-5
              !text-emerald-400
              empty:!hidden
            "
            id="login-msg"
            role="status"
          />

          <div
            className="
              err
              !mt-4
              !text-center
              !text-[12px]
              !font-medium
              !leading-5
              !text-red-400
              empty:!hidden
            "
            id="login-err"
            role="alert"
          />
        </div>

        {/* Footer inside the same card */}
        <div
          className="
            border-t border-slate-800/80
            px-7 py-4
            text-center
            text-[10.5px]
            text-slate-600
            sm:px-8
          "
        >
          Secure access to WardenIQ
        </div>
      </div>
    </div>
  );
}
