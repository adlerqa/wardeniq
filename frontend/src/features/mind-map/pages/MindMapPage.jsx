import { useEffect, useRef, useState } from "react";

import { CoverageList } from "../components/CoverageList.jsx";
import GitRepoPicker from "../components/GitRepoPicker.jsx";
import { AnalysisStatus, IndexedCodeDiag, RepoRows } from "../components/MindmapControls.jsx";
import useMindmap from "../hooks/useMindmap.js";

/**
 * MindMapPage
 *
 * React structure for the implementation coverage mind map.
 *
 * Project / repo controls, the analysis run, diagnostics and the coverage
 * list are React (useMindmap). The SVG graph inside #mm-graph is still drawn
 * by the mind-map compatibility controller.
 *
 * Additional interactions handled here:
 * - Mouse wheel zoom
 * - Drag / grab to pan
 * - Fullscreen mode
 */
export default function MindMapPage() {
  const mm = useMindmap();
  const graphCardRef = useRef(null);
  const graphStageRef = useRef(null);

const dragStateRef = useRef({
  active: false,
  moved: false,
  captured: false,

  pointerId: null,

  startClientX: 0,
  startClientY: 0,

  startSvgX: 0,
  startSvgY: 0,

  startPanX: 0,
  startPanY: 0,
});

  const suppressClickRef = useRef(false);
  const lastWheelZoomRef = useRef(0);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  /**
   * Fullscreen
   */
  const handleFullscreen = async () => {
    try {
      if (!graphCardRef.current) return;

      if (!document.fullscreenElement) {
        await graphCardRef.current.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch (error) {
      console.error("Fullscreen mode failed:", error);
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === graphCardRef.current);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  /**
   * Wheel zoom + grab/pan
   *
   * Important:
   * We intentionally reuse the existing mm-zoom-in / mm-zoom-out buttons.
   * This means the current compatibility controller remains the source of
   * truth for zoom state (MM_K), instead of creating a second zoom system.
   */
  useEffect(() => {
  const stage = graphStageRef.current;

  if (!stage) return undefined;

  const SVG_NS = "http://www.w3.org/2000/svg";

  const getSvg = () =>
    stage.querySelector("svg.mm-svg");

  const getZoomGroup = () =>
    stage.querySelector("#mm-zoom");

  /**
   * Create a separate pan layer around #mm-zoom.
   *
   * Important:
   * We NEVER modify #mm-zoom's own transform.
   * Your existing controller can continue controlling:
   *
   * translate(...)
   * scale(...)
   * translate(...)
   *
   * without React destroying its centering.
   */
  const ensurePanLayer = () => {
    const zoomGroup = getZoomGroup();

    if (!zoomGroup) return null;

    const parent = zoomGroup.parentNode;

    if (
      parent instanceof SVGElement &&
      parent.dataset.mmPanLayer === "true"
    ) {
      return parent;
    }

    const panLayer =
      document.createElementNS(SVG_NS, "g");

    panLayer.dataset.mmPanLayer = "true";
    panLayer.dataset.mmPanX = "0";
    panLayer.dataset.mmPanY = "0";

    parent.insertBefore(panLayer, zoomGroup);
    panLayer.appendChild(zoomGroup);

    return panLayer;
  };

  const getPan = () => {
    const layer = ensurePanLayer();

    if (!layer) {
      return {
        x: 0,
        y: 0,
      };
    }

    return {
      x: Number(
        layer.dataset.mmPanX || 0
      ),
      y: Number(
        layer.dataset.mmPanY || 0
      ),
    };
  };

  const setPan = (x, y) => {
    const layer = ensurePanLayer();

    if (!layer) return;

    layer.dataset.mmPanX = String(x);
    layer.dataset.mmPanY = String(y);

    layer.setAttribute(
      "transform",
      `translate(${x} ${y})`,
    );
  };

  /**
   * Convert browser pointer coordinates into real SVG coordinates.
   *
   * This is much more accurate than:
   *
   * viewBox.width / rect.width
   *
   * and works properly in:
   * - fullscreen
   * - responsive layouts
   * - different aspect ratios
   * - browser zoom
   */
  const clientPointToSvg = (
    svg,
    clientX,
    clientY,
  ) => {
    const matrix = svg.getScreenCTM();

    if (!matrix) {
      return null;
    }

    const point = new DOMPoint(
      clientX,
      clientY,
    );

    return point.matrixTransform(
      matrix.inverse(),
    );
  };

  const isInteractiveGraphElement = (
    target,
  ) => {
    if (!(target instanceof Element)) {
      return false;
    }

    return Boolean(
      target.closest(
        [
          "[data-mmbucket]",
          "[data-mmfeat]",
          ".mm-hub-back",
          "[data-mmfilter]",
          "[data-mmmode]",
          ".mm-node",
          "button",
          "a",
          "input",
          "select",
          "textarea",
        ].join(","),
      ),
    );
  };

  /**
   * ------------------------------------------------------
   * WHEEL ZOOM
   * ------------------------------------------------------
   *
   * Continue using your existing + / - buttons.
   * That means MM_K inside your controller stays synchronized.
   */
  const handleWheel = (event) => {
    if (!getZoomGroup()) return;

    event.preventDefault();

    if (Math.abs(event.deltaY) < 1) {
      return;
    }

    const now = performance.now();

    if (
      now -
        lastWheelZoomRef.current <
      40
    ) {
      return;
    }

    lastWheelZoomRef.current = now;

    const button =
      event.deltaY < 0
        ? document.getElementById(
            "mm-zoom-in",
          )
        : document.getElementById(
            "mm-zoom-out",
          );

    button?.click();
  };

  /**
   * ------------------------------------------------------
   * START DRAG
   * ------------------------------------------------------
   */
  const handlePointerDown = (event) => {
    if (
      event.pointerType === "mouse" &&
      event.button !== 0
    ) {
      return;
    }

    /**
     * Nodes must remain clickable.
     * Pan starts only from empty graph area.
     */
    if (
      isInteractiveGraphElement(
        event.target,
      )
    ) {
      return;
    }

    const svg = getSvg();

    if (!svg || !getZoomGroup()) {
      return;
    }

    const startPoint =
      clientPointToSvg(
        svg,
        event.clientX,
        event.clientY,
      );

    if (!startPoint) return;

    const currentPan = getPan();

    dragStateRef.current = {
      active: true,
      moved: false,
      captured: false,

      pointerId: event.pointerId,

      startSvgX: startPoint.x,
      startSvgY: startPoint.y,

      startPanX: currentPan.x,
      startPanY: currentPan.y,
    };

    suppressClickRef.current = false;
  };

  /**
   * ------------------------------------------------------
   * PAN
   * ------------------------------------------------------
   */
  const handlePointerMove = (event) => {
    const drag =
      dragStateRef.current;

    if (
      !drag.active ||
      drag.pointerId !== event.pointerId
    ) {
      return;
    }

    const svg = getSvg();

    if (!svg) return;

    const currentPoint =
      clientPointToSvg(
        svg,
        event.clientX,
        event.clientY,
      );

    if (!currentPoint) return;

    const deltaX =
      currentPoint.x - drag.startSvgX;

    const deltaY =
      currentPoint.y - drag.startSvgY;

    /**
     * Use screen distance only for detecting
     * whether this is actually a drag.
     */
    const screenDistance = Math.hypot(
      event.clientX -
        (drag.startClientX ??
          event.clientX),
      event.clientY -
        (drag.startClientY ??
          event.clientY),
    );

    /**
     * SVG distance fallback.
     */
    const svgDistance = Math.hypot(
      deltaX,
      deltaY,
    );

    if (
      !drag.moved &&
      screenDistance < 4 &&
      svgDistance < 4
    ) {
      return;
    }

    if (!drag.moved) {
      drag.moved = true;

      suppressClickRef.current = true;

      setIsDragging(true);

      try {
        stage.setPointerCapture(
          event.pointerId,
        );

        drag.captured = true;
      } catch {
        drag.captured = false;
      }
    }

    event.preventDefault();

    /**
     * No restrictive "center clamp".
     *
     * Previously:
     *
     * maxY = viewBox.height * 0.55
     *
     * prevented you from pulling the graph
     * where you wanted.
     *
     * We still keep a generous safety boundary
     * so it cannot disappear infinitely far away.
     */
    const viewBox =
      svg.viewBox?.baseVal;

    let nextX =
      drag.startPanX + deltaX;

    let nextY =
      drag.startPanY + deltaY;

    if (viewBox?.width && viewBox?.height) {
      const maxX =
        viewBox.width * 1.5;

      const maxY =
        viewBox.height * 1.5;

      nextX = Math.max(
        -maxX,
        Math.min(maxX, nextX),
      );

      nextY = Math.max(
        -maxY,
        Math.min(maxY, nextY),
      );
    }

    setPan(nextX, nextY);
  };

  /**
   * ------------------------------------------------------
   * END DRAG
   * ------------------------------------------------------
   */
  const stopDragging = (event) => {
    const drag =
      dragStateRef.current;

    if (!drag.active) return;

    if (
      event?.pointerId != null &&
      drag.pointerId !== event.pointerId
    ) {
      return;
    }

    if (drag.captured) {
      try {
        if (
          stage.hasPointerCapture?.(
            event.pointerId,
          )
        ) {
          stage.releasePointerCapture(
            event.pointerId,
          );
        }
      } catch {
        // Safe fallback.
      }
    }

    drag.active = false;
    drag.captured = false;

    setIsDragging(false);
  };

  /**
   * Prevent only the click generated after dragging.
   *
   * Normal branch/node clicks still work.
   */
  const handleClickCapture = (event) => {
    if (!suppressClickRef.current) {
      return;
    }

    if (
      isInteractiveGraphElement(
        event.target,
      )
    ) {
      suppressClickRef.current = false;
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    suppressClickRef.current = false;
  };

  stage.addEventListener(
    "wheel",
    handleWheel,
    {
      passive: false,
    },
  );

  stage.addEventListener(
    "pointerdown",
    handlePointerDown,
  );

  stage.addEventListener(
    "pointermove",
    handlePointerMove,
  );

  stage.addEventListener(
    "pointerup",
    stopDragging,
  );

  stage.addEventListener(
    "pointercancel",
    stopDragging,
  );

  stage.addEventListener(
    "lostpointercapture",
    stopDragging,
  );

  stage.addEventListener(
    "click",
    handleClickCapture,
    true,
  );

  return () => {
    stage.removeEventListener(
      "wheel",
      handleWheel,
    );

    stage.removeEventListener(
      "pointerdown",
      handlePointerDown,
    );

    stage.removeEventListener(
      "pointermove",
      handlePointerMove,
    );

    stage.removeEventListener(
      "pointerup",
      stopDragging,
    );

    stage.removeEventListener(
      "pointercancel",
      stopDragging,
    );

    stage.removeEventListener(
      "lostpointercapture",
      stopDragging,
    );

    stage.removeEventListener(
      "click",
      handleClickCapture,
      true,
    );
  };
}, []);

  /**
   * The existing mm-reset controller completely re-renders the graph,
   * which naturally removes our custom pan transform.
   *
   * Reset the local interaction state as well.
   */
const handleResetInteraction = () => {
  setIsDragging(false);

  dragStateRef.current = {
    active: false,
    moved: false,
    captured: false,

    pointerId: null,

    startClientX: 0,
    startClientY: 0,

    startSvgX: 0,
    startSvgY: 0,

    startPanX: 0,
    startPanY: 0,
  };

  suppressClickRef.current = false;

  /**
   * Existing controller will rerender/reset zoom.
   *
   * If the current pan layer still exists before that
   * rerender happens, reset it immediately as well.
   */
  const stage = graphStageRef.current;

  const panLayer = stage?.querySelector(
    '[data-mm-pan-layer="true"]',
  );

  if (panLayer) {
    panLayer.dataset.mmPanX = "0";
    panLayer.dataset.mmPanY = "0";

    panLayer.setAttribute(
      "transform",
      "translate(0 0)",
    );
  }
};

  return (
    <section id="view-mindmap" className="view" hidden>
      <div className="mindmap-shell">
        <div className="mindmap-hero">
          <div className="mindmap-toolbar">
            <div>
              <h2>Implementation coverage map</h2>

              <div className="sub">
                Review how much of each feature is actually implemented in code.
                wardenIQ reads the selected repositories, compares
                implementation paths against active test cases, and classifies
                each area as covered, partial, or uncovered.
              </div>

              <div className="view-explainer">
                Answers <b>“does the code actually build this test case?”</b> —{" "}
                <i>not</i> whether an automated test exists, and <i>not</i> what
                recent commits touched (that’s <b>Change impact analysis</b>).
              </div>
            </div>

            <div className="mindmap-hero-actions">
              <button
                type="button"
                className="ghost mindmap-refresh-btn"
                id="mm-refresh"
                onClick={() => mm.refresh()}
              >
                <span className="icon">↻</span>
                <span>Refresh</span>
              </button>
            </div>
          </div>

          <div className="mindmap-controls">
            <div className="mindmap-control-project">
              <label>Project</label>
              <select id="mm-proj" value={mm.pid} onChange={(e) => mm.changeProject(e.target.value)}>
                {mm.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {`${p.name} — ${p.repo_count} repos · ${p.feature_count} features`}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="go mindmap-primary-btn"
              id="mm-analyze"
              disabled={mm.analyzing}
              aria-busy={mm.analyzing ? "true" : undefined}
              onClick={mm.analyze}
            >
              Analyze codebase
            </button>
          </div>

          <label style={{ marginTop: "8px" }}>
            Repos &amp; branches{" "}
            <span className="muted" style={{ fontWeight: "400" }}>
              — uncheck any to exclude; set a branch per repo (blank = its
              default). Infra repos start unchecked — tick them to include.
            </span>
          </label>

          <div
            id="mm-repos"
            className="mindmap-panel"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <RepoRows repos={mm.repos} onChange={mm.updateRepo} />
          </div>

          <button
            type="button"
            className="ghost"
            id="mm-add-git"
            onClick={mm.openPicker}
            style={{
              marginTop: "8px",
              padding: "5px 12px",
              alignSelf: "flex-start",
            }}
          >
            + Add a repo from GitHub
          </button>

          <div
            className="muted"
            id="mm-status"
            style={{ marginTop: "8px" }}
          >
            <AnalysisStatus status={mm.status} />
          </div>
        </div>

        <div id="mm-diag">
          <IndexedCodeDiag key={mm.diag.key} perRepo={mm.diag.rows} />
        </div>

        <div
          ref={graphCardRef}
          className="card mm-graph-card"
          id="mm-graph-card"
          style={
            isFullscreen
              ? {
                  width: "100vw",
                  height: "100vh",
                  margin: 0,
                  borderRadius: 0,
                  overflow: "auto",
                  background: "var(--bg, #0b1118)",
                }
              : undefined
          }
        >
          <div className="mm-graph-head">
            <div>
              <h3
                style={{
                  margin: "0",
                  fontSize: "14px",
                }}
              >
                Implementation coverage
              </h3>

              <div className="sub" style={{ margin: "2px 0 0" }}>
                For every test case, an external-reviewer pass judges whether
                the production code visibly implements that behaviour — and
                cites the file that proves it. Click any branch to expand it.
              </div>
            </div>
          </div>

          <div className="mm-summary" id="mm-summary"></div>

          <div className="mm-stage-wrap">
            <div className="mm-stage-bar">
              <div className="mm-legend" id="mm-legend"></div>

              <div className="mm-stage-tools">
                <span className="mm-crumb" id="mm-crumb"></span>

                <button
                  type="button"
                  className="ghost mm-tool"
                  id="mm-zoom-out"
                  title="Zoom out"
                  aria-label="Zoom out"
                >
                  −
                </button>

                <button
                  type="button"
                  className="ghost mm-tool"
                  id="mm-zoom-in"
                  title="Zoom in"
                  aria-label="Zoom in"
                >
                  +
                </button>

                <button
                  type="button"
                  className="ghost mm-tool"
                  id="mm-reset"
                  title="Reset map position and zoom"
                  onClick={handleResetInteraction}
                >
                  Reset
                </button>

                <button
                  type="button"
                  className="ghost mm-tool"
                  id="mm-fullscreen"
                  title={isFullscreen ? "Exit fullscreen" : "Open fullscreen"}
                  aria-label={
                    isFullscreen ? "Exit fullscreen" : "Open fullscreen"
                  }
                  aria-pressed={isFullscreen}
                  onClick={handleFullscreen}
                >
                  {isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
                </button>
              </div>
            </div>

            <div
              ref={graphStageRef}
              id="mm-graph"
              className={`mm-stage ${isDragging ? "is-grabbing" : ""}`}
              aria-label="Implementation coverage graph. Scroll to zoom, drag empty space to move, and click a branch to open."
              title="Scroll to zoom • Drag empty space to move • Click a branch to open"
              style={{
                cursor: isDragging ? "grabbing" : "grab",
                userSelect: "none",
                touchAction: "none",

                ...(isFullscreen
                  ? {
                      maxHeight: "calc(100vh - 155px)",
                      minHeight: "calc(100vh - 155px)",
                    }
                  : {}),
              }}
            ></div>
          </div>

          <div id="mm-detail" className="mm-detail"></div>

          <div className="mm-graph-tip" id="mm-graph-tip" hidden></div>
        </div>

        <div id="mm-map">
          <CoverageList map={mm.map} />
        </div>
        {mm.picker ? (
          <GitRepoPicker repos={mm.picker.repos} onCancel={mm.closePicker} onAdd={mm.addPicked} />
        ) : null}
      </div>
    </section>
  );
}
