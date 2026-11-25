import ProjectDetailPanel from "../components/ProjectDetailPanel.jsx";
import ProjectListPanel from "../components/ProjectListPanel.jsx";
import useCreateProject from "../hooks/useCreateProject.js";
import useProjects from "../hooks/useProjects.js";

/** Projects & Repos: project cards, the create wizard and project settings. */
export default function ProjectsPage() {
  const pj = useProjects();
  const cp = useCreateProject(pj);
  return (
    <section id="view-projects" className="view" hidden>
      <ProjectListPanel pj={pj} cp={cp} />
      <ProjectDetailPanel pj={pj} />
    </section>
  );
}
