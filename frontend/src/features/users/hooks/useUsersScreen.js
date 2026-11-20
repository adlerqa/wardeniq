import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { escapeHtml } from "../../../lib/html.js";
import {
  currentUser,
  roleDescription,
  toast,
  uiConfirm,
  uiModalHTML,
} from "../../../lib/compatBridge.js";
import {
  HANDOFF_HTML,
  HINT_ADMIN,
  MSG_SELECT_PROJECT,
  accessDialogHtml,
  deliveryFailed,
  inviteHint,
  inviteScope,
  readAccessDialog,
  roleChangeMessage,
  validateInvite,
} from "../lib/users.js";

const INVITE = {
  email: "",
  name: "",
  role: "viewer",
  mode: "all",
  selected: [],
  hint: HINT_ADMIN, // the legacy form showed the admin hint until the first change
  msg: "",
};

/**
 * State and actions for the Users screen panels (invite form, users list,
 * audit log), ported from the compat 11-users.js. navigateTo("users") in
 * 00-core.js calls loadProjectPicker(), loadUsers() and loadAudit(); this hook
 * registers those on window while mounted. Nothing loads on mount: the screen
 * is mounted (hidden) for every role and these APIs are admin-only.
 */
export default function useUsersScreen() {
  const [projects, setProjects] = useState([]);
  const projectsRef = useRef([]);
  const [invite, setInvite] = useState(INVITE);
  const inviteRef = useRef(INVITE);
  const [users, setUsers] = useState(null);
  const [usersStatus, setUsersStatus] = useState("idle");
  const [usersError, setUsersError] = useState("");
  const [loadCount, setLoadCount] = useState(0);
  const [filters, setFilters] = useState({ q: "", status: "", role: "" });
  const [audit, setAudit] = useState({ status: "idle", logs: [], error: "" });
  const [selfId, setSelfId] = useState(null);
  const emailInput = useRef(null);
  const mounted = useRef(false);
  const seq = useRef({ users: 0, audit: 0, picker: 0 });

  const updateInvite = useCallback((change) => {
    const next = { ...inviteRef.current, ...change };
    inviteRef.current = next;
    if (mounted.current) setInvite(next);
  }, []);

  const storeProjects = useCallback((list) => {
    projectsRef.current = list;
    if (mounted.current) setProjects(list);
  }, []);

  const loadProjectPicker = useCallback(async () => {
    const my = ++seq.current.picker;
    let list;
    try {
      const r = await api("/api/projects");
      list = r.projects || [];
    } catch {
      list = [];
    }
    if (my !== seq.current.picker) return;
    storeProjects(list);
    updateInvite({ selected: [] }); // the picker is rebuilt, so ticks reset
  }, [storeProjects, updateInvite]);

  const loadUsers = useCallback(async () => {
    const my = ++seq.current.users;
    const current = () => mounted.current && my === seq.current.users;
    setUsersStatus("loading");
    try {
      if (!projectsRef.current.length) {
        try {
          const pr = await api("/api/projects");
          if (!projectsRef.current.length) storeProjects(pr.projects || []);
        } catch {
          /* project names are optional here */
        }
      }
      const r = await api("/api/users");
      if (!current()) return;
      const me = currentUser();
      setSelfId(me ? me.id : null);
      setUsers(r.users || []);
      setUsersStatus("ready");
      setLoadCount((n) => n + 1);
    } catch (e) {
      if (!current()) return;
      setUsersError(e.message);
      setUsersStatus("error");
    }
  }, [storeProjects]);

  const loadAudit = useCallback(async () => {
    const my = ++seq.current.audit;
    const current = () => mounted.current && my === seq.current.audit;
    setAudit((a) => ({ ...a, status: "loading" }));
    try {
      const r = await api("/api/audit-logs?limit=100");
      if (!current()) return;
      setAudit({ status: "ready", logs: r.logs || [], error: "" });
    } catch (e) {
      if (!current()) return;
      setAudit({ status: "error", logs: [], error: e.message });
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const hooks = {
      loadProjectPicker: () => loadProjectPicker(),
      loadUsers: () => loadUsers(),
      loadAudit: () => loadAudit(),
    };
    Object.assign(window, hooks);
    return () => {
      mounted.current = false;
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [loadProjectPicker, loadUsers, loadAudit]);

  // ---- invite form ----
  const setRole = (role) => updateInvite({ role, hint: inviteHint(role, inviteRef.current.mode) });
  const setMode = (mode) => updateInvite({ mode, hint: inviteHint(inviteRef.current.role, mode) });
  const toggleProject = (id, on) => {
    const sel = inviteRef.current.selected;
    updateInvite({ selected: on ? [...sel, id] : sel.filter((x) => x !== id) });
  };

  const sendInvite = async () => {
    const f = inviteRef.current;
    const email = f.email.trim();
    const name = f.name.trim();
    const scope = inviteScope(f.role, f.mode, f.selected);
    const invalid = validateInvite(email, scope);
    if (invalid) {
      toast(invalid, true);
      return;
    }
    try {
      const r = await api("/api/users", {
        method: "POST",
        json: { email, name, role: f.role, ...scope },
      });
      const msg = (r && r.message) || "User created.";
      updateInvite({ email: "", name: "", msg });
      if (deliveryFailed(r)) {
        toast(msg, { type: "warn", title: "User created, but invitation email failed" });
      } else {
        toast(msg);
      }
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't invite user" });
    }
  };

  // ---- row actions ----
  const patchUser = (id, body) => api(`/api/users/${id}`, { method: "PATCH", json: body });

  const changeRole = async (u, role) => {
    const who = u ? u.name || u.email : "this user";
    if (!(await uiConfirm(roleChangeMessage(who, role, roleDescription(role)), "Change role", "Change role"))) {
      loadUsers();
      return;
    }
    try {
      await patchUser(u.id, { role });
      toast(`Role changed to ${role}.`);
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't change user role" });
    }
    loadUsers();
  };

  const setActive = async (u, active) => {
    try {
      await patchUser(u.id, { active });
      toast(active ? "Enabled" : "Disabled");
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't update user status" });
    }
  };

  const deleteUser = async (u) => {
    if (!(await uiConfirm(`Delete ${u.email}?`, "Delete User", "Delete", true))) return;
    try {
      await api(`/api/users/${u.id}`, { method: "DELETE" });
      toast("User deleted");
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't delete user" });
    }
  };

  const resendInvite = async (u) => {
    try {
      const r = await api(`/api/users/${u.id}/resend-invite`, { method: "POST" });
      const msg = (r && r.message) || "Invite re-sent.";
      updateInvite({ msg });
      if (deliveryFailed(r)) {
        toast(msg, { type: "warn", title: "Invitation email not sent" });
      } else {
        toast(msg);
      }
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't resend invitation" });
    }
  };

  const cancelInvite = async (u) => {
    if (
      !(await uiConfirm(
        `Cancel the pending invite for ${u.email}?`,
        "Cancel Invite",
        "Cancel invite",
        true,
      ))
    )
      return;
    try {
      await api(`/api/users/${u.id}/cancel-invite`, { method: "POST" });
      toast("Invite cancelled");
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't cancel invitation" });
    }
  };

  const manageAccess = async (u) => {
    if (!projectsRef.current.length) {
      try {
        const pr = await api("/api/projects");
        storeProjects(pr.projects || []);
      } catch {
        /* the dialog says when there are no projects */
      }
    }
    // The title is set as text by uiModalHTML; it was HTML-escaped before as well.
    const ok = await uiModalHTML(
      `Project access — ${escapeHtml(u.email)}`,
      accessDialogHtml(u, projectsRef.current),
      "Save access",
    );
    if (!ok) return;
    const scope = readAccessDialog(document);
    if (!scope.all_projects && !scope.project_ids.length) {
      toast(MSG_SELECT_PROJECT, true);
      return;
    }
    try {
      await patchUser(u.id, scope);
      toast("Project access updated");
      loadUsers();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't update project access" });
    }
  };

  // Guided hand-off, offered instead of "Disable" when you are the only active admin.
  const adminHandoff = async () => {
    const ok = await uiModalHTML("Add another admin first", HANDOFF_HTML, "Assign an admin email");
    if (!ok) return; // keep using this local admin: no change
    setRole("admin");
    const input = emailInput.current;
    if (input) {
      input.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => input.focus(), 300);
    }
    toast("Role preset to Admin — enter their email above and click Invite.");
  };

  return {
    projects,
    invite: {
      ...invite,
      emailInput,
      setEmail: (email) => updateInvite({ email }),
      setName: (name) => updateInvite({ name }),
      setRole,
      setMode,
      toggleProject,
      send: sendInvite,
    },
    list: {
      users,
      loadCount,
      status: usersStatus,
      error: usersError,
      filters,
      setFilters: (change) => setFilters((f) => ({ ...f, ...change })),
      selfId,
      changeRole,
      setActive,
      deleteUser,
      resendInvite,
      cancelInvite,
      manageAccess,
      adminHandoff,
    },
    audit,
  };
}
