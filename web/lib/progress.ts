import type { Stage } from "@/lib/plan";

/* How the reading bar maps the stages a sheet's check streams onto its 0–100 (copied
   from pmr-checker's ADR 0021). Each stage owns a band; the bar creeps inside the band
   while the stage runs and only the next stage takes it past the band's edge, so it can
   be slow but never ahead of the work. The band edges are estimates; the boundaries
   between them are real events. */

type Band = readonly [number, number];

/** With an upload, sending the file is the bar's first stretch — the real fraction sent. */
const SENT = 8;

const BANDS: Record<string, Band> = {
  reading: [SENT, 38],      // Muse Spark reads the names and the scale
  measuring: [38, 72],      // vector walls, doors and fixtures
  segmenting: [38, 56],     // SAM 3.1 outlines the rooms of a picture
  scale: [56, 62],
  fixtures: [62, 68],
  outlining: [68, 92],      // SAM 3.1, batch by batch
  typing: [72, 97],         // Muse Spark types the rooms left unnamed
};

/** The band the bar may move in, for the stage the check has reached. A batch of
 *  outlines owns its own share of the outlining band. */
export function bandOf(stage: Stage | null, uploaded: boolean): Band {
  const start = uploaded ? SENT : 0;
  if (!stage) return [start, start + 4];
  if (stage.stage === "outlining" && stage.batch && stage.of) {
    const [lo, hi] = BANDS.outlining;
    const step = (hi - lo) / stage.of;
    return [lo + step * (stage.batch - 1), lo + step * stage.batch];
  }
  return BANDS[stage.stage] ?? [start, 97];
}

/** Where the bar stands while the file is still being sent. */
export const sendingAt = (fraction: number) => SENT * fraction;

/** One step of the creep, a sixtieth of the way to the band's ceiling: the bar stops a
 *  whole percent short of it, so even rounded it never shows the next stage begun.
 *  Never backwards: a stage that starts behind where the bar stands leaves it there. */
export function crept(at: number, [lo, hi]: Band): number {
  const from = Math.max(at, lo);
  return hi - from <= 1 ? from : from + (hi - from) / 60;
}

/** What the auditor is told the bar is waiting on. */
export function labelOf(stage: Stage | null, sent: number | null): string {
  if (sent !== null) return `Sending the plan — ${Math.round(sent * 100)}%`;
  if (!stage) return "Starting…";
  switch (stage.stage) {
    case "reading": return "Muse Spark is reading the plan…";
    case "measuring": return "Measuring the rooms against the drawn walls…";
    case "typing": return "Muse Spark is typing the unnamed rooms…";
    case "segmenting": return "SAM 3.1 is outlining the rooms…";
    case "scale": return "Muse Spark is reading a dimension for the scale…";
    case "fixtures": return "Muse Spark is finding the fixtures…";
    case "outlining": return `SAM 3.1 is outlining the fixtures — batch ${stage.batch}/${stage.of}`;
    default: return "Working…";
  }
}
