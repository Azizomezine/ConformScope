import type { Pt } from "@/lib/plan";
import { translate, type Locale } from "@/lib/i18n";

/**
 * The auditor's own dimensions, taken on the plan with the measuring tools (ported from
 * pmr-checker). Like the reference circle, a measurement is a drafting instrument: it
 * is never saved and never changes a verdict. Its points are plan pixels, so the
 * sheet's px_per_m is all it takes to turn them into metres.
 */
export type MeasureKind = "distance" | "perimeter" | "area" | "rectangle" | "count";

export interface Measurement {
  id: number;
  kind: MeasureKind;
  pts: Pt[];
}

/** How many points close each kind by themselves. The others are closed by the
 *  auditor (double-click, Enter, or a click back on the first point). */
export const POINTS_TO_CLOSE: Partial<Record<MeasureKind, number>> = {
  distance: 2,
  rectangle: 2,
};

/** The fewest points a kind needs to mean anything once closed. */
export const MIN_POINTS: Record<MeasureKind, number> = {
  distance: 2, perimeter: 2, area: 3, rectangle: 2, count: 1,
};

/** A count needs no scale: it measures nothing, it only numbers. */
export const needsScale = (kind: MeasureKind) => kind !== "count";

export const LABELS: Record<MeasureKind, string> = {
  distance: "Distance",
  perimeter: "Perimeter",
  area: "Area",
  rectangle: "Rectangle",
  count: "Count",
};

export const labelsFor = (locale: Locale): Record<MeasureKind, string> => ({
  distance: translate(locale, "measure.distance"),
  perimeter: translate(locale, "measure.perimeter"),
  area: translate(locale, "measure.area"),
  rectangle: translate(locale, "measure.rectangle"),
  count: translate(locale, "measure.count"),
});

export const dist = ([ax, ay]: Pt, [bx, by]: Pt) => Math.hypot(bx - ax, by - ay);

export function pathLength(pts: Pt[], closed = false): number {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += dist(pts[i - 1], pts[i]);
  if (closed && pts.length > 2) total += dist(pts[pts.length - 1], pts[0]);
  return total;
}

/** Shoelace. Unsigned: the auditor may click round either way. */
export function polygonArea(pts: Pt[]): number {
  let twice = 0;
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % pts.length];
    twice += ax * by - bx * ay;
  }
  return Math.abs(twice) / 2;
}

/** The four corners of the axis-aligned rectangle two opposite corners span. */
export function rectCorners([ax, ay]: Pt, [bx, by]: Pt): Pt[] {
  return [[ax, ay], [bx, ay], [bx, by], [ax, by]];
}

/** The outline a measurement draws, in plan pixels. */
export function outline(m: Pick<Measurement, "kind" | "pts">): Pt[] {
  return m.kind === "rectangle" && m.pts.length === 2 ? rectCorners(m.pts[0], m.pts[1]) : m.pts;
}

/** Holding Shift keeps a segment to the nearest multiple of 45°, the way a set square
 *  does — door widths and wall runs are taken square to the wall. */
export function constrain(from: Pt, to: Pt): Pt {
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const len = Math.hypot(dx, dy);
  const step = Math.PI / 4;
  const a = Math.round(Math.atan2(dy, dx) / step) * step;
  return [from[0] + Math.cos(a) * len, from[1] + Math.sin(a) * len];
}

/** What a measurement reads, at the sheet's scale. */
export function reading(m: Pick<Measurement, "kind" | "pts">, pxPerM: number): string {
  switch (m.kind) {
    // A perimeter is the path as walked: open, unless it was closed by a click back on
    // its first point, which repeats that point at its end.
    case "distance":
    case "perimeter":
      return `${(pathLength(m.pts) / pxPerM).toFixed(2)} m`;
    case "area":
      return `${(polygonArea(m.pts) / pxPerM ** 2).toFixed(2)} m²`;
    case "rectangle": {
      if (m.pts.length < 2) return "";
      const [[ax, ay], [bx, by]] = m.pts;
      const w = Math.abs(bx - ax) / pxPerM, h = Math.abs(by - ay) / pxPerM;
      return `${w.toFixed(2)} × ${h.toFixed(2)} m · ${(w * h).toFixed(2)} m²`;
    }
    case "count":
      return `${m.pts.length}`;
  }
}
