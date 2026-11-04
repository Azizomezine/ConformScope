"use client";

import { memo, useCallback, useEffect, useId, useRef, useState } from "react";
import PlanToolbar, { Tool, ZOOM_MAX, ZOOM_MIN } from "@/components/PlanToolbar";
import {
  centreOf, doorSides, roomLabel, sheetImageUrl, typeLabel, REQUIRED_DIAMETER_M,
  type Door, type Fixture, type PlanReading, type Pt, type Room, type WalkStep,
} from "@/lib/plan";
import {
  labelsFor, MIN_POINTS, MeasureKind, Measurement, POINTS_TO_CLOSE, constrain, dist,
  outline, reading as readingOf,
} from "@/lib/measure";
import {
  SPRING_MOMENTUM, SPRING_UI, clamp, projectMomentum, rubberClamp, settled, stepSpring,
} from "@/lib/spring";
import { usePreferences } from "@/app/preferences";

/** How far a press must travel before it is a pan rather than a click. */
const DRAG_SLOP_PX = 4;

/** How close, on screen, a click must land to the first point to close an area or a
 *  perimeter on it. */
const CLOSE_PX = 8;

const ASSUMED_SCALE_REASON = "view.assumedRef" as const;
const ASSUMED_SCALE_MEASURE = "view.assumedMeasure" as const;
const UNREAD_SHEET_MEASURE = "view.unreadMeasure" as const;

const isMeasure = (t: Tool): t is MeasureKind => t !== "select" && t !== "pan";

/** What the walk has shown so far (issue #14): where the icon is, the rooms it has
 *  reached and the stops it has met. */
export type WalkFrame = { icon: Pt | null; reached: Set<number | null>; stops: WalkStep[] };

/**
 * The drawing (ported from pmr-checker).
 *
 * The SVG viewBox IS the sheet's image, so the polygons, doorways and circles the API
 * sends (all in plan pixels) are drawn with no coordinate conversion at all. Pan and
 * zoom are one transform on the viewBox; nothing else knows about them.
 */
