import InviteUserPanel from "../components/InviteUserPanel.jsx";
import UsersListPanel from "../components/UsersListPanel.jsx";
import ApiTokensPanel from "../components/ApiTokensPanel.jsx";
import AuditLogPanel from "../components/AuditLogPanel.jsx";

export default function UsersPage() {
  return (
    <section id="view-users" className="view" hidden>
      <InviteUserPanel />
      <UsersListPanel />
      <ApiTokensPanel />
      <AuditLogPanel />
    </section>
  );
}
