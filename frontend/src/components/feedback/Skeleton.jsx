/**
 * Shimmer placeholders (React port of the compat `skeleton` helpers in
 * 00-core.js / styles/compat/06-feedback-and-loaders.css).
 */
const BASE =
  "relative overflow-hidden rounded-md bg-[#151d29] bg-[linear-gradient(90deg,rgba(255,255,255,0.02)_0%,rgba(255,255,255,0.07)_45%,rgba(255,255,255,0.02)_90%)] bg-[length:320px_100%] bg-no-repeat animate-shimmer";
const SIZES = {
  sm: "my-2 h-2.5 w-[55%]",
  md: "my-2 h-3",
  lg: "my-2 h-4 w-[70%]",
};

/** One line. `size` is sm | md | lg; `className` adds or overrides utilities. */
export function SkeletonLine({ size = "md", className = "" }) {
  return <div className={`${BASE} ${SIZES[size]} ${className}`} />;
}

/**
 * A block of `count` lines (first large, last small), returned as a fragment so
 * the lines sit directly in the parent's layout, like compat skeleton.blockLines().
 */
export function SkeletonBlockLines({ count = 4 }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <SkeletonLine key={i} size={i === 0 ? "lg" : i === count - 1 ? "sm" : "md"} />
      ))}
    </>
  );
}

const CARD =
  "min-h-[154px] rounded-2xl border border-solid border-[rgba(116,139,166,0.16)] bg-[linear-gradient(145deg,rgba(24,34,48,0.6),rgba(13,20,30,0.7))] p-[22px]";

/** Placeholder card (compat .sk-card). */
export function SkeletonCard({ className = "", children }) {
  return <div className={`${CARD} ${className}`}>{children}</div>;
}

/** Placeholder KPI tiles (compat skeleton.kpis()). */
export function SkeletonKpis({ count = 7 }) {
  return Array.from({ length: count }, (_, i) => (
    <div key={i} className="min-h-[86px] rounded-[14px] border border-solid border-line p-[18px]">
      <SkeletonLine className="!h-6 !w-1/2" />
      <SkeletonLine size="sm" className="!mt-2.5" />
    </div>
  ));
}

/** Loading placeholder of the Dashboard (compat skeleton.dashboard()). */
export function SkeletonDashboard() {
  return (
    <SkeletonState label="Loading dashboard">
      <SkeletonLine size="lg" className="!mb-5 !h-6 !w-[180px]" />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-4">
        <SkeletonKpis count={7} />
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1000px]:grid-cols-2">
        <SkeletonCard>
          <SkeletonKpis count={2} />
        </SkeletonCard>
        <SkeletonCard>
          <SkeletonBlockLines count={5} />
        </SkeletonCard>
      </div>
      <SkeletonCard className="mt-4">
        <SkeletonBlockLines count={6} />
      </SkeletonCard>
    </SkeletonState>
  );
}

/** Grid of placeholder cards (compat skeleton.cards()). */
export function SkeletonCards({ count = 6 }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className={CARD}>
          <SkeletonLine size="lg" />
          <SkeletonLine size="sm" />
          <SkeletonLine className="!mt-[22px] w-[40%]" />
        </div>
      ))}
    </div>
  );
}

/** Placeholder table: a header row and `rows` rows of `cols` cells (compat skeleton.table()). */
export function SkeletonTable({ cols = 5, rows = 5, label = "Loading table" }) {
  const c = Array.from({ length: cols }, (_, i) => i);
  return (
    <SkeletonState label={label}>
      <div className="overflow-auto">
        <table>
          <tbody>
            <tr>
              {c.map((i) => (
                <th key={i}>
                  <SkeletonLine size="sm" className="!my-0 !w-[70%]" />
                </th>
              ))}
            </tr>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                {c.map((i) => (
                  <td key={i}>
                    <SkeletonLine className="!my-0" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SkeletonState>
  );
}

/** Placeholder list rows: icon, two lines and a pill (compat skeleton.rows()). */
export function SkeletonRows({ count = 5, label = "Loading rows" }) {
  return (
    <SkeletonState label={label}>
      <div className="overflow-hidden rounded-xl border border-solid border-line">
        {Array.from({ length: count }, (_, i) => (
          <div
            key={i}
            className="flex items-center gap-[14px] border-0 border-b border-solid border-white/[0.04] px-4 py-[14px] last:border-b-0"
          >
            <SkeletonLine className="!my-0 !h-9 !w-9 flex-[0_0_auto] !rounded-[10px]" />
            <div className="flex-1">
              <SkeletonLine size="lg" className="!mb-2 !mt-0" />
              <SkeletonLine size="sm" className="!my-0" />
            </div>
            <SkeletonLine className="!my-0 !h-5 !w-16 flex-[0_0_auto] !rounded-[20px]" />
          </div>
        ))}
      </div>
    </SkeletonState>
  );
}

/** Wrapper that announces the loading state to assistive tech. */
export function SkeletonState({ label = "Loading content", children }) {
  return (
    <div role="status" aria-label={label} className="w-full">
      {children}
    </div>
  );
}