export default function PlanViewer({
  sheet, reading, active, onPick, correcting = false, onPoint, pending = null,
  walk = null, toolbarExtra,
}: {
  sheet: { id: string; page: number; width: number; height: number };
  /** Null for a bare sheet — one not checked yet, or a plan annexe: nothing on it
   *  rests on a scale, so no scale bar and no reference circle claim one. */
  reading: PlanReading | null;
  active: number | null;
  onPick: (room: number | null) => void;
  /** A correction is armed: the next click, on paper or over a room, is its point. */
  correcting?: boolean;
  onPoint?: (pt: Pt) => void;
  /** The correction's first point, placed and waiting for the second. */
  pending?: Pt | null;
  walk?: WalkFrame | null;
  toolbarExtra?: React.ReactNode;
}) {
  const x0 = 0, y0 = 0, x1 = sheet.width, y1 = sheet.height;
  type View = { x: number; y: number; k: number };
  const [view, setView] = useState<View>({ x: x0, y: y0, k: 1 });
  // px/py is the last point seen (the pan delta); ox/oy the point pressed (the slop
  // test). `moving` says what the press is dragging: the sheet, or the reference circle.
  // rawX/rawY is the un-resisted pan position; hist is a short pointer history
  // kept only to read release velocity from (velocity handoff).
  const drag = useRef<{
    px: number; py: number; ox: number; oy: number;
    panning: boolean; moving: "sheet" | "reference";
    rawX: number; rawY: number; hist: { t: number; x: number; y: number }[];
  } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  /* ── Spring-driven view (Apple: animate from the presentation value, carry
     velocity through re-targets, never lock input). `view` is the displayed
     value; an in-flight spring can be grabbed or re-aimed at any instant. */
  const viewRef = useRef<View>({ x: x0, y: y0, k: 1 });
  const applyView = (v: View) => { viewRef.current = v; setView(v); };
  const anim = useRef<{
    target: View; vx: number; vy: number; vlk: number; last: number;
    damping: number; response: number;
  } | null>(null);
  const animRaf = useRef(0);

  const boundsFor = (k: number) => {
    const w = (x1 - x0) / k, h = (y1 - y0) / k;
    return { w, h, minX: x0, maxX: x1 - w, minY: y0, maxY: y1 - h };
  };
  const clampView = (v: View): View => {
    const b = boundsFor(v.k);
    return { ...v, x: clamp(v.x, b.minX, b.maxX), y: clamp(v.y, b.minY, b.maxY) };
  };
  const rubberView = (v: View): View => {
    const b = boundsFor(v.k);
    return { ...v, x: rubberClamp(v.x, b.minX, b.maxX, b.w), y: rubberClamp(v.y, b.minY, b.maxY, b.h) };
  };

  function stopSpring() {
    cancelAnimationFrame(animRaf.current);
    anim.current = null;
  }

  function springTo(target: View, opts: {
    vx?: number; vy?: number; vlk?: number; damping?: number; response?: number;
  } = {}) {
    if (typeof window !== "undefined"
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      stopSpring(); applyView(clampView(target)); return;
    }
    const prev = anim.current;
    anim.current = {
      target: clampView(target),
      // Re-targeting keeps the in-flight velocity unless a gesture hands one over.
      vx: opts.vx ?? prev?.vx ?? 0, vy: opts.vy ?? prev?.vy ?? 0, vlk: opts.vlk ?? prev?.vlk ?? 0,
      last: performance.now(),
      damping: opts.damping ?? SPRING_UI.damping, response: opts.response ?? SPRING_UI.response,
    };
    if (prev) return; // the running loop picks the new target up
    const tick = (now: number) => {
      const a = anim.current;
      if (!a) return;
      const dt = Math.min(0.05, Math.max(0.001, (now - a.last) / 1000));
      a.last = now;
      const cur = viewRef.current;
      const sx = stepSpring({ x: cur.x, v: a.vx }, a.target.x, dt, a.damping, a.response);
      const sy = stepSpring({ x: cur.y, v: a.vy }, a.target.y, dt, a.damping, a.response);
      const sk = stepSpring({ x: Math.log(cur.k), v: a.vlk }, Math.log(a.target.k), dt, a.damping, a.response);
      a.vx = sx.v; a.vy = sy.v; a.vlk = sk.v;
      const next: View = { x: sx.x, y: sy.x, k: Math.exp(sk.x) };
      if (settled(sx, a.target.x, 0.5) && settled(sy, a.target.y, 0.5) && settled(sk, Math.log(a.target.k), 0.001)) {
        anim.current = null; applyView(a.target); return;
      }
      applyView(next);
      animRaf.current = requestAnimationFrame(tick);
    };
    animRaf.current = requestAnimationFrame(tick);
  }

  useEffect(() => () => cancelAnimationFrame(animRaf.current), []);
  // Whether the last press ended as a pan: the click that follows lands on bare paper
  // and must not be read as the auditor pointing there.
  const panned = useRef(false);

  // The reference circle. Held here and nowhere else: it is never saved.
  const [reference, setReference] = useState<Pt | null>(null);
  const refusedId = useId();

  const [tool, setTool] = useState<Tool>("select");
  const [bare, setBare] = useState(false);
  const [measures, setMeasures] = useState<Measurement[]>([]);
  const [draftPts, setDraftPts] = useState<Pt[]>([]);
  const [hover, setHover] = useState<Pt | null>(null);
  const nextMeasureId = useRef(1);

  // The svg's size on screen, for the scale bar: two metres drawn at the current zoom.
  const [box, setBox] = useState<[number, number] | null>(null);
  useEffect(() => {
    const el = svg.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (r.width && r.height) setBox([r.width, r.height]);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const { locale, t } = usePreferences();
  const LABELS = labelsFor(locale);
  const metre = reading?.px_per_m ?? null;
  const measured = metre !== null && !!reading?.checked;
  // Its one claim is its size. On an assumed scale that claim is a guess, and the eye
  // trusts a drawn circle — so it is refused rather than shown dashed.
  const referenceTrusted = measured && reading?.scale_source !== "assumed";
  const measureRefusal = !measured ? t(UNREAD_SHEET_MEASURE)
    : !referenceTrusted ? t(ASSUMED_SCALE_MEASURE) : null;

  // React's onWheel is passive, so it cannot preventDefault — the wheel would leak
  // through to the browser's own page zoom. Bind it natively instead.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      // Aim at the in-flight target, so repeated wheel ticks accumulate instead
      // of each restarting from a stale frame — and the spring stays interruptible.
      const base = anim.current?.target ?? viewRef.current;
      const perPx = Math.max((x1 - x0) / r.width, (y1 - y0) / r.height) / base.k;
      const w = (x1 - x0) / base.k, h = (y1 - y0) / base.k;
      // Zoom about the cursor: the point under the pointer stays put.
      const mx = base.x + w / 2 + (e.clientX - r.left - r.width / 2) * perPx;
      const my = base.y + h / 2 + (e.clientY - r.top - r.height / 2) * perPx;
      const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, base.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      springTo({
        k,
        x: mx - ((mx - base.x) / w) * ((x1 - x0) / k),
        y: my - ((my - base.y) / h) * ((y1 - y0) / k),
      }, { response: 0.28 });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // springTo only touches refs and setState, so the first closure stays correct.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [x0, y0, x1, y1]);

  // One factor for both axes: the svg letterboxes the sheet (`meet`), so it is fitted
  // by whichever axis is tighter and the other gets margins.
  const ptPerPx = (r: DOMRect) => Math.max((x1 - x0) / r.width, (y1 - y0) / r.height) / view.k;

  function onPointerDown(e: React.PointerEvent) {
    panned.current = false;
    // Grabbing mid-flight starts from the presentation (on-screen) value.
    stopSpring();
    const onReference = (e.target as Element).closest?.(".reference-circle") != null;
    drag.current = {
      px: e.clientX, py: e.clientY, ox: e.clientX, oy: e.clientY, panning: false,
      moving: onReference ? "reference" : "sheet",
      rawX: viewRef.current.x, rawY: viewRef.current.y,
      hist: [{ t: performance.now(), x: e.clientX, y: e.clientY }],
    };
    // Not capturing the pointer here: capture retargets the click to this <svg>, and a
    // room's own handler would never run. Capture is taken once the press is a drag.
  }

  function onPointerMove(e: React.PointerEvent) {
    if (isMeasure(tool) && draftPts.length > 0 && !drag.current?.panning) {
      setHover(snapped(e, pagePoint(e)));
    }
    const d = drag.current;
    if (!d || !svg.current) return;
    d.hist.push({ t: performance.now(), x: e.clientX, y: e.clientY });
    if (d.hist.length > 8) d.hist.shift();
    if (!d.panning) {
      if (Math.hypot(e.clientX - d.ox, e.clientY - d.oy) < DRAG_SLOP_PX) return;
      d.panning = true;
      svg.current.setPointerCapture?.(e.pointerId);
    }
    const perPx = ptPerPx(svg.current.getBoundingClientRect());
    const dx = (e.clientX - d.px) * perPx;
    const dy = (e.clientY - d.py) * perPx;
    d.px = e.clientX;
    d.py = e.clientY;
    if (d.moving === "reference") setReference((c) => c && [c[0] + dx, c[1] + dy]);
    else {
      // 1:1 with the pointer, resisted past the sheet's edges (rubber-banding).
      d.rawX -= dx; d.rawY -= dy;
      applyView(rubberView({ ...viewRef.current, x: d.rawX, y: d.rawY }));
    }
  }

  function release(e: React.PointerEvent) {
    const d = drag.current;
    if (d?.panning && svg.current?.hasPointerCapture?.(e.pointerId)) {
      svg.current.releasePointerCapture(e.pointerId);
    }
    panned.current = d?.panning ?? panned.current;
    drag.current = null;
    // Velocity handoff + momentum projection: continue at the finger's exact
    // velocity, land where the flick was going, then spring to the nearest
    // in-bounds resting place (which also snaps a rubber-banded edge back).
    if (d?.panning && d.moving === "sheet" && svg.current) {
      const now = performance.now();
      const first = d.hist.find((p) => now - p.t <= 120) ?? d.hist[0];
      const last = d.hist[d.hist.length - 1];
      const dt = first && last ? (last.t - first.t) / 1000 : 0;
      const perPx = ptPerPx(svg.current.getBoundingClientRect());
      const fresh = last && now - last.t <= 80;
      const vx = fresh && dt > 0.02 ? -((last.x - first.x) / dt) * perPx : 0;
      const vy = fresh && dt > 0.02 ? -((last.y - first.y) / dt) * perPx : 0;
      const cur = viewRef.current;
      if (Math.hypot(vx, vy) > 40) {
        springTo(
          { ...cur, x: cur.x + projectMomentum(vx), y: cur.y + projectMomentum(vy) },
          { vx, vy, damping: SPRING_MOMENTUM.damping, response: SPRING_MOMENTUM.response },
        );
      } else {
        springTo(cur, { vx: 0, vy: 0 });
      }
    }
  }

  const w = (x1 - x0) / view.k;
  const h = (y1 - y0) / view.k;

  /** The plan point under a click, or null in the letterbox margin. */
  function pagePoint(e: React.MouseEvent): Pt | null {
    if (!svg.current) return null;
    const r = svg.current.getBoundingClientRect();
    const perPx = ptPerPx(r);
    const x = view.x + w / 2 + (e.clientX - r.left - r.width / 2) * perPx;
    const y = view.y + h / 2 + (e.clientY - r.top - r.height / 2) * perPx;
    return x < x0 || x > x1 || y < y0 || y > y1 ? null : [x, y];
  }

  /** A click that reached the paper. A room has already had it; the click that ends a
   *  pan is not a point at all. While a correction is armed, a click over a room is its
   *  point too, and the room is not opened. */
  function onPaperClick(e: React.MouseEvent) {
    if (panned.current) { panned.current = false; return; }
    if (tool === "pan") return;
    if ((e.target as Element).closest?.(".reference-circle")) return;
    if (isMeasure(tool)) {
      // The second click of a double-click closes the measurement; it is no point.
      if (e.detail >= 2) { finishDraft(); return; }
      const pt = snapped(e, pagePoint(e));
      if (pt) addPoint(tool, pt);
      return;
    }
    if (correcting) {
      const pt = pagePoint(e);
      if (pt) onPoint?.(pt);
      return;
    }
    if (!(e.target as Element).closest?.(".room")) onPick(null);
  }

  /** Shift held: square to the last point placed, as with a set square. */
  function snapped(e: React.MouseEvent, pt: Pt | null): Pt | null {
    const last = draftPts[draftPts.length - 1];
    return pt && last && e.shiftKey ? constrain(last, pt) : pt;
  }

  function addPoint(kind: MeasureKind, pt: Pt) {
    if ((kind === "area" || kind === "perimeter") && draftPts.length >= MIN_POINTS[kind]
        && svg.current && dist(pt, draftPts[0]) / ptPerPx(svg.current.getBoundingClientRect()) < CLOSE_PX) {
      finishDraft(kind === "perimeter" ? [...draftPts, draftPts[0]] : draftPts, kind);
      return;
    }
    const next = [...draftPts, pt];
    if (POINTS_TO_CLOSE[kind] === next.length) finishDraft(next, kind);
    else setDraftPts(next);
  }

  /** Keep the measurement being taken, if it means anything yet, and start afresh. */
  function finishDraft(pts: Pt[] = draftPts, kind: Tool = tool) {
    if (isMeasure(kind) && pts.length >= MIN_POINTS[kind]) {
      const id = nextMeasureId.current++;
      setMeasures((ms) => [...ms, { id, kind, pts }]);
    }
    setDraftPts([]);
    setHover(null);
  }

  function chooseTool(t: Tool) {
    finishDraft();
    setTool(t);
  }

  // Enter closes the measurement, Escape drops it (or puts the tool down), and
  // Backspace takes back the last point placed.
  useEffect(() => {
    if (!isMeasure(tool)) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest?.("input, textarea, select, [contenteditable='true']")) return;
      if (e.key === "Enter") { e.preventDefault(); finishDraft(); }
      else if (e.key === "Escape") {
        if (draftPts.length) { setDraftPts([]); setHover(null); } else setTool("select");
      } else if (e.key === "Backspace" && draftPts.length) {
        e.preventDefault();
        setDraftPts((p) => p.slice(0, -1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- finishDraft reads only draftPts/tool, both deps
  }, [tool, draftPts]);

  /** Zoom from the toolbar: about the centre of the view, not a cursor. Springs
   *  from the current value and keeps any in-flight velocity. */
  function zoomTo(k: number) {
    const base = anim.current?.target ?? viewRef.current;
    const cx = base.x + (x1 - x0) / base.k / 2, cy = base.y + (y1 - y0) / base.k / 2;
    springTo({ k, x: cx - (x1 - x0) / k / 2, y: cy - (y1 - y0) / k / 2 }, { response: 0.32 });
  }

  function toggleReference() {
    if (!referenceTrusted) return;
    setReference((c) => (c ? null : [view.x + w / 2, view.y + h / 2]));
  }

  // Stable across walk-animation frames (the parent re-renders at 60fps while
  // the wheelchair rolls): the memoised shapes below can then skip re-render.
  const pickRoom = useCallback((i: number) => {
    if (!correcting && tool === "select") onPick(active === i ? null : i);
  }, [correcting, tool, onPick, active]);

  const rooms = reading?.rooms ?? [];
  // Struck in plan order, left to right, the way an auditor works across a sheet.
  const order = new Map(
    rooms.map((r, i) => [i, centreOf(r)[0]] as const)
      .filter(([i]) => rooms[i].conforme !== null)
      .sort((a, b) => a[1] - b[1])
      .map(([i], n) => [i, n]),
  );

  // Marks drawn at one screen size whatever the zoom, sized off the sheet rather than
  // the scale: a count needs no scale, and a bare sheet has none.
  const unit = Math.max(x1 - x0, y1 - y0) / 200;
  const draft = isMeasure(tool) && draftPts.length > 0
    ? { kind: tool, pts: hover ? [...draftPts, hover] : draftPts }
    : null;
  const at = (pt: Pt) => `translate(${pt[0]} ${pt[1]}) scale(${1 / view.k})`;
  const pts = (polygon: Pt[]) => polygon.map(([x, y]) => `${x},${y}`).join(" ");

  return (
    <div className={`drawing${correcting ? " correcting" : ""}${isMeasure(tool) ? " measuring" : ""}${tool === "pan" ? " panning" : ""}${bare ? " bare" : ""}`}>
      <svg
        ref={svg}
        viewBox={`${view.x} ${view.y} ${w} ${h}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={release}
        onPointerCancel={release}
        onPointerLeave={release}
        onClick={onPaperClick}
      >
        <image href={sheetImageUrl(sheet.id, sheet.page)} x={x0} y={y0} width={x1 - x0} height={y1 - y0} />

        {rooms.map((room, i) => (
          <MemoRoomShape key={i} room={room} index={i} metre={metre} unit={unit} k={view.k}
                     active={active === i} strikeIndex={order.get(i) ?? 0}
                     onPick={pickRoom} />
        ))}

        <g className="fixtures">
          {(reading?.fixtures ?? []).map((fixture, i) => (
            <MemoFixtureShape key={i} fixture={fixture} />
          ))}
        </g>

        <g className="doors">
          {(reading?.doors ?? []).map((door, i) => (
            <MemoDoorShape key={i} door={door} rooms={rooms} />
          ))}
        </g>

        {walk && (
          <g className="walk">
            {rooms.map((room, i) => walk.reached.has(i) ? (
              <polygon key={`reached-${i}`} className="reached" points={pts(room.polygon_px)} />
            ) : null)}
            {walk.stops.map((step, i) => (
              <g key={`stop-${i}`} className="stop" transform={at(step.point_px)}>
                <circle r={unit * 2.2} />
                <text textAnchor="middle" dominantBaseline="central" style={{ fontSize: unit * 2.8 }}>!</text>
              </g>
            ))}
            {walk.icon && (
              <g className="wheelchair" transform={at(walk.icon)}>
                <circle r={unit * 2.6} />
                <text textAnchor="middle" dominantBaseline="central" style={{ fontSize: unit * 3 }}>♿</text>
              </g>
            )}
          </g>
        )}

        {pending && (
          <g className="pointed" transform={at(pending)}>
            <line x1={-unit * 2} x2={unit * 2} y1={0} y2={0} />
            <line x1={0} x2={0} y1={-unit * 2} y2={unit * 2} />
          </g>
        )}

        <g className="measures">
          {metre !== null && measures.map((m) => (
            <MemoCote key={m.id} m={m} k={view.k} unit={unit} metre={metre} />
          ))}
          {draft && metre !== null && <MemoCote m={draft} k={view.k} unit={unit} metre={metre} draft />}
        </g>

        {reference && metre !== null && (
          <circle cx={reference[0]} cy={reference[1]} r={(REQUIRED_DIAMETER_M / 2) * metre}
                  className="reference-circle" />
        )}
      </svg>

      {measured && metre !== null && <>
        <div className="reference" role="group" aria-label={t("view.referenceAria")}>
          {!referenceTrusted && <span id={refusedId} className="reason">{t(ASSUMED_SCALE_REASON)}</span>}
          {/* aria-disabled, not disabled: a disabled button leaves the tab order, and
              with it the only place the refusal is explained. */}
          <button type="button" aria-pressed={reference != null}
                  aria-disabled={!referenceTrusted || undefined}
                  aria-describedby={referenceTrusted ? undefined : refusedId}
                  onClick={toggleReference}>
            {t("view.reference", { size: REQUIRED_DIAMETER_M.toFixed(2) })}
          </button>
        </div>

        <div className="scalebar">
          <div className="bar" style={{
            width: box ? (metre * 2 * view.k) / Math.max((x1 - x0) / box[0], (y1 - y0) / box[1]) : 0,
          }} />
          <span>2 m</span>
        </div>
      </>}

      {(measures.length > 0 || draft) && metre !== null && (
        <section className="cotes" aria-label={t("view.measurements")}>
          <ol>
            {measures.map((m) => (
              <li key={m.id}>
                <span>{LABELS[m.kind]}</span>
                <output>{readingOf(m, metre)}</output>
                <button type="button"
                        aria-label={t("view.removeMeasure", { label: LABELS[m.kind].toLowerCase(), value: readingOf(m, metre) })}
                        onClick={() => setMeasures((ms) => ms.filter((x) => x.id !== m.id))}>×</button>
              </li>
            ))}
            {draft && (
              <li className="draft">
                <span>{LABELS[draft.kind]}</span>
                <output>{readingOf(draft, metre)}</output>
              </li>
            )}
          </ol>
        </section>
      )}

      {/* After the sheet in the document, drawn above it by the flex order (tool.css):
          the plan stays the drawing's first <svg>. */}
      <PlanToolbar
        zoom={view.k} onZoom={zoomTo} onFit={() => springTo({ x: x0, y: y0, k: 1 }, { response: 0.38 })}
        tool={tool} onTool={chooseTool}
        bare={bare} onBare={setBare}
        measureRefusal={measureRefusal}
        canUndo={measures.length > 0 || draftPts.length > 0}
        onUndo={() => {
          if (draftPts.length) { setDraftPts([]); setHover(null); }
          else setMeasures((ms) => ms.slice(0, -1));
        }}
        canClear={measures.length > 0 || draftPts.length > 0}
        onClear={() => { setMeasures([]); setDraftPts([]); setHover(null); }}
        extra={toolbarExtra}
      />
    </div>
  );
}

/** One measurement on the sheet: its outline in plan pixels, its ends and its reading
 *  at one screen size whatever the zoom. */
function Cote({ m, k, unit, metre, draft = false }: {
  m: Pick<Measurement, "kind" | "pts">; k: number; unit: number; metre: number; draft?: boolean;
}) {
  const at = (pt: Pt) => `translate(${pt[0]} ${pt[1]}) scale(${1 / k})`;
  const cls = `cote ${m.kind}${draft ? " draft" : ""}`;

  if (m.kind === "count") {
    return (
      <g className={cls}>
        {m.pts.map((pt, i) => (
          <g key={i} transform={at(pt)}>
            <circle r={unit * 1.4} />
            <text textAnchor="middle" dominantBaseline="central" style={{ fontSize: unit * 1.6 }}>{i + 1}</text>
          </g>
        ))}
      </g>
    );
  }

  const pts = outline(m);
  const closed = m.kind === "area" || m.kind === "rectangle";
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ") + (closed ? " Z" : "");
  const mean = (i: 0 | 1) => pts.reduce((s, p) => s + p[i], 0) / pts.length;
  const mid: Pt = m.kind === "perimeter" ? pts[pts.length - 1] : [mean(0), mean(1)];

  return (
    <g className={cls}>
      <path d={d} />
      {m.pts.map((pt, i) => (
        <g key={i} transform={at(pt)}><circle className="end" r={unit * 0.5} /></g>
      ))}
      {pts.length > 1 && (
        <g transform={at(mid)}>
          <text y={-unit * 1.2} textAnchor="middle" style={{ fontSize: unit * 2.4 }}>{readingOf(m, metre)}</text>
        </g>
      )}
    </g>
  );
}

function RoomShape({ room, index, metre, unit, k, active, strikeIndex, onPick }: {
  room: Room; index: number; metre: number | null; unit: number; k: number;
  active: boolean; strikeIndex: number; onPick: (index: number) => void;
}) {
  const { locale } = usePreferences();
  const verdict = room.conforme === null ? "" : room.conforme ? "conforme" : "non-conforme";
  const radius = room.circle_m !== null && metre ? (room.circle_m / 2) * metre : null;
  const circumference = radius ? 2 * Math.PI * radius : 0;
  const anchor = centreOf(room);
  const flagged = room.warnings.length > 0;

  return (
    <g className={`room${active ? " active" : ""}`} onClick={() => onPick(index)}>
      <title>{`${roomLabel(room, index, locale)} · ${typeLabel(room, locale)}${room.verdict ? ` · ${room.verdict}` : ""}`}</title>
      <polygon points={room.polygon_px.map(([x, y]) => `${x},${y}`).join(" ")}
               className={`outline ${verdict}${flagged ? " flagged" : ""}`} />
      {radius && room.circle_px && (
        <circle cx={room.circle_px[0]} cy={room.circle_px[1]} r={radius}
                className={`compass ${verdict}`}
                style={{
                  // Drawn, not faded in: the compass sweeps the circle open.
                  ["--c" as string]: circumference,
                  ["--dash" as string]: `${unit * 0.9} ${unit * 0.65}`,
                  strokeWidth: unit * 0.35,
                  animationDelay: `${strikeIndex * 90}ms, ${strikeIndex * 90 + 700}ms`,
                }} />
      )}
      {room.circle_px && <circle cx={room.circle_px[0]} cy={room.circle_px[1]} r={unit * 0.4} className="pivot" />}
      {/* Every room is numbered, checked or not: an auditor needs to point at one.
          scale(1/k) keeps the glyph one screen size at every zoom. */}
      <g className="numero" transform={`translate(${anchor[0]} ${anchor[1]}) scale(${1 / k})`}>
        <text textAnchor="middle" dominantBaseline="central" style={{ fontSize: unit * 2.6 }}>{index + 1}</text>
      </g>
    </g>
  );
}

// Memoised: PlanViewer re-renders every animation frame while the walk
// rolls or the view springs, but a room/fixture/door shape only changes
// when the reading or the zoom does. Without this, each frame re-created
// every polygon string on the sheet -- the freeze on big plans.
const MemoRoomShape = memo(RoomShape);
const MemoFixtureShape = memo(FixtureShape);
const MemoDoorShape = memo(DoorShape);
const MemoCote = memo(Cote);

function FixtureShape({ fixture }: { fixture: Fixture }) {
  const pts = (polygon: Pt[]) => polygon.map(([x, y]) => `${x},${y}`).join(" ");
  const by = fixture.outline_source === "vector" ? "" :
    ` (outlined by ${fixture.outline_source === "sam" ? "SAM 3.1" : "Muse Spark"})`;
  return (
    <g>
      <polygon className={`fixture ${fixture.kind}`} points={pts(fixture.polygon_px)}>
        <title>{`${fixture.kind}${by}`}</title>
      </polygon>
      {fixture.space && fixture.space.polygon_px.length > 0 && (
        <polygon className={`space ${fixture.space.fits ? "fits" : "fails"}${fixture.space.to_confirm ? " to-confirm" : ""}`}
                 points={pts(fixture.space.polygon_px)}>
          <title>{fixture.space.verdict}</title>
        </polygon>
      )}
    </g>
  );
}

function DoorShape({ door, rooms }: { door: Door; rooms: Room[] }) {
  const [[ax, ay], [bx, by]] = door.doorway_px;
  const status = door.proposed ? "proposed" : door.ok === null ? "unchecked" : door.ok ? "ok" : "bad";
  return (
    <line className={`door ${status}`} x1={ax} y1={ay} x2={bx} y2={by}>
      <title>{`${doorSides(door, rooms)} · ${door.verdict}`}</title>
    </line>
  );
}
