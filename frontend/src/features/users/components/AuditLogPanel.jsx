import { SkeletonTable } from "../../../components/feedback/Skeleton.jsx";
import { auditDanger, auditDetail, auditTime } from "../lib/users.js";
import { Badge } from "./shared.jsx";

/** Recent security-relevant actions. */
export default function AuditLogPanel({ audit }) {
  return (
    <div className="card">
      <h2>Audit log</h2>
      <div className="sub">
        Recent security-relevant actions (invites, role changes, deletes, settings, denied access).
      </div>
      <div>
        {audit.status === "idle" && <span className="text-[12px] text-muted">Loading…</span>}
        {audit.status === "loading" && <SkeletonTable cols={5} rows={6} label="Loading audit log" />}
        {audit.status === "error" && (
          <div className="mt-2 text-[12.5px] text-red">
            Couldn&apos;t load the audit log. {audit.error}
          </div>
        )}
        {audit.status === "ready" && !audit.logs.length && (
          <span className="text-[12px] text-muted">No audit entries yet.</span>
        )}
        {audit.status === "ready" && audit.logs.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Target</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {audit.logs.map((l, i) => (
                <tr key={l.id || i}>
                  <td className="whitespace-nowrap text-[12px] text-muted">{auditTime(l.ts)}</td>
                  <td>
                    <Badge tone={auditDanger(l.action) ? "red" : "green"}>{l.action || ""}</Badge>
                  </td>
                  <td>{l.actor_email || l.actor_id || "—"}</td>
                  <td>{l.target || "—"}</td>
                  <td className="text-[11.5px] text-muted">{auditDetail(l)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
