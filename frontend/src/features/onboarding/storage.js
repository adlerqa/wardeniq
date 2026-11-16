/**
 * Per-user localStorage flags for the onboarding UI (issue #254): "the welcome
 * prompt was answered" and "the checklist was dismissed". Keys are scoped to
 * the signed-in user, so a second person signing in on the same browser still
 * gets their own first-visit welcome. Every access is guarded: storage can be
 * unavailable (private mode, blocked cookies) and must never break the page.
 */

/** Pure: the storage key for `base`, scoped to `user` when known. */
export function scopedKey(base, user) {
  const u = (user || "").trim().toLowerCase();
  return u ? `${base}:${u}` : base;
}

/** The signed-in user's email (or "admin"), as applyRole() writes it into #user-email. */
export function currentUser() {
  try {
    const el = document.getElementById("user-email");
    return el ? (el.textContent || "").trim().toLowerCase() : "";
  } catch {
    return "";
  }
}

export function readFlag(base, fallback = false) {
  try {
    return localStorage.getItem(scopedKey(base, currentUser())) === "1";
  } catch {
    return fallback;
  }
}

export function writeFlag(base, value) {
  try {
    const key = scopedKey(base, currentUser());
    if (value) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}
