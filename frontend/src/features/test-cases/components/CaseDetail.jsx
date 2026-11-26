import { Fragment } from "react";

import { editCase } from "../../../lib/compatBridge.js";
import { EXPECTED_LABELS, caseDetail, caseMetaText, expectedKeys, isStructured } from "../lib/caseDetail.js";
import { typeLabel } from "../lib/testCases.js";
import PriorityBadge from "./PriorityBadge.jsx";

function ExpectedItem({ item }) {
  if (item !== null && typeof item === "object") return <pre>{JSON.stringify(item, null, 2)}</pre>;
  return String(item);
}

export function ExpectedValue({ value }) {
  if (Array.isArray(value))
    return value.length ? (
      <ul>
        {value.map((item, i) => (
          <li key={i}>
            <ExpectedItem item={item} />
          </li>
        ))}
      </ul>
    ) : (
      <span className="muted">None</span>
    );
  if (value && typeof value === "object")
    return (
      <ul>
        {Object.entries(value).map(([key, item]) => (
          <li key={key}>
            <b>{`${key.replaceAll("_", " ")}:`}</b>{" "}
            {Array.isArray(item) ? (
              <ul>
                {item.map((entry, i) => (
                  <li key={i}>
                    <ExpectedItem item={entry} />
                  </li>
                ))}
              </ul>
            ) : (
              <ExpectedItem item={item} />
            )}
          </li>
        ))}
      </ul>
    );
  return <span>{value === null || value === undefined || value === "" ? "Not specified" : String(value)}</span>;
}

function ExpectedResult({ value }) {
  if (!isStructured(value)) return <div className="case-detail-value">{caseMetaText(value)}</div>;
  return (
    <div className="expected-grid">
      {expectedKeys(value).map((key) => (
        <div key={key} className="expected-row">
          <div className="expected-key">{EXPECTED_LABELS[key] || key.replaceAll("_", " ")}</div>
          <div className="expected-content">
            <ExpectedValue value={value[key]} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** A test case's detail under its row: head, four panels and the steps table. */
export default function CaseDetail({ testCase: c, onClose }) {
  const d = caseDetail(c);
  return (
    <>
      <div className="case-detail-head">
        <div>
          <div style={{ fontSize: "15px", fontWeight: 700 }}>
            {c.display_id ? (
              <span className="badge" style={{ marginRight: "8px" }}>
                {c.display_id}
              </span>
            ) : null}
            {d.title}
            {d.imported ? (
              <span className="badge reused" style={{ marginLeft: "6px" }} title="Came from an uploaded sheet">
                Imported from sheet
              </span>
            ) : null}
          </div>
          <div style={{ marginTop: "5px" }}>
            <span className={`badge ${c.type}`}>{typeLabel(c.type)}</span> <PriorityBadge priority={c.priority} />{" "}
            {(c.tags || []).map((t, i) => (
              <Fragment key={i}>
                {i ? " " : null}
                <span className="badge">{t}</span>
              </Fragment>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", gap: "7px" }}>
          <button
            className="ghost needs-editor"
            onClick={(e) => {
              e.stopPropagation();
              editCase(c.id);
            }}
          >
            Edit testcase
          </button>
          <button
            className="ghost"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
          >
            Close
          </button>
        </div>
      </div>
      <div className="case-detail-grid">
        <div className="case-detail-panel">
          <div className="case-detail-label">Description</div>
          <div className="case-detail-value">{caseMetaText(d.description)}</div>
        </div>
        <div className="case-detail-panel">
          <div className="case-detail-label">Endpoint</div>
          <div className="case-detail-value">{d.endpoint || "Not applicable or not specified"}</div>
        </div>
        <div className="case-detail-panel">
          <div className="case-detail-label">Expected result</div>
          <ExpectedResult value={d.expected} />
        </div>
        <div className="case-detail-panel">
          <div className="case-detail-label">Source lineage</div>
          <div className="case-detail-value">{d.lineage}</div>
        </div>
      </div>
      <div className="case-steps-table">
        <div className="case-step case-step-head">
          <span>#</span>
          <span>Step</span>
          <span>Expected result</span>
        </div>
        {d.steps.length ? (
          d.steps.map((s, i) => (
            <div key={i} className="case-step">
              <span className="case-step-num">{`${i + 1}.`}</span>
              <span>{s.action}</span>
              <span className="case-step-expected">{s.expected || "No separate expected result"}</span>
            </div>
          ))
        ) : (
          <div className="case-detail-loading">No detailed steps were saved for this testcase.</div>
        )}
      </div>
    </>
  );
}
