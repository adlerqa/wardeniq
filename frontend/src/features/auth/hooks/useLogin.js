import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api.js";
import { setCurrentUser } from "../../../lib/compatBridge.js";
import {
  CODE_LENGTH,
  INTRO_OTP,
  INTRO_PASSWORD,
  SESSION_LOST,
  boxDigit,
  createBootPoller,
  loginMethod,
  otpSentMessage,
  pastedDigits,
  smtpStatusWithRetry,
} from "../lib/login.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

/**
 * Sign-in screen state (was the login half of compat/runtime/controllers/10-auth.js).
 *
 * Registers window.showLogin({ msg }) — used by api() on a 401, the bridge,
 * logout and the invite-link boot (16-boot.js). After a successful sign-in it
 * hands off to the compat runtime: applyRole, maybeShowInvite, startApp.
 *
 * The overlay's `hidden` attribute is set directly (not as React state) because
 * checkAuth (useIdentity.js) hides it on boot from outside this hook. The inputs
 * are uncontrolled for the same reason: the invite-link boot prefills the email.
 */
export function useLogin() {
  const root = useRef(null);
  const field = {
    email: useRef(null),
    username: useRef(null),
    pw: useRef(null),
    target: useRef(null),
    code: useRef(null),
    newPw: useRef(null),
    masterUser: useRef(null),
    masterSecret: useRef(null),
    masterNewPw: useRef(null),
  };
  const boxes = useRef([]);
  const [step, setStep] = useState("step1");
  const [intro, setIntro] = useState("Sign in to continue to your WardenIQ workspace.");
  const [boot, setBoot] = useState({ hidden: true, text: "" });
  const [msg, setMsg] = useState({ text: "" });
  const [err, setErr] = useState("");
  const [to, setTo] = useState("");
  const [sent, setSent] = useState("Verification code sent to");
  const [busy, setBusyState] = useState(() => new Set());
  const busyRef = useRef(busy);

  const value = (k) => (field[k].current ? field[k].current.value : "");
  const isShown = () => !!root.current && !root.current.hidden;
  const setBusy = (id, on) => {
    const next = new Set(busyRef.current);
    if (on) next.add(id);
    else next.delete(id);
    busyRef.current = next;
    setBusyState(next);
  };
  const isBusy = (id) => busyRef.current.has(id);
  const withBusy = async (id, fn) => {
    setBusy(id, true);
    try {
      await fn();
    } finally {
      setBusy(id, false);
    }
  };

  const poller = useRef(null);
  if (!poller.current)
    poller.current = createBootPoller({
      api: (p) => api(p),
      isShown,
      show: (text) => setBoot({ hidden: false, text }),
      hide: () => setBoot({ hidden: true, text: "" }),
      setTimeout: (fn, ms) => setTimeout(fn, ms),
    });

  // ---- 6-box code entry ----
  const code = () =>
    boxes.current
      .map((b) => (b ? b.value : ""))
      .join("")
      .replace(/\D/g, "");
  const clearCode = () => boxes.current.forEach((b) => b && (b.value = ""));
  const focusCode = () => {
    const b = boxes.current.filter(Boolean);
    (b.find((x) => !x.value) || b[0])?.focus();
  };

  const showLogin = async (opts) => {
    setCurrentUser(null);
    if (root.current) root.current.hidden = false;
    void poller.current.start();
    const menu = document.getElementById("usermenu");
    if (menu) menu.hidden = true;
    setErr("");
    setMsg({ text: (opts && opts.msg) || "" });
    clearCode();
    const status = await smtpStatusWithRetry((p) => api(p));
    if (loginMethod(status) === "otp") {
      setIntro(INTRO_OTP);
      setStep("step1");
      setTimeout(() => field.email.current?.focus(), 50);
    } else {
      setIntro(INTRO_PASSWORD);
      setStep("password");
      setTimeout(() => field.username.current?.focus(), 50);
    }
  };
  const showRef = useRef(showLogin);
  showRef.current = showLogin;

  const signedIn = async (user) => {
    setCurrentUser(user);
    if (root.current) root.current.hidden = true;
    callWindow("applyRole");
    try {
      sessionStorage.removeItem("wq_invite_token");
    } catch {
      /* storage unavailable */
    }
    if (await callWindow("maybeShowInvite")) return;
    callWindow("startApp");
  };

  // ---- email one-time code ----
  const send = async () => {
    if (isBusy("login-send")) return;
    const email = value("email").trim();
    if (!email) {
      setErr("Enter your email");
      return;
    }
    await withBusy("login-send", async () => {
      setErr("");
      setMsg({ text: "Sending your sign-in code…" });
      try {
        const r = await api("/api/auth/request-otp", { method: "POST", json: { email } });
        setStep("step2");
        setTo(email);
        const m = otpSentMessage(r);
        setSent(m.sent);
        setMsg(m.msg);
        clearCode();
        setTimeout(focusCode, 50);
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  const verify = async () => {
    if (isBusy("login-verify")) return;
    const c = code();
    if (!c) {
      setErr("Enter the code");
      return;
    }
    await withBusy("login-verify", async () => {
      setErr("");
      try {
        const r = await api("/api/auth/verify-otp", { method: "POST", json: { email: to, code: c } });
        let user = r.user;
        // The code was accepted: confirm the HTTP-only session cookie was stored and works.
        try {
          const me = await fetch("/api/auth/me", { credentials: "include" });
          if (!me.ok) throw new Error("Session cookie was not created correctly.");
          const data = await me.json();
          if (!data?.user) throw new Error("Authenticated user could not be restored.");
          user = data.user;
        } catch (sessionError) {
          console.error("[Auth] OTP succeeded but session validation failed:", sessionError);
          showLogin();
          setErr(SESSION_LOST);
          return;
        }
        await signedIn(user);
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  const back = () => {
    setStep("step1");
    setErr("");
    setMsg({ text: "" });
    clearCode();
  };

  const boxProps = (i) => ({
    ref: (el) => {
      boxes.current[i] = el;
    },
    onInput: (e) => {
      const box = e.currentTarget;
      box.value = boxDigit(box.value);
      if (box.value && i < CODE_LENGTH - 1) boxes.current[i + 1]?.focus();
    },
    onKeyDown: (e) => {
      const b = boxes.current;
      if (e.key === "Enter") {
        verify();
      } else if (e.key === "Backspace" && !e.currentTarget.value && i > 0) {
        b[i - 1].value = "";
        b[i - 1].focus();
        e.preventDefault();
      } else if (e.key === "ArrowLeft" && i > 0) {
        b[i - 1].focus();
        e.preventDefault();
      } else if (e.key === "ArrowRight" && i < CODE_LENGTH - 1) {
        b[i + 1].focus();
        e.preventDefault();
      }
    },
    onPaste: (e) => {
      e.preventDefault();
      const digits = pastedDigits((e.clipboardData || window.clipboardData).getData("text"));
      if (!digits) return;
      const b = boxes.current;
      digits.split("").forEach((d, k) => {
        if (b[k]) b[k].value = d;
      });
      (b[Math.min(digits.length, CODE_LENGTH - 1)] || e.currentTarget).focus();
      if (digits.length >= CODE_LENGTH) verify();
    },
  });

  // ---- username / password (no SMTP) ----
  const signIn = async () => {
    if (isBusy("login-signin")) return;
    const username = value("username").trim();
    const password = value("pw");
    if (!username) {
      setErr("Enter your username");
      return;
    }
    if (!password) {
      setErr("Enter your password");
      return;
    }
    await withBusy("login-signin", async () => {
      setErr("");
      try {
        const r = await api("/api/auth/login-password", { method: "POST", json: { username, password } });
        await signedIn(r.user);
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  // ---- forgot / reset password ----
  const forgot = async () => {
    setStep(null);
    setErr("");
    setMsg({ text: "" });
    try {
      const status = await api("/api/auth/smtp-status");
      if (status && status.smtp_setup) {
        setStep("forgot1");
        if (field.target.current) field.target.current.value = value("username").trim();
      } else {
        setStep("nosmtp");
      }
    } catch {
      setStep("nosmtp");
    }
  };

  const backToLogin = () => {
    setStep(null);
    showLogin();
  };

  const requestReset = async () => {
    if (isBusy("reset-request-btn")) return;
    const target = value("target").trim();
    if (!target) {
      setErr("Enter username or email");
      return;
    }
    await withBusy("reset-request-btn", async () => {
      setErr("");
      setMsg({ text: "" });
      try {
        const r = await api("/api/auth/request-password-reset", {
          method: "POST",
          json: { username_or_email: target },
        });
        if (r.smtp_configured) {
          setMsg({ text: r.message || "Reset code sent. Please check your email." });
          setStep("forgot2");
        } else {
          setStep("nosmtp");
        }
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  const submitReset = async () => {
    if (isBusy("reset-submit-btn")) return;
    const target = value("target").trim();
    const c = value("code").trim();
    const newPassword = value("newPw");
    if (!c) {
      setErr("Enter the 6-digit reset code");
      return;
    }
    if (!newPassword) {
      setErr("Enter a new password");
      return;
    }
    await withBusy("reset-submit-btn", async () => {
      setErr("");
      setMsg({ text: "" });
      try {
        const r = await api("/api/auth/reset-password", {
          method: "POST",
          json: { username_or_email: target, code: c, new_password: newPassword },
        });
        setMsg({ text: r.message || "Password reset successfully. Please sign in." });
        setStep(null);
        showLogin();
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  const masterReset = async () => {
    if (isBusy("reset-master-submit-btn")) return;
    const username = value("masterUser").trim() || "admin";
    const appSecret = value("masterSecret").trim();
    const newPassword = value("masterNewPw");
    if (!appSecret) {
      setErr("Enter App Master Secret (APP_SECRET)");
      return;
    }
    if (!newPassword) {
      setErr("Enter a new password");
      return;
    }
    await withBusy("reset-master-submit-btn", async () => {
      setErr("");
      setMsg({ text: "" });
      try {
        const r = await api("/api/auth/reset-password-master", {
          method: "POST",
          json: { username, app_secret: appSecret, new_password: newPassword },
        });
        setMsg({ text: r.message || "Password reset successfully. Please sign in." });
        setStep(null);
        showLogin();
      } catch (e) {
        setErr(e.message);
      }
    });
  };

  useEffect(() => {
    const fn = (opts) => showRef.current(opts);
    window.showLogin = fn;
    const p = poller.current;
    return () => {
      p.stop();
      if (window.showLogin === fn) delete window.showLogin;
    };
  }, []);

  const onEnter = (fn) => (e) => {
    if (e.key === "Enter") fn();
  };

  return {
    root,
    field,
    boxProps,
    step,
    intro,
    boot,
    msg,
    err,
    to,
    sent,
    busy,
    actions: {
      send,
      verify,
      back,
      signIn,
      forgot,
      backToLogin,
      requestReset,
      submitReset,
      masterReset,
      emailKey: onEnter(send),
      usernameKey: onEnter(() => field.pw.current?.focus()),
      pwKey: onEnter(signIn),
    },
  };
}
