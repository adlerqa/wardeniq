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

/** Wrapper that announces the loading state to assistive tech. */
export function SkeletonState({ label = "Loading content", children }) {
  return (
    <div role="status" aria-label={label} className="w-full">
      {children}
    </div>
  );
}
