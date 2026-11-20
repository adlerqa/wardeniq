import { Fragment } from "react";

import { planHeader, planSections } from "../lib/testPlan.js";

const UL = "my-2 pl-5";
const LI = "my-1";

function Section({ section }) {
  const s = section;
  return (
    <>
      <h2 className="!mt-5 [border-bottom:1px_solid_var(--line)] pb-[5px] text-accent2">
        {s.title}
      </h2>
      {s.kind === "paragraph" && <p>{s.text}</p>}
      {s.kind === "list" && (
        <ul className={UL}>
          {s.items.map((x, i) => (
            <li key={i} className={LI}>
              {x}
            </li>
          ))}
        </ul>
      )}
      {s.kind === "keyValue" && (
        <table className="mt-2.5">
          <tbody>
            {s.rows.map((r, i) => (
              <tr key={i}>
                <td className="w-[180px] font-semibold">{r.key}</td>
                <td>{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {s.kind === "grouped" &&
        s.groups.map((g) => (
          <Fragment key={g.label}>
            <h3 className="mb-1 mt-2.5 text-[13px]">{g.label}</h3>
            <ul className="mb-2 pl-5">
              {g.items.map((x, i) => (
                <li key={i} className={LI}>
                  {x}
                </li>
              ))}
            </ul>
          </Fragment>
        ))}
      {s.kind === "table" && (
        <table className="mt-2.5">
          <thead>
            <tr>
              {s.columns.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {s.rows.map((r, i) => (
              <tr key={i}>
                {r.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {s.kind === "json" && <pre>{s.text}</pre>}
    </>
  );
}

/** A generated test plan (React port of the compat renderTestPlan()). */
export default function TestPlanContent({ plan }) {
  const sections = planSections(plan);
  if (!plan || !plan.sections) return null;
  const header = planHeader(plan);
  return (
    <>
      <h1>{header.title}</h1>
      {header.projectLine && (
        <div className="mb-[15px] text-[12px] text-muted">{header.projectLine}</div>
      )}
      {sections.map((s, i) => (
        <Section key={i} section={s} />
      ))}
    </>
  );
}

