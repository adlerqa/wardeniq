import { SkeletonRows } from "../../../components/feedback/Skeleton.jsx";
import { cycleListMeta, cycleProgress } from "../lib/cycles.js";

/** Saved cycles of the project; a click opens the cycle below. */
export default function TestCyclesListPanel({ tc }) {
  const { list } = tc;
  let body = null;
  if (list.status === "loading") body = <SkeletonRows count={5} label="Loading test cycles" />;
  else if (list.status === "error") body = <div className="err">{`Couldn't load test cycles. ${list.error}`}</div>;
  else if (list.status === "ready")
    body = list.cycles.length ? (
      list.cycles.map((c) => (
        <div key={c.id} className="feat" onClick={() => tc.openCycle(c.id)}>
          <div className="n">
            {c.name} <span className="badge">{c.status || "draft"}</span>
          </div>
          <div className="progress" style={{ margin: "7px 0 4px" }}>
            <div className="pbar" style={{ width: `${cycleProgress(c).pct}%` }}></div>
          </div>
          <div className="m">{cycleListMeta(c)}</div>
        </div>
      ))
    ) : (
      <span className="muted">no cycles yet</span>
    );
  return (
    <div className="card">
      <h2>Test cycles</h2>
      <div className="sub">Saved release regression cycles for the selected project.</div>
      <div id="cyc-list">{body}</div>
    </div>
  );
}
