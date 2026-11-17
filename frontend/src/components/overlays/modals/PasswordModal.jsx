import { useState } from "react";

function EyeIcon({ visible }) {
  return visible ? (
    // Eye-off: password is currently visible, click to hide
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m3 3 18 18" />
      <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
      <path d="M9.9 4.2A10.7 10.7 0 0 1 12 4c6.5 0 10 8 10 8a16.8 16.8 0 0 1-2.1 3.1" />
      <path d="M6.6 6.6C3.7 8.4 2 12 2 12s3.5 8 10 8a10.1 10.1 0 0 0 4.1-.9" />
    </svg>
  ) : (
    // Eye: password is hidden, click to show
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function PasswordField({ id, label, autoComplete = "off", placeholder = "••••••••" }) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div>
      <label
        htmlFor={id}
        className="block text-[12.5px] font-medium leading-5 text-slate-300"
      >
        {label}
      </label>

      <div className="relative mt-2">
        <input
          id={id}
          type={showPassword ? "text" : "password"}
          autoComplete={autoComplete}
          placeholder={placeholder}
          className="
            h-11
            w-full
            rounded-lg
            border
            border-slate-700/80
            bg-[#0B121C]
            px-3.5
            pr-11
            text-[14px]
            text-slate-100
            outline-none
            transition-all
            duration-200
            placeholder:text-slate-600
            hover:border-slate-600
            focus:border-cyan-500/70
            focus:ring-2
            focus:ring-cyan-500/10
          "
        />

        <button
          type="button"
          onClick={() => setShowPassword((value) => !value)}
          className="
            absolute
            right-2
            top-1/2
            flex
            h-8
            w-8
            -translate-y-1/2
            items-center
            justify-center
            rounded-md
            border-0
            bg-transparent
            p-0
            text-slate-500
            transition-colors
            duration-200
            hover:bg-slate-800/70
            hover:text-slate-200
            focus:outline-none
            focus:ring-2
            focus:ring-cyan-500/20
          "
          title={showPassword ? "Hide password" : "Show password"}
          aria-label={showPassword ? "Hide password" : "Show password"}
        >
          <EyeIcon visible={showPassword} />
        </button>
      </div>
    </div>
  );
}

/** Shared password modal overlay. */
export default function PasswordModal() {
  return (
    <div
      className="
        modal
        fixed
        inset-0
        z-[100]
        flex
        items-center
        justify-center
        bg-black/70
        p-4
        backdrop-blur-[2px]
      "
      id="pwd-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pwd-title"
    >
      <div
        className="
          box
          !m-0
          !w-full
          !max-w-[440px]
          overflow-hidden
          !rounded-2xl
          !border
          !border-slate-800
          !bg-[#101720]
          !p-0
          shadow-[0_24px_70px_rgba(0,0,0,0.4)]
        "
      >
        {/* Header */}
        <div className="editor-head !flex !items-start !justify-between !border-b !border-slate-800 !px-6 !py-5">
          <div className="flex min-w-0 items-start gap-3.5">
            <div
              className="
                mt-0.5 flex h-10 w-10 shrink-0
                items-center justify-center
                rounded-xl
                border border-cyan-500/15
                bg-cyan-500/[0.07]
                text-cyan-400
              "
            >
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="5" y="10" width="14" height="11" rx="2.5" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                <circle cx="12" cy="15.5" r="1" />
              </svg>
            </div>

            <div className="min-w-0">
              <h2
                id="pwd-title"
                className="m-0 text-[16px] font-semibold tracking-[-0.01em] text-slate-100"
              >
                Change password
              </h2>

              <p
                className="muted mt-1 text-[12.5px] leading-5 text-slate-500"
                id="pwd-intro"
              >
                Update the password used for your local administrator account.
              </p>
            </div>
          </div>

          <button
            type="button"
            className="
              ghost
              ml-4 flex !h-8 !w-8 shrink-0
              !items-center !justify-center
              !rounded-lg
              !border-0
              !bg-transparent
              !p-0
              text-slate-500
              transition
              hover:!bg-slate-800
              hover:!text-slate-200
            "
            id="pwd-x"
            title="Close"
            aria-label="Close change password dialog"
          >
            <svg
              viewBox="0 0 24 24"
              width="17"
              height="17"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <div className="space-y-5 px-6 py-6">
          <PasswordField
            id="pwd-current"
            label="Current password"
            autoComplete="off"
          />

          <PasswordField
            id="pwd-new"
            label="New password"
            autoComplete="off"
          />

          <PasswordField
            id="pwd-confirm"
            label="Confirm new password"
            autoComplete="off"
          />

          {/* Requirement */}
          <div className="flex items-start gap-2.5">
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mt-[2px] shrink-0 text-slate-600"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5" />
              <path d="M12 8h.01" />
            </svg>

            <p className="m-0 text-[11.5px] leading-[18px] text-slate-500">
              Use at least{" "}
              <span className="font-medium text-slate-400">8 characters</span>{" "}
              with at least one letter and one number.
            </p>
          </div>

          {/* Existing error target */}
          <div
            id="pwd-err"
            className="
              err
              text-[12px]
              font-medium
              leading-5
              !text-red-400
              empty:hidden
            "
            role="alert"
          />
        </div>

        {/* Footer */}
        <div className="flex w-full items-center gap-3 border-t border-slate-800 px-6 py-4">
          <button
            type="button"
            className="
              ghost
              !h-10
              !w-full
              !rounded-lg
              !border
              !border-slate-700
              !bg-transparent
              !px-4
              !text-[13px]
              !font-medium
              !text-slate-300
              transition-all
              hover:!border-slate-600
              hover:!bg-slate-800
              hover:!text-white
            "
            id="pwd-cancel"
          >
            Cancel
          </button>

          <button
            type="button"
            className="
              go
              !h-10
              !w-full
              !rounded-lg
              !border-0
              !bg-cyan-500
              !px-4
              !text-[13px]
              !font-semibold
              text-white
              transition-colors
              hover:!bg-cyan-400
              focus:outline-none
              focus:ring-2
              focus:ring-cyan-400/25
              disabled:cursor-not-allowed
              disabled:opacity-50
            "
            id="pwd-save"
          >
            Save password
          </button>
        </div>
      </div>
    </div>
  );
}
