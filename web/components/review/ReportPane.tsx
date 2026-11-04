"use client";

import {
  Accessibility, ArrowRight, DoorOpen, Download, FileText, ListChecks, Pause, Play, RotateCcw, Sparkles, Undo2, WandSparkles, X,
} from "lucide-react";
import { Block, Key, Mark } from "@/components/Cartouche";
import ExportReport from "@/components/ExportReport";
import { PaneHeader } from "@/components/review/Workspace";
import { Button } from "@/components/ui/button";
import {
  doorSides, roomLabel, type Correction, type ExplainResult, type PlanReading, type Walk,
} from "@/lib/plan";
import { scoreRules, type RuleScore } from "@/lib/rules";
import { cn } from "@/lib/utils";
import { usePreferences } from "@/app/preferences";

/**
 * What the report will say about the sheet open (ported from pmr-checker): the rooms
 * folded into one strip of ticks, then the checks ConformScope adds — the walk, the
 * doors, the accessible WC — and Muse Spark's explanations of every failure.
 * Verdict sentences from the server (walk.verdict, stop reasons, explanations)
 * arrive in the API's words; the chrome around them is localized here.
 */
export default function ReportPane({
  reading, active, onPickRoom, walk, playing, played, onPlay, onPause,
  busy, onCorrect, asDrawn, proposed, proposing, onPropose, explain, explaining, onExplain, onClose,
  fileName,
}: {
  reading: PlanReading;
  active: number | null;
  onPickRoom: (i: number) => void;
  walk: Walk | null;
  playing: boolean;
  /** The walk has rolled at least once, so the button replays it. */
  played: boolean;
  onPlay: () => void;
  onPause: () => void;
  busy: boolean;
  /** A correction added to the ones stored: an override from a stop or a door. */
  onCorrect: (correction: Correction) => void;
  /** The walk through the plan as drawn, to compare a proposal with. */
  asDrawn: Walk | null;
  /** The doors widened on paper; the walk shown is walked through them. */
  proposed: number[];
  proposing: boolean;
  /** Walk again with these doors widened (none: the plan as drawn). */
  onPropose: (doors: number[]) => void;
  explain: ExplainResult | null;
  explaining: boolean;
  onExplain: () => void;
  onClose: () => void;
  /** The file uploaded, to title the exported report. */
  fileName?: string | null;
}) {
  const { locale, t } = usePreferences();
  const rooms = reading.rooms;
  const checked = rooms.filter((r) => r.conforme !== null);
  const passing = checked.filter((r) => r.conforme).length;
  const failing = checked.length - passing;
  const unchecked = rooms.length - checked.length;
  const doors = reading.doors ?? [];
  const judged = doors.filter((d) => d.ok !== null);
  const narrow = judged.filter((d) => !d.ok);
  const clean = walk ? walk.unreachable.length === 0 && walk.stops.length === 0 : null;
  const trying = proposed.length > 0;
  const tryWiden = (door: number) => !proposed.includes(door) && onPropose([...proposed, door]);
  const widenTo = (door: number) => doors[door]?.required_m?.toFixed(2) ?? "0.80";

  return (
    <section aria-label={t("report.title")} className="flex h-full min-h-0 flex-col bg-card">
      <PaneHeader icon={<FileText />} title={t("report.title")}>
        <Button variant="ghost" size="icon-xs" aria-label={t("report.close")} onClick={onClose}>
          <X />
        </Button>
      </PaneHeader>
      <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin]">
        <RulesScore scores={scoreRules(reading, walk)} />

        <Block>
          <Key>{t("report.turning")}</Key>
          <div className="mt-1.5 flex items-baseline gap-2.5 font-mono">
            <span className="text-[34px] leading-none font-medium">{passing}</span>
            <span className="text-[34px] leading-none text-border">/</span>
            <span className="text-[34px] leading-none font-medium">{checked.length}</span>
            <span className="font-sans text-[13px] text-muted-foreground">{t("report.roomsPass")}</span>
          </div>
          {/* One tick per room, in number order: the rooms pane folded into one line. */}
          <ol aria-hidden className="mt-3.5 flex h-2.5 items-end gap-[3px]">
            {rooms.map((r, i) => (
              <li key={i} style={{ animationDelay: `${i * 18}ms` }}
                  onClick={() => onPickRoom(i)}
                  className={cn(
                    "max-w-5 flex-1 cursor-pointer rounded-[1px] motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:fill-mode-both",
                    r.conforme === null ? "h-1 bg-pas-verifie/40"
                      : r.conforme ? "h-full bg-conforme" : "h-full bg-non-conforme",
                    active === i && "outline outline-offset-2 outline-primary",
                  )} />
            ))}
          </ol>
          <p className="mt-2.5 text-xs text-muted-foreground">
            {failing === 0 ? t("report.noFail") : t(failing === 1 ? "report.failsOne" : "report.failsMany", { n: failing })}
            {unchecked > 0 && t("report.uncheckedSuffix", { n: unchecked })}
          </p>
        </Block>

        {walk && walk.route.length > 0 && (
          <Block>
            <Key className="flex items-center gap-1.5"><Accessibility className="size-3.5" />{t("report.walk")}</Key>
            <p className="mt-2"><Mark ok={clean}>{walk.verdict}</Mark></p>
            <div className="mt-2.5 flex gap-2">
              <Button size="sm" variant="outline" disabled={playing} onClick={onPlay}>
                {played ? <RotateCcw /> : <Play />}{played ? t("report.replay") : t("report.play")}
              </Button>
              {playing && <Button size="sm" variant="ghost" onClick={onPause}><Pause />{t("report.pause")}</Button>}
            </div>
            {trying && asDrawn && (
              <div role="status" aria-live="polite"
                   className="proposal mt-3 rounded-md border border-dashed border-conforme/60 bg-conforme/5 px-3 py-2.5 text-xs motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
                <Key className="flex items-center gap-1.5 text-conforme"><WandSparkles className="size-3.5" />{t("prop.fixed")}</Key>
                <dl className="mt-2 grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1">
                  <dt className="text-muted-foreground">{t("prop.reached")}</dt>
                  <dd className="flex items-center gap-1.5 font-mono">
                    {asDrawn.reached.length}<ArrowRight className="size-3 text-muted-foreground" aria-label={t("prop.becomes")} />
                    <span className="font-semibold text-conforme">{walk.reached.length}</span>
                    <span className="text-muted-foreground">{t("prop.of", { n: rooms.length })}</span>
                  </dd>
                  <dt className="text-muted-foreground">{t("prop.stops")}</dt>
                  <dd className="flex items-center gap-1.5 font-mono">
                    {asDrawn.stops.length}<ArrowRight className="size-3 text-muted-foreground" aria-label={t("prop.becomes")} />
                    <span className="font-semibold text-conforme">{walk.stops.length}</span>
                  </dd>
                </dl>
                <ul className="mt-2 grid gap-0.5">
                  {proposed.map((d) => (
                    <li key={d} className="text-foreground/85">
                      {t("prop.widen", { sides: doors[d] ? doorSides(doors[d], rooms, locale) : t("prop.doorFallback", { n: d }) })}{" "}
                      <span className="font-mono">{doors[d]?.width_m.toFixed(2)} → {widenTo(d)} m</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-muted-foreground">{t("prop.whatif")}</p>
                <Button size="xs" variant="ghost" className="-ml-1.5 mt-1" disabled={proposing} onClick={() => onPropose([])}>
                  <Undo2 />{t("prop.back")}
                </Button>
              </div>
            )}
            {walk.unreachable.length > 0 && (
              <p className="mt-2.5 text-xs text-muted-foreground">
                {t("report.notReached")} {walk.unreachable.map((u) => roomLabel(rooms[u.room], u.room, locale)).join(", ")}
              </p>
            )}
            {walk.stops.length > 0 && (
              <ul className="mt-2.5 grid gap-2">
                {walk.stops.map((stop, i) => (
                  <li key={i} className="rounded-md border border-non-conforme/30 bg-non-conforme/5 px-2.5 py-2 text-xs">
                    <p>
                      {stop.kind === "door"
                        ? t("report.stoppedDoor", { reason: stop.reason })
                        : `${roomLabel(rooms[stop.room ?? 0], stop.room ?? 0, locale)}: ${stop.reason}`}
                    </p>
                    {stop.kind === "door" && stop.door !== null && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <Button size="xs" disabled={busy || proposing}
                                onClick={() => tryWiden(stop.door as number)}>
                          <WandSparkles />{t("prop.tryWidenTo", { width: widenTo(stop.door) })}
                        </Button>
                        <Button size="xs" variant="ghost" disabled={busy}
                                onClick={() => onCorrect({ kind: "override", target: "door", index: stop.door as number, value: true })}>
                          {t("prop.misread")}
                        </Button>
                      </div>
                    )}
                    {stop.kind === "turn" && stop.room !== null && (
                      <Button size="xs" variant="ghost" className="-ml-1.5 mt-1" disabled={busy}
                              onClick={() => onCorrect({ kind: "override", target: "room", index: stop.room as number, value: true })}>
                        {t("report.fixRoom")}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Block>
        )}

        {reading.doors_ok != null && (
          <Block>
            <Key className="flex items-center gap-1.5"><DoorOpen className="size-3.5" />{t("report.doors")}</Key>
            <p className="mt-2">
              <Mark ok={reading.doors_ok}>
                {reading.doors_ok
                  ? t("report.doorsOk", { n: judged.length })
                  : t(narrow.length === 1 ? "report.doorsBadOne" : "report.doorsBadMany", { n: narrow.length })}
              </Mark>
            </p>
            {narrow.length > 0 && (
              <ul className="mt-2.5 grid gap-2">
                {narrow.map((door) => {
                  const index = doors.indexOf(door);
                  return (
                    <li key={index} className="rounded-md border border-secondary px-2.5 py-2 text-xs">
                      <p>{doorSides(door, rooms, locale)}</p>
                      <p className="mt-0.5 font-mono text-muted-foreground">
                        {t("report.needsM", { width: door.width_m.toFixed(2), required: door.required_m?.toFixed(2) ?? "" })}
                        {door.role === "entrance" && t("report.entrance")}
                      </p>
                      <div className="-ml-1.5 mt-1 flex flex-wrap gap-1.5">
                        {proposed.includes(index) ? (
                          <span className="px-1.5 py-0.5 text-conforme">{t("prop.widened")}</span>
                        ) : (
                          <Button size="xs" variant="outline" disabled={busy || proposing} onClick={() => tryWiden(index)}>
                            <WandSparkles />{t("prop.tryWidening")}
                          </Button>
                        )}
                        <Button size="xs" variant="ghost" disabled={busy}
                                onClick={() => onCorrect({ kind: "override", target: "door", index, value: true })}>
                          {t("report.overrideDoor")}
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Block>
        )}

        {reading.accessible_wc != null && (
          <Block>
            <Key>{t("report.wc")}</Key>
            <p className="mt-2">
              <Mark ok={reading.accessible_wc}>
                {reading.accessible_wc ? t("report.wcOk") : t("report.wcBad")}
              </Mark>
            </p>
          </Block>
        )}

        <Block>
          <Key className="flex items-center gap-1.5"><Sparkles className="size-3.5" />{t("report.why")}</Key>
          {!explain ? (
            <>
              <p className="mt-2 text-xs text-muted-foreground">{t("report.whyBody")}</p>
              <Button size="sm" className="mt-2.5" disabled={explaining || busy} onClick={onExplain}>
                <Sparkles />{explaining ? t("report.explaining") : t("report.explain")}
              </Button>
            </>
          ) : explain.failures.length === 0 ? (
            <p className="mt-2"><Mark ok>{t("report.nothing")}</Mark></p>
          ) : (
            <ul className="mt-2.5 grid gap-2.5">
              {explain.failures.map((failure) => (
                <li key={failure.id} className="rounded-md border border-secondary px-2.5 py-2 text-xs leading-relaxed">
                  <p className="font-medium text-foreground">{failure.subject}</p>
                  <p className="mt-1 text-foreground/80">{failure.reason}</p>
                  <p className="mt-1 text-primary">{t("report.fix")} {failure.fix}</p>
                  <p className="mt-1.5">
                    {failure.verify.status === "verified" ? (
                      failure.verify.doubtful ? (
                        <Mark ok={false}>
                          {t(failure.verify.agree ? "report.doubtfulUnsure" : "report.doubtfulDisagrees",
                             { pct: Math.round(failure.verify.confidence * 100), note: failure.verify.note })}
                        </Mark>
                      ) : (
                        <Mark ok>{t("report.verified", { pct: Math.round(failure.verify.confidence * 100) })}</Mark>
                      )
                    ) : (
                      <span className="text-muted-foreground">{t("report.notVerified")}</span>
                    )}
                    {failure.source === "template" && (
                      <span className="ml-1.5 text-muted-foreground">{t("report.fromMeasurements")}</span>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Block>

        <ExportReport planId={reading.id} fileName={fileName} />

        {reading.corrections.length > 0 && (
          <Block>
            <Key>{t("report.corrections")}</Key>
            <p className="mt-2 text-xs text-muted-foreground">
              {t(reading.corrections.length === 1 ? "report.correctionsOne" : "report.correctionsMany",
                 { n: reading.corrections.length })}
            </p>
            <Button asChild size="sm" variant="outline" className="mt-2.5">
              <a href={`/api/plans/${reading.id}/sheets/${reading.page}/labels`}>
                <Download />{t("report.download")}
              </a>
            </Button>
          </Block>
        )}

        <Legend />
      </div>
    </section>
  );
}

/** Every rule at a glance: how many pass, against which value and which text. */
function RulesScore({ scores }: { scores: RuleScore[] }) {
  const { t } = usePreferences();
  // Every room, door and space judged is one check; the walk is built on them.
  const measured = scores.filter((s) => s.rule.id !== "walk");
  const checks = measured.reduce((n, s) => n + s.total, 0);
  const fails = measured.reduce((n, s) => n + s.total - s.passed, 0);
  const rules = scores.filter((s) => s.total > 0).length;
  return (
    <Block>
      <Key className="flex items-center gap-1.5"><ListChecks className="size-3.5" />{t("score.title")}</Key>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1 font-mono">
        <span className="text-[28px] leading-none font-medium">{checks}</span>
        <span className="font-sans text-[13px] text-muted-foreground">{t("score.summary", { rules, fails })}</span>
      </div>
      <ul className="mt-2.5 grid min-w-0 grid-cols-1 gap-1.5">
        {scores.map(({ rule, passed, total }) => {
          const ok = total === 0 ? null : passed === total;
          return (
            <li key={rule.id}
                className={cn("grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-2.5 rounded-md border px-2.5 py-1.5 text-xs",
                  ok === null ? "border-secondary text-muted-foreground"
                    : ok ? "border-conforme/30 bg-conforme/5" : "border-non-conforme/30 bg-non-conforme/5")}>
              <span aria-hidden className={cn("mt-1 size-2 rounded-full",
                ok === null ? "bg-pas-verifie/40" : ok ? "bg-conforme" : "bg-non-conforme")} />
              <span className="min-w-0">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-foreground">{t(rule.name)}</span>
                  <span className={cn("shrink-0 font-mono", ok === false && "text-non-conforme", ok && "text-conforme")}>
                    {total === 0 ? t("score.none")
                      : `${passed}/${total}${rule.id === "walk" ? ` ${t("score.walkUnit")}` : ""}`}
                  </span>
                </span>
                <span className="block text-[11px] break-words text-muted-foreground">
                  <span className="font-mono whitespace-nowrap">{rule.value}</span> · {t(rule.source)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </Block>
  );
}

/** What the marks on the sheet mean. */
function Legend() {
  const { t } = usePreferences();
  return (
    <div className="key-legend px-4 py-4 text-xs text-muted-foreground" role="note">
      <Key>{t("legend.title")}</Key>
      <div className="mt-2 flex items-center gap-2.5 text-conforme">
        <Ring /><span>{t("legend.pass")}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5 text-non-conforme">
        <Ring /><span>{t("legend.fail")}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="h-1 w-3.5 flex-none rounded-full bg-conforme" />
        <span aria-hidden className="-ml-1.5 h-1 w-3.5 flex-none rounded-full bg-non-conforme" />
        <span>{t("legend.door")}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="w-3.5 flex-none border-t-[3px] border-dashed border-conforme" />
        <span>{t("legend.widened")}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="size-3.5 flex-none rounded-[2px] border border-dashed border-conforme" />
        <span>{t("legend.transfer")}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="grid size-3.5 flex-none place-items-center rounded-full bg-non-conforme text-[9px] font-bold text-white">!</span>
        <span>{t("legend.stop")}</span>
      </div>
    </div>
  );
}

/** The verdict circle as it is drawn on the plan: a dashed ring. */
function Ring() {
  return <span aria-hidden className="size-3.5 flex-none rounded-full border-[1.5px] border-dashed border-current" />;
}
