import InviteUserPanel from "../components/InviteUserPanel.jsx";
import UsersListPanel from "../components/UsersListPanel.jsx";
import ApiTokensPanel from "../components/ApiTokensPanel.jsx";
import AuditLogPanel from "../components/AuditLogPanel.jsx";
import useUsersScreen from "../hooks/useUsersScreen.js";

export default function UsersPage() {
  const screen = useUsersScreen();
  return (
    <section id="view-users" className="view" hidden>
      <InviteUserPanel invite={screen.invite} projects={screen.projects} />
      <UsersListPanel list={screen.list} projects={screen.projects} />
      <ApiTokensPanel />
      <AuditLogPanel audit={screen.audit} />
    </section>
  );
}
