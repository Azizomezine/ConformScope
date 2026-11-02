"use client";

import { Accessibility, DoorOpen, Download, FileText, Pause, Play, RotateCcw, Sparkles, X } from "lucide-react";
import { Block, Key, Mark } from "@/components/Cartouche";
import { PaneHeader } from "@/components/review/Workspace";
import { Button } from "@/components/ui/button";
import {
  doorSides, roomLabel, type Correction, type ExplainResult, type PlanReading, type Walk,
} from "@/lib/plan";
import { cn } from "@/lib/utils";

/**
 * What the report will say about the sheet open (ported from pmr-checker): the rooms
 * folded into one strip of ticks, then the checks ConformScope adds — the walk, the
 * doors, the accessible WC — and Muse Spark's explanations of every failure.
 */
export default function ReportPane({
  reading, active, onPickRoom, walk, playing, played, onPlay, onPause,
  busy, onCorrect, explain, explaining, onExplain, onClose,
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
  explain: ExplainResult | null;
  explaining: boolean;
  onExplain: () => void;
  onClose: () => void;
}) {
  const rooms = reading.rooms;
  const checked = rooms.filter((r) => r.conforme !== null);
  const passing = checked.filter((r) => r.conforme).length;
  const failing = checked.length - passing;
  const unchecked = rooms.length - checked.length;
  const doors = reading.doors ?? [];
  const judged = doors.filter((d) => d.ok !== null);
  const narrow = judged.filter((d) => !d.ok);
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const clean = walk ? walk.unreachable.length === 0 && walk.stops.length === 0 : null;

  return (
    <section aria-label="Report" className="flex h-full min-h-0 flex-col bg-card">
      <PaneHeader icon={<FileText />} title="Report">
        <Button variant="ghost" size="icon-xs" aria-label="Close the report" onClick={onClose}>
          <X />
        </Button>
      </PaneHeader>
      <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin]">
        <Block>
          <Key>Turning circle</Key>
          <div className="mt-1.5 flex items-baseline gap-2.5 font-mono">
            <span className="text-[34px] leading-none font-medium">{passing}</span>
            <span className="text-[34px] leading-none text-border">/</span>
            <span className="text-[34px] leading-none font-medium">{checked.length}</span>
            <span className="font-sans text-[13px] text-muted-foreground">rooms pass</span>
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
            {failing === 0 ? "No room fails" : `${plural(failing, "room")} fail${failing === 1 ? "s" : ""}`}
            {unchecked > 0 && `, ${unchecked} not checked`}
          </p>
        </Block>

        {walk && walk.route.length > 0 && (
          <Block>
            <Key className="flex items-center gap-1.5"><Accessibility className="size-3.5" />Walk the plan</Key>
            <p className="mt-2"><Mark ok={clean}>{walk.verdict}</Mark></p>
            <div className="mt-2.5 flex gap-2">
              <Button size="sm" variant="outline" disabled={playing} onClick={onPlay}>
                {played ? <RotateCcw /> : <Play />}{played ? "Replay the walk" : "Play the walk"}
              </Button>
              {playing && <Button size="sm" variant="ghost" onClick={onPause}><Pause />Pause</Button>}
            </div>
            {walk.unreachable.length > 0 && (
              <p className="mt-2.5 text-xs text-muted-foreground">
                Not reached: {walk.unreachable.map((u) => roomLabel(rooms[u.room], u.room)).join(", ")}
              </p>
            )}
            {walk.stops.length > 0 && (
              <ul className="mt-2.5 grid gap-2">
                {walk.stops.map((stop, i) => (
                  <li key={i} className="rounded-md border border-non-conforme/30 bg-non-conforme/5 px-2.5 py-2 text-xs">
                    <p>
                      {stop.kind === "door"
                        ? `Stopped at a door: ${stop.reason}`
                        : `${roomLabel(rooms[stop.room ?? 0], stop.room ?? 0)}: ${stop.reason}`}
                    </p>
                    {stop.kind === "door" && stop.door !== null && (
                      <Button size="xs" variant="ghost" className="-ml-1.5 mt-1" disabled={busy}
                              onClick={() => onCorrect({ kind: "override", target: "door", index: stop.door as number, value: true })}>
                        Fix it: mark this door wide enough
                      </Button>
                    )}
                    {stop.kind === "turn" && stop.room !== null && (
                      <Button size="xs" variant="ghost" className="-ml-1.5 mt-1" disabled={busy}
                              onClick={() => onCorrect({ kind: "override", target: "room", index: stop.room as number, value: true })}>
                        Fix it: mark this room as passing
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
            <Key className="flex items-center gap-1.5"><DoorOpen className="size-3.5" />Doors</Key>
            <p className="mt-2">
              <Mark ok={reading.doors_ok}>
                {reading.doors_ok
                  ? `All ${judged.length} doors are wide enough`
                  : `${plural(narrow.length, "door")} ${narrow.length === 1 ? "is" : "are"} too narrow`}
              </Mark>
            </p>
            {narrow.length > 0 && (
              <ul className="mt-2.5 grid gap-2">
                {narrow.map((door) => {
                  const index = doors.indexOf(door);
                  return (
                    <li key={index} className="rounded-md border border-secondary px-2.5 py-2 text-xs">
                      <p>{doorSides(door, rooms)}</p>
                      <p className="mt-0.5 font-mono text-muted-foreground">
                        {door.width_m.toFixed(2)} m, needs {door.required_m?.toFixed(2)} m
                        {door.role === "entrance" && " · read as the entrance"}
                      </p>
                      <Button size="xs" variant="ghost" className="-ml-1.5 mt-1" disabled={busy}
                              onClick={() => onCorrect({ kind: "override", target: "door", index, value: true })}>
                        Override: mark wide enough
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Block>
        )}

        {reading.accessible_wc != null && (
          <Block>
            <Key>Accessible WC</Key>
            <p className="mt-2">
              <Mark ok={reading.accessible_wc}>
                {reading.accessible_wc
                  ? "A toilet has a 0.80 × 1.30 m transfer space"
                  : "No toilet has a 0.80 × 1.30 m transfer space"}
              </Mark>
            </p>
          </Block>
        )}

        <Block>
          <Key className="flex items-center gap-1.5"><Sparkles className="size-3.5" />Why it fails</Key>
          {!explain ? (
            <>
              <p className="mt-2 text-xs text-muted-foreground">
                A plain-language reason and fix for each failure, double-checked by Muse Spark Open.
              </p>
              <Button size="sm" className="mt-2.5" disabled={explaining || busy} onClick={onExplain}>
                <Sparkles />{explaining ? "Explaining…" : "Explain the failures"}
              </Button>
            </>
          ) : explain.failures.length === 0 ? (
            <p className="mt-2"><Mark ok>Nothing to explain: every check passed.</Mark></p>
          ) : (
            <ul className="mt-2.5 grid gap-2.5">
              {explain.failures.map((failure) => (
                <li key={failure.id} className="rounded-md border border-secondary px-2.5 py-2 text-xs leading-relaxed">
                  <p className="font-medium text-foreground">{failure.subject}</p>
                  <p className="mt-1 text-foreground/80">{failure.reason}</p>
                  <p className="mt-1 text-primary">Fix: {failure.fix}</p>
                  <p className="mt-1.5">
                    {failure.verify.status === "verified" ? (
                      failure.verify.doubtful ? (
                        <Mark ok={false}>
                          Doubtful — the verifier {failure.verify.agree ? "is unsure" : "disagrees"}{" "}
                          ({Math.round(failure.verify.confidence * 100)}%): {failure.verify.note}
                        </Mark>
                      ) : (
                        <Mark ok>Verified by Muse Spark Open ({Math.round(failure.verify.confidence * 100)}%)</Mark>
                      )
                    ) : (
                      <span className="text-muted-foreground">Not verified (no verifier key).</span>
                    )}
                    {failure.source === "template" && (
                      <span className="ml-1.5 text-muted-foreground">Written from the measurements.</span>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Block>

        {reading.corrections.length > 0 && (
          <Block>
            <Key>Corrections</Key>
            <p className="mt-2 text-xs text-muted-foreground">
              {plural(reading.corrections.length, "correction")} saved on this sheet, kept as
              fine-tuning labels.
            </p>
            <Button asChild size="sm" variant="outline" className="mt-2.5">
              <a href={`/api/plans/${reading.id}/sheets/${reading.page}/labels`}>
                <Download />Download the labels (JSONL)
              </a>
            </Button>
          </Block>
        )}

        <Legend />
      </div>
    </section>
  );
}

/** What the marks on the sheet mean. */
function Legend() {
  return (
    <div className="key-legend px-4 py-4 text-xs text-muted-foreground" role="note">
      <Key>Legend</Key>
      <div className="mt-2 flex items-center gap-2.5 text-conforme">
        <Ring /><span>The Ø1.50 m circle fits: passes</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5 text-non-conforme">
        <Ring /><span>The circle does not fit: fails</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="h-1 w-3.5 flex-none rounded-full bg-conforme" />
        <span aria-hidden className="-ml-1.5 h-1 w-3.5 flex-none rounded-full bg-non-conforme" />
        <span>A doorway, wide enough or too narrow</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="size-3.5 flex-none rounded-[2px] border border-dashed border-conforme" />
        <span>A transfer space beside a toilet (dashed: to confirm)</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2.5">
        <span aria-hidden className="grid size-3.5 flex-none place-items-center rounded-full bg-non-conforme text-[9px] font-bold text-white">!</span>
        <span>Where the wheelchair stops</span>
      </div>
    </div>
  );
}

/** The verdict circle as it is drawn on the plan: a dashed ring. */
function Ring() {
  return <span aria-hidden className="size-3.5 flex-none rounded-full border-[1.5px] border-dashed border-current" />;
}
