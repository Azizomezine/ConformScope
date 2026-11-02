"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Accessibility, ChevronLeft, ChevronRight, CircleAlert, CircleCheck, CircleDashed, Combine,
  DoorClosed, FileText, FileUp, PackageX, PenLine, RotateCcw, Ruler,
} from "lucide-react";
import { Key, Mark } from "@/components/Cartouche";
import PlanViewer, { type WalkFrame } from "@/components/PlanViewer";
import { Group, IconButton } from "@/components/PlanToolbar";
import ReportPane from "@/components/review/ReportPane";
import RoomsPane from "@/components/review/RoomsPane";
import Workspace from "@/components/review/Workspace";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  NDJSON, SCALE_TEXT, SOURCE_TEXT, fixtureSummary, insidePolygon, sheetSize, streamed, uploadDossier,
  type Correction, type Dossier, type ExplainResult, type PlanReading, type Pt, type Sheet,
  type Stage, type Walk,
} from "@/lib/plan";
import { bandOf, crept, labelOf, sendingAt } from "@/lib/progress";
import { cn } from "@/lib/utils";

const STEP_MS = 450; // one leg of the route: a room centre to a doorway, or a pause at a stop

type Mode = "none" | "merge" | "wall" | "remove" | "door" | "walk";

const HINTS: Record<Exclude<Mode, "none">, [string, string]> = {
  merge: ["Click the room that stays.", "Now click the nook to merge into it."],
  wall: ["Click one end of the missing wall.", "Now click the other end of the wall."],
  remove: ["Click the fixture that is not there.", ""],
  door: ["Click inside the swing of the door that is not there.", ""],
  walk: ["Click the room the wheelchair starts in.", ""],
};

function failure(error: unknown) {
  return error instanceof TypeError ? "Could not reach the ConformScope server." : String((error as Error).message);
}

/**
 * The check screen (its look and its loading ported from pmr-checker): a masthead with
 * the tally, the reading card over the sheet while it is checked, then the plan, the
 * rooms and the report side by side.
 */
