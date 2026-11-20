import { ProjectChecklist, RadioOption } from "./shared.jsx";
import { NO_PROJECTS_TEXT } from "../lib/users.js";

/**
 * Invite a user. The u-email, u-role and u-invite ids are kept because the
 * guided tour points at them.
 */
export default function InviteUserPanel({ invite, projects }) {
  const adminForcesAll = invite.role === "admin";
  return (
    <div className="card">
      <h2>Invite a user</h2>
      <div className="sub">
        New users sign in passwordlessly with an emailed one-time code.{" "}
        <b>Viewer</b>{" "}
        = read-only,{" "}
        <b>Editor</b>{" "}
        = create/edit/generate,{" "}
        <b>Admin</b>{" "}
        = also manage users &amp; configuration.
      </div>
      <div className="flex items-end gap-2.5">
        <div className="flex-[2]">
          <label htmlFor="u-email">Email</label>
          <input
            id="u-email"
            ref={invite.emailInput}
            type="email"
            placeholder="teammate@company.com"
            value={invite.email}
            onChange={(e) => invite.setEmail(e.target.value)}
          />
        </div>
        <div className="flex-1">
          <label htmlFor="u-name">Name</label>
          <input
            id="u-name"
            placeholder="optional"
            value={invite.name}
            onChange={(e) => invite.setName(e.target.value)}
          />
        </div>
        <div className="flex-[0_0_140px]">
          <label htmlFor="u-role">Role</label>
          <select id="u-role" value={invite.role} onChange={(e) => invite.setRole(e.target.value)}>
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button id="u-invite" type="button" className="go m-0 flex-1" onClick={invite.send}>
          Invite
        </button>
      </div>
      <div className="mt-3.5" role="group" aria-labelledby="u-access-label">
        <label id="u-access-label" className="mb-1.5 block">
          Project access
        </label>
        <div className="mb-2 flex gap-[18px]">
          <RadioOption
            name="u-scope"
            value="all"
            checked={invite.mode === "all"}
            disabled={adminForcesAll}
            onChange={invite.setMode}
          >
            All projects
          </RadioOption>
          <RadioOption
            name="u-scope"
            value="some"
            checked={invite.mode === "some"}
            disabled={adminForcesAll}
            onChange={invite.setMode}
          >
            Specific projects
          </RadioOption>
        </div>
        {!adminForcesAll && invite.mode === "some" && (
          <ProjectChecklist
            projects={projects}
            selected={invite.selected}
            onToggle={invite.toggleProject}
            emptyText={NO_PROJECTS_TEXT}
          />
        )}
        <div className="mt-1 text-[11.5px] text-muted">{invite.hint}</div>
      </div>
      <div className="mt-2 text-[12px] text-muted" aria-live="polite">
        {invite.msg}
      </div>
    </div>
  );
}
