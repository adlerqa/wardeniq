import { useCallback, useMemo, useRef, useState } from "react";

import { mmModel, mmSafeTipNodes, zoomStep } from "../lib/graph.js";

/**
 * State of the coverage graph (was MM_SEL / MM_FILTER / MM_K / MM_MODE and
 * the document listeners in 09-mind-map-and-jobs.js).
 *
 * `drawKey` changes whenever the old code redrew the SVG (new data, layout,
 * feature, bucket, filter, reset) but not on zoom, which only rewrote the
 * zoom transform. Keying the SVG on it resets the drag-pan the same way.
 */
export default function useCoverageGraph(data) {
  const [view, setView] = useState({ sel: null, filter: null, k: 1, mode: "auto", drawKey: 0 });
  const tipRef = useRef(null);
  const m = useMemo(() => (data ? mmModel(data) : null), [data]);
  const redraw = (patch) => setView((v) => ({ ...v, ...patch, drawKey: v.drawKey + 1 }));

  /** Clicks anywhere in the graph card: layout, breadcrumb / back, bucket, feature, filter chip. */
  const onCardClick = (e) => {
    const t = e.target;
    if (!t || typeof t.closest !== "function") return;
    const md = t.closest("[data-mmmode]");
    if (md) {
      redraw({ mode: md.dataset.mmmode, k: 1 });
      return;
    }
    if (t.closest("#mm-crumb-root") || t.closest(".mm-hub-back")) {
      redraw({ sel: null, filter: null, k: 1 });
      return;
    }
    const b = t.closest("[data-mmbucket]");
    if (b) {
      const [i, st] = b.dataset.mmbucket.split(":");
      redraw({ sel: +i, filter: st, k: 1 });
      return;
    }
    const f = t.closest("[data-mmfeat]");
    if (f) {
      const i = +f.dataset.mmfeat;
      setView((v) => ({ ...v, sel: v.sel === i ? null : i, filter: null, k: 1, drawKey: v.drawKey + 1 }));
      return;
    }
    const fl = t.closest("[data-mmfilter]");
    if (fl) redraw({ filter: fl.dataset.mmfilter || null });
  };

  const zoom = (d) => setView((v) => ({ ...v, k: zoomStep(v.k, d) }));
  const reset = () => redraw({ sel: null, filter: null, k: 1 });

  /** Tooltip: the hovered node's data-tip, through the formatting-only sanitizer. */
  const onCardMouseOver = useCallback((e) => {
    const tip = tipRef.current;
    if (!tip) return;
    const t = e.target && typeof e.target.closest === "function" ? e.target.closest("[data-tip]") : null;
    if (!t) {
      tip.hidden = true;
      return;
    }
    tip.replaceChildren(mmSafeTipNodes(t.getAttribute("data-tip")));
    tip.hidden = false;
    const b = e.currentTarget.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(8, e.clientX - b.left + 14), Math.max(8, b.width - 262)) + "px";
    tip.style.top = Math.max(6, e.clientY - b.top - 8) + "px";
  }, []);
  const onCardMouseOut = useCallback(() => {
    if (tipRef.current) tipRef.current.hidden = true;
  }, []);

  // A new /mindmap response redraws (selection and layout are kept, as before).
  const [seenData, setSeenData] = useState(data);
  if (seenData !== data) {
    setSeenData(data);
    setView((v) => ({ ...v, drawKey: v.drawKey + 1 }));
  }

  return { m, ...view, tipRef, onCardClick, onCardMouseOver, onCardMouseOut, zoom, reset };
}
