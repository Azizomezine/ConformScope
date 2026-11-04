import type { I18nKey } from "@/lib/i18n";
import type { PlanReading, Walk } from "@/lib/plan";

/**
 * The rules ConformScope checks, one list for the landing page and the report.
 * Values are the ones the checker measures against (turning.py, doors.py,
 * spaces.py); the source is the French housing accessibility arrêté. The
 * washbasin space's article is still to confirm (CONTEXT.md), and says so.
 */
export type RuleId = "turning" | "doors" | "transfer" | "washbasin" | "walk";

export type Rule = {
  id: RuleId;
  value: string;
  name: I18nKey;
  text: I18nKey;
  source: I18nKey;
};

export const RULES: Rule[] = [
  { id: "turning", value: "Ø 1.50 m", name: "rule.turning.name", text: "rule.turning.text", source: "rule.src.arrete" },
  { id: "doors", value: "0.80 / 0.90 m", name: "rule.doors.name", text: "rule.doors.text", source: "rule.src.arrete" },
  { id: "transfer", value: "0.80 × 1.30 m", name: "rule.transfer.name", text: "rule.transfer.text", source: "rule.src.arrete" },
  { id: "washbasin", value: "0.80 × 1.30 m", name: "rule.washbasin.name", text: "rule.washbasin.text", source: "rule.src.confirm" },
  { id: "walk", value: "door → room", name: "rule.walk.name", text: "rule.walk.text", source: "rule.src.walk" },
];

/** On the roadmap, never shown as checked. */
export const NEXT_RULES: I18nKey[] = ["next.manoeuvre", "next.corridor", "next.threshold", "next.fire"];

export type RuleScore = { rule: Rule; passed: number; total: number };

/** How each rule did on one sheet; a rule with nothing to judge has total 0. */
export function scoreRules(reading: PlanReading, walk: Walk | null): RuleScore[] {
  const rooms = reading.rooms.filter((r) => r.conforme !== null);
  const doors = (reading.doors ?? []).filter((d) => d.ok !== null);
  const spaces = (reading.fixtures ?? []).map((f) => f.space).filter((s) => s !== null);
  const of = (kind: "transfer" | "washbasin") => spaces.filter((s) => s.kind === kind);
  const counts: Record<RuleId, [number, number]> = {
    turning: [rooms.filter((r) => r.conforme).length, rooms.length],
    doors: [doors.filter((d) => d.ok).length, doors.length],
    transfer: [of("transfer").filter((s) => s.fits).length, of("transfer").length],
    washbasin: [of("washbasin").filter((s) => s.fits).length, of("washbasin").length],
    walk: walk ? [walk.reached.length, reading.rooms.length] : [0, 0],
  };
  return RULES.map((rule) => ({ rule, passed: counts[rule.id][0], total: counts[rule.id][1] }));
}
