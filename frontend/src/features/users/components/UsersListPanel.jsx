import { SkeletonTable } from "../../../components/feedback/Skeleton.jsx";
import {
  ROLES,
  countActiveAdmins,
  lastLoginText,
  matchesFilters,
  rowActions,
  userAccess,
  userStatus,
} from "../lib/users.js";
import { ICONS } from "./icons.jsx";
import { AccessCell, ActionButton, Badge } from "./shared.jsx";

function StatusBadge({ user }) {
  const s = userStatus(user);
  if (s === "pending") return <Badge tone="amber">invite pending</Badge>;
  return s === "active" ? <Badge tone="green">active</Badge> : <Badge>disabled</Badge>;
}

function Actions({ user, list, activeAdmins }) {
  const make = {
    access: () => (
      <ActionButton key="access" icon={ICONS.access} label="Access" title="Manage project access" onClick={() => list.manageAccess(user)} />
    ),
    resend: () => (
      <ActionButton key="resend" icon={ICONS.resend} label="Resend" title="Resend invite email" onClick={() => list.resendInvite(user)} />
    ),
    cancel: () => (
      <ActionButton key="cancel" danger icon={ICONS.cancel} label="Cancel" title="Cancel this invite" onClick={() => list.cancelInvite(user)} />
    ),
    unlock: () => (
      <ActionButton
        key="unlock"
        icon={ICONS.lock}
        label="Add admin to unlock"
        title="You're the only admin — add another admin first to unlock this"
        onClick={list.adminHandoff}
      />
    ),
    disable: () => (
      <ActionButton key="disable" icon={ICONS.disable} label="Disable" title="Disable this user" onClick={() => list.setActive(user, false)} />
    ),
    enable: () => (
      <ActionButton key="enable" icon={ICONS.enable} label="Enable" title="Enable this user" onClick={() => list.setActive(user, true)} />
    ),
    delete: () => (
      <ActionButton key="delete" danger icon={ICONS.del} label="Delete" title="Delete this user" onClick={() => list.deleteUser(user)} />
    ),
  };
  return (
    <div className="flex flex-nowrap justify-end gap-1.5">
      {rowActions(user, { selfId: list.selfId, activeAdmins }).map((a) => make[a]())}
    </div>
  );
}

/** Users list with client-side filters and per-user actions. */
export default function UsersListPanel({ list, projects }) {
  const all = list.users || [];
  const rows = all.filter((u) => matchesFilters(u, list.filters));
  // Counted over ALL users, like the backend's "last active admin" guard.
  const activeAdmins = countActiveAdmins(all);
  return (
    <div className="card">
      <h2>Users</h2>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          aria-label="Search users"
          placeholder="Search name or email…"
          value={list.filters.q}
          onChange={(e) => list.setFilters({ q: e.target.value })}
          className="m-0 min-w-[180px] flex-1"
        />
        <select
          aria-label="Filter by status"
          value={list.filters.status}
          onChange={(e) => list.setFilters({ status: e.target.value })}
          className="m-0 w-auto"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
          <option value="pending">Invite pending</option>
        </select>
        <select
          aria-label="Filter by role"
          value={list.filters.role}
          onChange={(e) => list.setFilters({ role: e.target.value })}
          className="m-0 w-auto"
        >
          <option value="">All roles</option>
          <option value="admin">Admin</option>
          <option value="editor">Editor</option>
          <option value="viewer">Viewer</option>
        </select>
        <span className="ml-auto text-[12px] text-muted">
          {list.users ? `${rows.length} of ${all.length}` : ""}
        </span>
      </div>
      <div>
        {list.status === "loading" && <SkeletonTable cols={7} rows={6} label="Loading users" />}
        {list.status === "error" && <div className="mt-2 text-[12.5px] text-red">{list.error}</div>}
        {list.status === "ready" && !rows.length && (
          <div className="py-4 text-[12px] text-muted">
            {all.length
              ? "No users match these filters."
              : "No users yet. Invite your first teammate above."}
          </div>
        )}
        {list.status === "ready" && rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Access</th>
                <th>Status</th>
                <th>Last login</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => {
                const self = list.selfId != null && list.selfId === u.id;
                return (
                  <tr key={u.id}>
                    <td>
                      {u.email}
                      {self && (
                        <>
                          {" "}
                          <span className="text-[12px] text-muted">(you)</span>
                        </>
                      )}
                    </td>
                    <td>{u.name || ""}</td>
                    <td>
                      {/* Uncontrolled and re-created after every reload, so the
                          choice stays visible while the confirm dialog is open and
                          snaps back if it is cancelled, as before. */}
                      <select
                        key={`${u.role}-${list.loadCount}`}
                        aria-label={`Role for ${u.email}`}
                        defaultValue={u.role}
                        onChange={(e) => list.changeRole(u, e.target.value)}
                        className="w-auto"
                      >
                        {ROLES.map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <AccessCell access={userAccess(u, projects)} />
                    </td>
                    <td>
                      <StatusBadge user={u} />
                    </td>
                    <td className="text-[12px] text-muted">{lastLoginText(u)}</td>
                    <td>
                      <Actions user={u} list={list} activeAdmins={activeAdmins} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
