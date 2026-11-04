import type { Stage } from "@/lib/plan";
import { translate, type Locale } from "@/lib/i18n";

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

/** Past this, the wait is called out as longer than usual. */
const SLOW_MS = 90_000;

/** m:ss, for the clock beside the bar. */
export function clockOf(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** How long the auditor should expect to wait, so a bar that sits still does not read
 *  as stuck: the last stage (typing) is the slow one, and a long wait is said aloud. */
export function waitHintOf(stage: Stage | null, sent: number | null, elapsedMs: number, locale: Locale = "en"): string {
  if (elapsedMs > SLOW_MS) return translate(locale, "progress.slow");
  if (sent === null && stage?.stage === "typing") return translate(locale, "progress.typingHint");
  return translate(locale, "progress.expect");
}

/** What the auditor is told the bar is waiting on. */
export function labelOf(stage: Stage | null, sent: number | null, locale: Locale = "en"): string {
  if (sent !== null) return translate(locale, "progress.sending", { pct: Math.round(sent * 100) });
  if (!stage) return translate(locale, "progress.starting");
  switch (stage.stage) {
    case "reading": return translate(locale, "progress.reading");
    case "measuring": return translate(locale, "progress.measuring");
    case "typing": return translate(locale, "progress.typing");
    case "segmenting": return translate(locale, "progress.segmenting");
    case "scale": return translate(locale, "progress.scale");
    case "fixtures": return translate(locale, "progress.fixtures");
    case "outlining": return translate(locale, "progress.outlining", { batch: stage.batch ?? "", of: stage.of ?? "" });
    default: return translate(locale, "progress.working");
  }
}