export function PlanIntake() {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [reading, setReading] = useState<PlanReading | null>(null);
  // Each sheet as it was last read, so moving between a dossier's sheets shows one
  // already checked at once; and each sheet's size, to draw it before it is checked.
  const readings = useRef(new Map<string, PlanReading>());
  const [sizes, setSizes] = useState<Record<string, [number, number]>>({});
  const [readKeys, setReadKeys] = useState<ReadonlySet<string>>(new Set());
  const key = (id: string, p: number) => `${id}|${p}`;
  // The sheet open, by its key: a check answering for another is kept but not shown.
  const openKey = useRef<string | null>(null);

  const [fault, setFault] = useState<string | null>(null);
  // The sheet's first check: the reading card stands over it until it lands.
  const [checking, setChecking] = useState(false);
  // A correction replayed: the plan stays on screen under a status pill.
  const [replaying, setReplaying] = useState(false);
  // How much of the file has been sent (0..1); null once it has all gone.
  const [sent, setSent] = useState<number | null>(null);
  const [stage, setStage] = useState<Stage | null>(null);
  const [uploaded, setUploaded] = useState(false);
  const [progress, setProgress] = useState(0);

  const [active, setActive] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("none");
  const [pending, setPending] = useState<Pt | null>(null);
  const [reportOpen, setReportOpen] = useState(true);
  const [explain, setExplain] = useState<ExplainResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const busy = checking || replaying || sent !== null;

  // Walk the plan (issue #14): the route, and how many of its legs the icon has rolled.
  const [walk, setWalk] = useState<Walk | null>(null);
  const [clock, setClock] = useState(0);
  const [playing, setPlaying] = useState(false);
  const reducedMotion = useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );

  function play(next: Walk | null) {
    setWalk(next);
    setClock(0);
    // Reduced motion: no rolling icon — land on the end state, stops included.
    if (reducedMotion && next) {
      setClock(Math.max(0, next.route.length - 1));
      setPlaying(false);
      return;
    }
    setPlaying(Boolean(next && next.route.length > 1));
  }

  useEffect(() => {
    if (!playing || !walk) return;
    const legs = walk.route.length - 1;
    let frame = 0;
    // Seed from the first frame, not performance.now(): a rAF timestamp is the frame's
    // start and can be earlier than "now", which made dt negative, the clock < 0 and
    // walk.route[-1] undefined — the crash on "Replay the walk".
    let last: number | null = null;
    const tick = (now: number) => {
      const dt = last === null ? 0 : now - last;
      last = now;
      setClock((c) => {
        const next = Math.min(legs, Math.max(0, c + dt / STEP_MS));
        if (next >= legs) setPlaying(false);
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, walk]);

  // Creeps inside the band of the stage the server last reported, and only the next
  // stage takes it past the band's edge. Until the file has gone, the bar is the real
  // fraction sent instead.
  const drafting = (checking || replaying) && sent === null;
  // (The bar is set back to nothing where each piece of work starts.)
  useEffect(() => {
    if (!drafting) return;
    const band = bandOf(stage, uploaded);
    const id = setInterval(() => setProgress((p) => crept(p, band)), 300);
    return () => clearInterval(id);
  }, [drafting, stage, uploaded]);

  // Escape puts a correction tool down, as it would any half-made mark.
  useEffect(() => {
    if (mode === "none") return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setMode("none"); setPending(null); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode]);

  // A refresh or a link: the URL says which dossier and sheet are open.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = q.get("plan");
    if (!id) return;
    const sheet = Number(q.get("sheet"));
    fetch(`/api/plans/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("This plan is no longer on the server."))))
      .then((d: Dossier) => {
        setDossier(d);
        const chosen = d.sheets.find((s) => s.page === sheet) ?? d.sheets.find((s) => !s.annexe) ?? d.sheets[0];
        openSheet(d, chosen.page, "none");
      })
      .catch((e) => setFault(failure(e)));
    // Once, on arrival: later sheets are opened by the auditor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function show(body: PlanReading) {
    readings.current.set(key(body.id, body.page), body);
    setReadKeys((ks) => new Set(ks).add(key(body.id, body.page)));
    setReading(body);
    setExplain(null);
    play(body.walk ?? null);
  }

  /** Open a sheet: one already read is shown at once, as it was left; one never read
   *  is drawn bare under the reading card while it is checked (issue #11). */
  async function openSheet(d: Dossier, sheet: number, history: "push" | "replace" | "none" = "push") {
    setPage(sheet);
    openKey.current = key(d.id, sheet);
    setActive(null); setMode("none"); setPending(null); setFault(null);
    nameInUrl(d.id, sheet, history);
    const kept = readings.current.get(key(d.id, sheet));
    if (kept) { show(kept); return; }
    setReading(null); play(null);
    setChecking(true); setProgress(0);
    sheetSize(d.id, sheet)
      .then((size) => setSizes((s) => ({ ...s, [key(d.id, sheet)]: size })))
      .catch(() => {});
    try {
      const response = await fetch(`/api/plans/${d.id}/sheets/${sheet}`, { headers: NDJSON });
      const body = await streamed<PlanReading>(response, setStage);
      // A late answer about a sheet already left is kept, not shown.
      readings.current.set(key(d.id, sheet), body);
      setReadKeys((ks) => new Set(ks).add(key(d.id, sheet)));
      if (openKey.current === key(d.id, sheet)) show(body);
    } catch (error) {
      setFault(failure(error));
    } finally {
      setChecking(false);
      setStage(null);
      setUploaded(false);
    }
  }

  async function upload(file: File) {
    setFault(null); setReading(null); setDossier(null); setPage(null); setActive(null);
    setFileName(file.name); play(null);
    setSent(0); setStage(null); setUploaded(true);
    readings.current.clear(); setReadKeys(new Set());
    try {
      const d = await uploadDossier(file, (f) => setSent(f >= 1 ? null : f));
      setSent(null);
      setDossier(d);
      const first = d.sheets.find((s) => !s.annexe) ?? d.sheets[0];
      await openSheet(d, first.page, "replace");
    } catch (error) {
      setSent(null);
      setUploaded(false);
      setFault(failure(error));
    }
  }

  async function postCorrections(corrections: Correction[]) {
    if (!reading) return;
    setReplaying(true); setFault(null); setStage(null); setProgress(0);
    try {
      const response = await fetch(`/api/plans/${reading.id}/sheets/${reading.page}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...NDJSON },
        body: JSON.stringify({ corrections }),
      });
      show(await streamed<PlanReading>(response, setStage));
      setPending(null);
      setMode("none");
    } catch (error) {
      setFault(`The correction was not applied. ${failure(error)}`);
    } finally {
      setReplaying(false);
      setStage(null);
    }
  }

  const correct = (c: Correction) => reading && postCorrections([...reading.corrections, c]);

  async function walkFrom(room: number) {
    if (!reading) return;
    try {
      const response = await fetch(`/api/plans/${reading.id}/sheets/${reading.page}/walk?from=${room}`);
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? `Walking the plan failed (${response.status})`);
      play(body);
      setMode("none");
    } catch (error) {
      setFault(failure(error));
    }
  }

  // Explain + verify (issue #16): a human sentence and a second opinion per failure.
  async function explainFailures() {
    if (!reading) return;
    setExplaining(true); setFault(null);
    try {
      const response = await fetch(`/api/plans/${reading.id}/sheets/${reading.page}/explain`);
      const body = await response.json().catch(() => null);
      if (!response.ok || !body) throw new Error(body?.detail ?? `Explaining the failures failed (${response.status})`);
      setExplain(body as ExplainResult);
    } catch (error) {
      setFault(failure(error));
    } finally {
      setExplaining(false);
    }
  }

  /** A click on the plan while a correction tool is in hand, in plan pixels. */
  function onPoint([xPx, yPx]: Pt) {
    if (!reading || mode === "none" || busy) return;
    if (mode === "walk") {
      const room = reading.rooms.findIndex((r) => insidePolygon([xPx, yPx], r.polygon_px));
      if (room >= 0) walkFrom(room);
      return;
    }
    // Corrections are anchored in PDF points, so they survive a re-render (issue #6).
    const f = reading.pt_per_plan_px ?? 1;
    const pt: Pt = [Math.round(xPx * f * 10) / 10, Math.round(yPx * f * 10) / 10];
    if (mode === "remove") { correct({ kind: "remove_fixture", point: pt }); return; }
    if (mode === "door") { correct({ kind: "remove_door", point: pt }); return; }
    if (!pending) { setPending(pt); return; }
    // Merge: first click the room that stays, second the nook it claims.
    if (mode === "merge") correct({ kind: "merge", point: pt, target_point: pending });
    else correct({ kind: "wall", start: pending, end: pt });
  }

  function toggle(next: Mode) {
    setMode(mode === next ? "none" : next);
    setPending(null);
    setActive(null);
  }

  // Where the icon is, and what it has passed so far.
  const legs = walk ? walk.route.length - 1 : 0;
  const at = Math.min(Math.floor(clock), Math.max(legs, 0));
  const frame: WalkFrame | null = (() => {
    if (!walk || walk.route.length === 0) return null;
    const a = walk.route[at].point_px;
    const b = walk.route[Math.min(at + 1, legs)].point_px;
    const f = clock - at;
    const passed = walk.route.slice(0, at + 1);
    return {
      icon: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f],
      reached: new Set(passed.filter((s) => s.event === "enter").map((s) => s.room)),
      stops: passed.filter((s) => s.event === "blocked_door" || s.event === "cannot_turn"),
    };
  })();

  const sheet = dossier?.sheets.find((s) => s.page === page) ?? null;
  const size = dossier && page !== null ? sizes[key(dossier.id, page)] : undefined;
  const shown = reading && reading.page === page && reading.id === dossier?.id ? reading : null;
  const checked = shown?.rooms.filter((r) => r.conforme !== null) ?? [];
  const passing = checked.filter((r) => r.conforme).length;
  // The pending point is kept in PDF points, as corrections are; the drawing wants pixels.
  const pointToFix = (pending: Pt | null) => (pending && shown?.pt_per_plan_px
    ? [pending[0] / shown.pt_per_plan_px, pending[1] / shown.pt_per_plan_px] as Pt : pending);
  // Whole percents: 0.42 × 100 is 42.00000000000001 in floating point.
  const pct = Math.round(sent !== null ? sendingAt(sent) : progress);

  const correctionTools = shown?.checked ? (
    <Group label="Corrections">
      <IconButton label="Merge a nook into a room" icon={Combine} pressed={mode === "merge"}
                  disabled={busy} onClick={() => toggle("merge")} />
      <IconButton label="Draw a missing wall" icon={PenLine} pressed={mode === "wall"}
                  disabled={busy} onClick={() => toggle("wall")} />
      <IconButton label="Remove a fixture" icon={PackageX} pressed={mode === "remove"}
                  disabled={busy || !shown.fixtures?.length} onClick={() => toggle("remove")} />
      <IconButton label="Remove a door" icon={DoorClosed} pressed={mode === "door"}
                  disabled={busy || !shown.doors?.length} onClick={() => toggle("door")} />
      <IconButton label="Start the walk in a room" icon={Accessibility} pressed={mode === "walk"}
                  disabled={busy || shown.rooms.length === 0} onClick={() => toggle("walk")} />
      <IconButton label="Clear every correction" icon={RotateCcw}
                  disabled={busy || shown.corrections.length === 0} onClick={() => postCorrections([])} />
    </Group>
  ) : null;

  const card = (over: boolean) => (
    // An unfilled drawing frame, waiting for its sheet — or, the sheet known, a note
    // pinned over it saying what it is still waiting for.
    <div className={cn("w-full max-w-[560px] rounded-lg border border-dashed border-border px-6 py-12 text-center sm:px-14",
                       over && "status pointer-events-auto border-solid bg-card/95 py-6 shadow-lg")}>
      {!over && <div className="font-mono text-[44px] leading-none text-primary" aria-hidden>Ø</div>}
      <p className={cn("font-lettering text-[13px] font-semibold uppercase tracking-[.14em]", !over && "mt-4")}>
        {shown && !shown.checked ? "Plan annexe — not checked"
          : sent !== null ? "Sending the plan…"
          : checking ? "Checking the sheet…"
          : over ? "Check interrupted" : "No plan open"}
      </p>
      <p className="mx-auto mt-2 max-w-[46ch] text-muted-foreground">
        {shown && !shown.checked ? shown.reason
          : sent !== null ? "The file is sent as it is; its sheets are listed as soon as it arrives."
          : checking ? "Muse Spark reads the names and the scale, then the rooms are measured in metres and every turning circle, door and toilet is checked."
          : over ? "Open this sheet again to resume its check."
          : "Open a home plan, PDF or picture — one sheet or a whole building. ConformScope measures every room in metres and checks the Ø1.50 m turning circle, the doors and the walk through the home."}
      </p>

      {!busy && !over && (
        <Button className="mt-6" onClick={() => picker.current?.click()}>
          <FileUp />Choose a plan
        </Button>
      )}
      {!busy && over && !shown && dossier && page !== null && (
        <Button className="mt-4" variant="outline" onClick={() => openSheet(dossier, page, "none")}>
          <RotateCcw />Check this sheet again
        </Button>
      )}

      {(checking || sent !== null) && (
        <div className="mt-6" role="status" aria-live="polite">
          <div className="flex items-center gap-3">
            <Progress value={pct} aria-label="Checking the sheet" className="h-1 rounded-none bg-border" />
            <span className="min-w-[4ch] text-right font-mono text-xs text-primary">{pct}%</span>
          </div>
          <p className="mt-2 text-left font-mono text-xs text-muted-foreground">{labelOf(stage, sent)}</p>
        </div>
      )}
    </div>
  );

  return (
    <TooltipProvider>
    <main className="tool bg-background text-foreground">
      <header className="masthead flex h-14 flex-none items-center gap-3 border-b border-border bg-card px-4">
        <Link href="/" className={cn("flex flex-none items-center gap-2 font-lettering text-[13px] font-bold uppercase tracking-[.18em]",
                                     shown && "hidden xl:flex")}>
          <span aria-hidden className="font-mono text-base text-primary">Ø</span>ConformScope
        </Link>
        <Separator orientation="vertical" className={cn("h-6!", shown && "hidden xl:block")} />

        {shown ? (
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="truncate text-sm font-medium" title={fileName ?? undefined}>
              {fileName ?? "Plan"}
              {sheet && (dossier?.sheets.length ?? 0) > 1 && <span className="text-muted-foreground"> — {sheet.name}</span>}
            </p>
            <div className="flex items-center gap-3.5 text-xs text-muted-foreground [&_svg]:size-3.5">
              <span className="tally inline-flex items-center gap-1 whitespace-nowrap">
                <CircleCheck aria-hidden />
                <span className="font-mono text-foreground">{passing}</span>/
                <span className="font-mono text-foreground">{checked.length}</span> rooms pass
              </span>
              <span className="hidden items-center gap-1 whitespace-nowrap font-mono md:inline-flex">
                <CircleDashed aria-hidden />Ø 1.50 m
              </span>
              {shown.checked && (
                <span className={cn("hidden items-center gap-1 whitespace-nowrap lg:inline-flex",
                                    shown.scale_source === "assumed" && "text-primary")}>
                  <Ruler aria-hidden />
                  {shown.scale ?? "no written scale"}
                  {shown.scale_source && `, ${SCALE_TEXT[shown.scale_source] ?? shown.scale_source}`}
                </span>
              )}
            </div>
          </div>
        ) : (
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
            Can a wheelchair live in this home?
          </span>
        )}

        <div className="ml-auto flex flex-none items-center gap-2">
          {dossier && dossier.sheets.length > 1 && (
            <Sheets sheets={dossier.sheets} open={page} disabled={sent !== null}
                    read={(s) => readKeys.has(key(dossier.id, s.page))}
                    onOpen={(s) => openSheet(dossier, s.page)} />
          )}
          {shown?.checked && (
            <Button variant="outline" size="sm" aria-pressed={reportOpen}
                    className="aria-pressed:border-primary aria-pressed:bg-accent"
                    onClick={() => setReportOpen((o) => !o)}>
              <FileText /><span className="sr-only md:not-sr-only">Report</span>
            </Button>
          )}
          <Button variant={shown ? "ghost" : "outline"} size="sm"
                  className={cn(!shown && "border-primary/60")}
                  disabled={busy} onClick={() => picker.current?.click()}>
            <FileUp /><span className={cn(shown && "sr-only lg:not-sr-only")}>Open a plan</span>
          </Button>
          <input ref={picker} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" hidden
                 onChange={(e) => {
                   const file = e.target.files?.[0];
                   // Emptied, so choosing the same file again still reads it.
                   e.target.value = "";
                   if (file) upload(file);
                 }} />
        </div>
      </header>

      {fault && (
        <Alert role="alert" className="fault mx-4 mt-3 mb-1 w-auto border-destructive/40 bg-destructive/10 text-foreground">
          <CircleAlert className="text-destructive!" />
          <AlertDescription className="text-foreground/85">{fault}</AlertDescription>
        </Alert>
      )}

      {!(shown?.checked) && (
        dossier && page !== null && (size || shown) ? (
          <div className="sheet relative min-h-0 flex-1 [&>.drawing]:h-full">
            {/* Keyed on the sheet: each sheet opens whole, not at the zoom the last was left at. */}
            <PlanViewer key={`${dossier.id}-${page}`}
                        sheet={{ id: dossier.id, page, width: shown?.width ?? size![0], height: shown?.height ?? size![1] }}
                        reading={null} active={null} onPick={() => {}} />
            <div className="pointer-events-none absolute inset-x-0 top-14 flex justify-center px-4">
              {card(true)}
            </div>
          </div>
        ) : (
          <div className="empty grid flex-1 place-items-center overflow-y-auto p-6 sm:p-10">
            {card(false)}
          </div>
        )
      )}

      {shown?.checked && dossier && (
        <Workspace
          reportOpen={reportOpen}
          plan={
            <div className="relative h-full [&>.drawing]:h-full">
              <PlanViewer key={`${dossier.id}-${shown.page}`}
                          sheet={{ id: shown.id, page: shown.page, width: shown.width, height: shown.height }}
                          reading={shown} active={active}
                          onPick={(i) => setActive(i)}
                          correcting={mode !== "none" && !busy} onPoint={onPoint}
                          pending={pointToFix(pending)}
                          walk={frame} toolbarExtra={correctionTools} />
              {mode !== "none" && !replaying && (
                <p role="status"
                   className="pointer-events-none absolute top-13 left-1/2 w-max max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-2xl bg-ink/85 px-3.5 py-1.5 text-center text-xs text-vellum shadow-md backdrop-blur-xl backdrop-saturate-150 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-1 motion-safe:duration-200">
                  {HINTS[mode][pending ? 1 : 0] || HINTS[mode][0]} Esc to cancel.
                </p>
              )}
              {replaying && (
                <div role="status" aria-live="polite"
                     className="absolute top-13 left-1/2 w-[min(420px,calc(100%-2rem))] -translate-x-1/2 rounded-lg border border-border bg-card/95 px-4 py-3 shadow-lg">
                  <p className="font-lettering text-[11px] font-semibold uppercase tracking-[.14em]">Applying the correction…</p>
                  <div className="mt-2 flex items-center gap-3">
                    <Progress value={pct} aria-label="Applying the correction" className="h-1 rounded-none bg-border" />
                    <span className="min-w-[4ch] text-right font-mono text-xs text-primary">{pct}%</span>
                  </div>
                  <p className="mt-1.5 font-mono text-xs text-muted-foreground">{labelOf(stage, null)}</p>
                </div>
              )}
            </div>
          }
          rooms={
            <RoomsPane
              rooms={shown.rooms} active={active}
              onPick={(i) => { setMode("none"); setPending(null); setActive(i); }}
              notices={
                <>
                  {shown.scale_source === "assumed" && (
                    <p role="status" className="assumed-scale mb-3 rounded-sm px-3 py-2.5 text-xs leading-relaxed">
                      Scale assumed: no dimension was read on this plan. Check it before you rely on a verdict.
                    </p>
                  )}
                  {/* The tool talking about its own work: cobalt, never a verdict. */}
                  {shown.warnings.map((w) => (
                    <p key={w} className="notice mb-3 rounded-sm border-l-2 border-primary bg-accent px-3 py-2.5 text-xs leading-relaxed text-[#b9cdea]">
                      {w}
                    </p>
                  ))}
                </>
              }
              body={(room, i, open) => {
                if (!open) return null;
                const fixtures = shown.fixtures ?? [];
                return (
                  <div className="grid gap-2 border-t border-secondary bg-accent/40 px-3 py-3 text-xs motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-1 motion-safe:duration-200">
                    {room.verdict && <p><Mark ok={room.conforme}>{room.verdict}</Mark></p>}
                    <p className="text-muted-foreground">
                      Typed from the {SOURCE_TEXT[room.type_source]}
                      {room.written_area_m2 !== null && ` · ${room.written_area_m2} m² written on the plan`}
                    </p>
                    {(room.doors?.length ?? 0) > 0 && (
                      <p className="text-muted-foreground">
                        {room.doors!.length} door{room.doors!.length === 1 ? "" : "s"}
                        {room.doors!.some((d) => shown.doors?.[d]?.ok === false) && (
                          <span className="text-non-conforme"> · one is too narrow</span>
                        )}
                      </p>
                    )}
                    {(room.fixtures?.length ?? 0) > 0 && (
                      <p className="text-muted-foreground">Fixtures: {fixtureSummary(fixtures, room.fixtures)}</p>
                    )}
                    {(room.fixtures ?? []).map((f) => {
                      const space = fixtures[f]?.space;
                      return space ? <p key={f}><Mark ok={space.fits}>{space.verdict}</Mark></p> : null;
                    })}
                    {room.outline_source !== "auto" && <p className="text-primary">Outline corrected by hand</p>}
                    {room.warnings.map((w) => <p key={w} className="text-non-conforme">{w}</p>)}
                    <div className="mt-1 flex flex-wrap gap-1.5 border-t border-dashed border-border pt-2">
                      <Button size="xs" variant="outline" disabled={busy} onClick={() => walkFrom(i)}>
                        <Accessibility />Start the walk here
                      </Button>
                      {room.conforme !== null && (
                        <Button size="xs" variant="ghost" disabled={busy}
                                onClick={() => correct({ kind: "override", target: "room", index: i, value: !room.conforme })}>
                          {room.conforme ? "Override: mark as failing" : "Override: mark as passing"}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              }} />
          }
          report={
            <ReportPane reading={shown} active={active} onPickRoom={setActive}
                        walk={walk} playing={playing} played={clock > 0}
                        onPlay={() => play(walk)} onPause={() => setPlaying(false)}
                        busy={busy} onCorrect={correct}
                        explain={explain} explaining={explaining} onExplain={explainFailures}
                        onClose={() => setReportOpen(false)} />
          } />
      )}
    </main>
    </TooltipProvider>
  );
}

function nameInUrl(id: string, page: number, history: "push" | "replace" | "none") {
  if (history === "none") return;
  const url = `${window.location.pathname}?plan=${encodeURIComponent(id)}&sheet=${page}`;
  if (history === "push") window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
}

/** The paginator between a dossier's sheets, in page order (pmr-checker's levels). A
 *  plan annexe is dimmed and says why on hover; a sheet already checked opens at once. */
function Sheets({ sheets, open, disabled, read, onOpen }: {
  sheets: Sheet[];
  open: number | null;
  disabled: boolean;
  read: (sheet: Sheet) => boolean;
  onOpen: (sheet: Sheet) => void;
}) {
  const at = sheets.findIndex((s) => s.page === open);
  return (
    <nav className="sheets flex items-center gap-1" aria-label="Sheets of the dossier">
      <Key className="mr-1 hidden md:block">Sheet</Key>
      <Button variant="ghost" size="icon-xs" aria-label="Previous sheet" disabled={disabled || at <= 0}
              onClick={() => onOpen(sheets[at - 1])}><ChevronLeft /></Button>
      {sheets.map((s, i) => (
        <Tooltip key={s.page}>
          <TooltipTrigger asChild>
            <Button size="icon-xs" variant="ghost" disabled={disabled}
                    className={cn("font-mono text-xs text-muted-foreground",
                                  i === at && "bg-accent text-foreground ring-1 ring-primary",
                                  s.annexe && "opacity-40",
                                  read(s) && i !== at && "text-foreground")}
                    aria-label={s.annexe ? `${s.name}, not checked` : s.name}
                    aria-current={i === at ? "page" : undefined}
                    onClick={() => onOpen(s)}>
              {i + 1}
            </Button>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">
            <p className="font-medium">{s.name}</p>
            {s.annexe ? "A plan annexe: listed, never checked." : read(s) ? "Checked" : "Checked when opened"}
          </TooltipContent>
        </Tooltip>
      ))}
      <Button variant="ghost" size="icon-xs" aria-label="Next sheet"
              disabled={disabled || at < 0 || at >= sheets.length - 1}
              onClick={() => onOpen(sheets[at + 1])}><ChevronRight /></Button>
    </nav>
  );
}
