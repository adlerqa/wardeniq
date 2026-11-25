import { PRIO_COLORS, prioKey, prioLabel } from "../lib/testCases.js";

/** Priority pill (00-core.js prioBadge). */
export default function PriorityBadge({ priority }) {
  const [border, background, color] = PRIO_COLORS[prioKey(priority)];
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: "999px",
        border: `1px solid ${border}`,
        background,
        color,
      }}
    >
      {prioLabel(priority)}
    </span>
  );
}
