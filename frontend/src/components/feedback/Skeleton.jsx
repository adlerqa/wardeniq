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

/** A block of `count` lines: first large, last small (compat skeleton.blockLines). */
export function SkeletonLines({ count = 4 }) {
  return (
    <div>
      {Array.from({ length: count }, (_, i) => (
        <SkeletonLine key={i} size={i === 0 ? "lg" : i === count - 1 ? "sm" : "md"} />
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
