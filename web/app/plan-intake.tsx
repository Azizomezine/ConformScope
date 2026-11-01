"use client";

import { useEffect, useState, type MouseEvent } from "react";
import styles from "./page.module.css";

type Room = {
  name: string;
  room_type: string;
  type_source: "text" | "fixture" | "muse" | "none";
  area_m2: number | null;
  written_area_m2: number | null;
  polygon_px: [number, number][];
  circle_m: number | null;
  circle_px: [number, number] | null;
  conforme: boolean | null;
  max_diameter_m: number | null;
  verdict: string | null;
  outline_source: string;
  fixtures?: number[];
  doors?: number[];
  warnings: string[];
};

type Door = {
  rooms: [number | null, number | null];
  role: "interior" | "entrance" | "communs";
  width_m: number;
  measured_m: number;
  required_m: number | null;
  ok: boolean | null;
  verdict: string;
  doorway_px: [number, number][];
  swing_px: [number, number];
};

type Fixture = {
  kind: "placard" | "appliance" | "washbasin" | "toilet";
  room: number | null;
  polygon_px: [number, number][];
  outline_source: string;
  space: Space | null;
};

type Space = {
  kind: "transfer" | "washbasin";
  fits: boolean;
  verdict: string;
  to_confirm: boolean;
  polygon_px: [number, number][];
};

type Pt = [number, number];

type WalkStep = {
  point_px: Pt;
  room: number | null;
  door: number | null;
  event: "start" | "enter" | "through" | "back" | "blocked_door" | "cannot_turn";
};

type Walk = {
  start: { room: number | null; door: number | null } | null;
  reached: number[];
  unreachable: { room: number; blocked_by: number | null }[];
  stops: { kind: "door" | "turn"; door: number | null; room: number | null; reason: string }[];
  route: WalkStep[];
  verdict: string;
};

const STEP_MS = 450; // one leg of the route: a room centre to a doorway, or a pause at a stop

function insidePolygon([x, y]: Pt, polygon: [number, number][]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

type Correction =
  | { kind: "merge"; point: Pt; target_point: Pt }
  | { kind: "wall"; start: Pt; end: Pt }
  | { kind: "remove_fixture"; point: Pt }
  | { kind: "remove_door"; point: Pt }
  | { kind: "override"; target: "room" | "door"; index: number; value: boolean };

type Sheet = {
  page: number;
  title: string | null;
  name: string;
  annexe: boolean;
};

type Dossier = {
  id: string;
  sheets: Sheet[];
};

type PlanReading = {
  id: string;
  page: number;
  name: string;
  checked: boolean;
  reason: string | null;
  width: number;
  height: number;
  scale: string | null;
  kind: "vector" | "picture" | null;
  scale_source: string | null;
  px_per_m: number | null;
  pt_per_plan_px: number | null;
  corrections: Correction[];
  rooms: Room[];
  fixtures?: Fixture[];
  accessible_wc?: boolean | null;
  doors?: Door[];
  doors_ok?: boolean | null;
  walk?: Walk | null;
  warnings: string[];
};

type ExplainFailure = {
  id: string;
  kind: string;
  subject: string;
  reason: string;
  fix: string;
  source: "muse-spark" | "template";
  verify:
    | { status: "verified"; agree: boolean; confidence: number; note: string; doubtful: boolean }
    | { status: "not_verified" };
};

type ExplainResult = {
  failures: ExplainFailure[];
  explained_by: string | null;
  verified_by: string | null;
};

const DOOR_COLOURS = { ok: "#2e7d32", bad: "#c62828", unchecked: "#868e96" };

function doorColour(door: Door) {
  return door.ok === null ? DOOR_COLOURS.unchecked : door.ok ? DOOR_COLOURS.ok : DOOR_COLOURS.bad;
}

function doorSides(door: Door, rooms: Room[]) {
  return door.rooms
    .map((i) => (i === null ? "outside the rooms" : roomLabel(rooms[i], i)))
    .join(" ↔ ");
}

const TYPE_COLOURS: Record<string, string> = {
  living: "#f4a261",
  bedroom: "#8ab17d",
  kitchen: "#e9c46a",
  bathroom: "#4ea8de",
  wc: "#2a6f97",
  corridor: "#b5a1d9",
  entrance: "#d4a5a5",
  storage: "#adb5bd",
  other: "#ced4da",
};

const FIXTURE_COLOURS: Record<Fixture["kind"], string> = {
  placard: "#6c757d",
  appliance: "#e09f3e",
  washbasin: "#1971c2",
  toilet: "#1971c2",
};

function fixtureSummary(fixtures: Fixture[], indices: number[] | undefined) {
  const counts = new Map<string, number>();
  for (const i of indices ?? []) {
    const kind = fixtures[i]?.kind;
    if (kind) counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts].map(([kind, n]) => (n === 1 ? kind : `${n} ${kind}s`)).join(", ");
}

const SOURCE_TEXT: Record<Room["type_source"], string> = {
  text: "name on the plan",
  fixture: "toilet drawn",
  muse: "Muse Spark",
  none: "unknown",
};

const SCALE_TEXT: Record<string, string> = {
  measured: "measured from the dimension lines",
  scale: "from the written scale",
  assumed: "assumed",
  cote: "from a written dimension",
  from_areas: "from the written areas",
};

function roomLabel(room: Room, i: number) {
  return room.name || `Room ${i + 1}`;
}

type Stage = { stage: string; batch?: number; of?: number };

function stageText({ stage, batch, of }: Stage) {
  switch (stage) {
    case "reading": return "Muse Spark is reading the plan";
    case "measuring": return "Measuring the rooms against the drawn walls";
    case "typing": return "Muse Spark is typing the unnamed rooms";
    case "segmenting": return "SAM 3.1 is outlining the rooms";
    case "scale": return "Muse Spark is reading a dimension for the scale";
    case "fixtures": return "Muse Spark is finding the fixtures";
    case "outlining": return `SAM 3.1 is outlining the fixtures ${batch}/${of}`;
    default: return "Working";
  }
}

// The check streams its stages as NDJSON (issue #12): one line per stage as it starts,
// heartbeats while a long one runs, then the result or an error.
async function streamed<T>(response: Response, onStage: (stage: Stage) => void): Promise<T> {
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `The server answered ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffered += value;
    const lines = buffered.split("\n");
    buffered = done ? "" : lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if ("result" in event) return event.result as T;
      if ("error" in event) throw new Error(event.error);
      if ("stage" in event) onStage(event);
    }
    if (done) throw new Error("The server stopped before answering.");
  }
}

const NDJSON = { Accept: "application/x-ndjson" };

export function PlanIntake() {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [reading, setReading] = useState<PlanReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"none" | "merge" | "wall" | "remove" | "door" | "walk">("none");
  // Walk the plan (issue #14): the route, and how many of its legs the icon has rolled.
  const [explain, setExplain] = useState<ExplainResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [walk, setWalk] = useState<Walk | null>(null);
  const [clock, setClock] = useState(0);
  const [playing, setPlaying] = useState(false);

  function play(next: Walk | null) {
    setWalk(next);
    setClock(0);
    setPlaying(Boolean(next && next.route.length > 1));
  }

  function show(body: PlanReading) {
    setReading(body);
    setExplain(null);
    play(body.walk ?? null);
  }

  // Explain + verify (issue #16): a human sentence and a second opinion per failure.
  async function explainFailures() {
    if (!reading) return;
    setExplaining(true);
    setError(null);
    try {
      const response = await fetch(`/api/plans/${reading.id}/sheets/${reading.page}/explain`);
      const body = await response.json().catch(() => null);
      if (!response.ok || !body) {
        setError(body?.detail ?? `Explaining the failures failed (${response.status})`);
        return;
      }
      setExplain(body as ExplainResult);
    } catch {
      setError("Could not reach the ConformScope server.");
    } finally {
      setExplaining(false);
    }
  }

  useEffect(() => {
    if (!playing || !walk) return;
    const legs = walk.route.length - 1;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      setClock((c) => {
        const next = Math.min(legs, c + dt / STEP_MS);
        if (next >= legs) setPlaying(false);
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, walk]);

  async function walkFrom(room: number) {
    if (!reading) return;
    try {
      const response = await fetch(`/api/plans/${reading.id}/sheets/${reading.page}/walk?from=${room}`);
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        setError(body?.detail ?? `Walking the plan failed (${response.status})`);
        return;
      }
      play(body);
      setMode("none");
    } catch {
      setError("Could not reach the ConformScope server.");
    }
  }

  // Where the icon is, and what it has passed so far.
  const legs = walk ? walk.route.length - 1 : 0;
  const at = Math.min(Math.floor(clock), Math.max(legs, 0));
  const icon: Pt | null = (() => {
    if (!walk || walk.route.length === 0) return null;
    const a = walk.route[at].point_px;
    const b = walk.route[Math.min(at + 1, legs)].point_px;
    const f = clock - at;
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
  })();
  const passed = walk ? walk.route.slice(0, at + 1) : [];
  const reachedSoFar = new Set(passed.filter((s) => s.event === "enter").map((s) => s.room));
  const stopsSoFar = passed.filter((s) => s.event === "blocked_door" || s.event === "cannot_turn");
  const [pending, setPending] = useState<Pt | null>(null);
  const [stage, setStage] = useState<Stage | null>(null);

  function failed(error: unknown) {
    setError(error instanceof TypeError ? "Could not reach the ConformScope server." : String((error as Error).message));
  }

  async function postCorrections(corrections: Correction[]) {
    if (!reading) return;
    setBusy(true);
    setError(null);
    setStage(null);
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
      failed(error);
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  function onPlanClick(event: MouseEvent<SVGSVGElement>) {
    if (!reading || mode === "none" || busy) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const xPx = ((event.clientX - rect.left) / rect.width) * reading.width;
    const yPx = ((event.clientY - rect.top) / rect.height) * reading.height;
    if (mode === "walk") {
      const room = reading.rooms.findIndex((r) => insidePolygon([xPx, yPx], r.polygon_px));
      if (room >= 0) walkFrom(room);
      return;
    }
    const f = reading.pt_per_plan_px ?? 1;
    const pt: Pt = [Math.round(xPx * f * 10) / 10, Math.round(yPx * f * 10) / 10];
    if (mode === "remove") {
      postCorrections([...reading.corrections, { kind: "remove_fixture", point: pt }]);
      return;
    }
    if (mode === "door") {
      postCorrections([...reading.corrections, { kind: "remove_door", point: pt }]);
      return;
    }
    if (!pending) {
      setPending(pt);
      return;
    }
    if (mode === "merge") {
      // First click: the room that stays. Second: the nook it claims.
      postCorrections([...reading.corrections, { kind: "merge", point: pt, target_point: pending }]);
    } else {
      postCorrections([...reading.corrections, { kind: "wall", start: pending, end: pt }]);
    }
  }

  // A sheet is checked the first time it is opened, then kept (issue #11).
  async function openSheet(id: string, sheet: number) {
    setBusy(true);
    setError(null);
    setReading(null);
    setPage(sheet);
    setMode("none");
    setPending(null);
    setStage(null);
    try {
      const response = await fetch(`/api/plans/${id}/sheets/${sheet}`, { headers: NDJSON });
      show(await streamed<PlanReading>(response, setStage));
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setReading(null);
    setDossier(null);
    setPage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/plans", { method: "POST", body: form });
      const body: Dossier | null = await response.json().catch(() => null);
      if (!response.ok || !body) {
        setError((body as { detail?: string } | null)?.detail ?? `Upload failed (${response.status})`);
        setBusy(false);
        return;
      }
      setDossier(body);
      const first = body.sheets.find((sheet) => !sheet.annexe) ?? body.sheets[0];
      await openSheet(body.id, first.page);
    } catch {
      setError("Could not reach the ConformScope server.");
      setBusy(false);
    }
  }

  return (
    <div className={styles.intake}>
      <label className={styles.drop}>
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload(file);
          }}
        />
        {busy ? "Reading and measuring the plan…" : "Drop a plan or a whole building (PDF or image)"}
      </label>

      {busy && (
        <p role="status" className={styles.muted}>
          {/* Indeterminate: the bar says work is going on, the stage says which. */}
          <progress aria-label="Checking the sheet" style={{ width: "100%" }} />
          <br />
          {stage ? `${stageText(stage)}…` : "Starting…"}
        </p>
      )}

      {dossier && dossier.sheets.length > 1 && (
        <nav className={styles.toolbar} aria-label="Sheets">
          {dossier.sheets.map((sheet) => (
            <button
              key={sheet.page}
              type="button"
              data-active={sheet.page === page}
              disabled={busy}
              title={sheet.annexe ? "Not checked: a plan annexe" : (sheet.title ?? undefined)}
              style={sheet.annexe ? { opacity: 0.55 } : undefined}
              onClick={() => openSheet(dossier.id, sheet.page)}
            >
              {sheet.name}
            </button>
          ))}
          <span className={styles.muted}>
            {dossier.sheets.length} sheets · {dossier.sheets.filter((sheet) => sheet.annexe).length} not checked
          </span>
        </nav>
      )}

      {error && <p role="alert" className={styles.error}>{error}</p>}

      {reading && reading.checked && (
        <div className={styles.toolbar}>
          <button
            type="button"
            data-active={mode === "merge"}
            disabled={busy}
            onClick={() => { setMode(mode === "merge" ? "none" : "merge"); setPending(null); }}
          >
            Merge a nook into a room
          </button>
          <button
            type="button"
            data-active={mode === "wall"}
            disabled={busy}
            onClick={() => { setMode(mode === "wall" ? "none" : "wall"); setPending(null); }}
          >
            Draw a missing wall
          </button>
          <button
            type="button"
            data-active={mode === "remove"}
            disabled={busy || !reading.fixtures?.length}
            onClick={() => { setMode(mode === "remove" ? "none" : "remove"); setPending(null); }}
          >
            Remove a fixture
          </button>
          <button
            type="button"
            data-active={mode === "door"}
            disabled={busy || !reading.doors?.length}
            onClick={() => { setMode(mode === "door" ? "none" : "door"); setPending(null); }}
          >
            Remove a door
          </button>
          <button
            type="button"
            data-active={mode === "walk"}
            disabled={busy || reading.rooms.length === 0}
            onClick={() => { setMode(mode === "walk" ? "none" : "walk"); setPending(null); }}
          >
            Start the walk here
          </button>
          <button
            type="button"
            disabled={busy || reading.corrections.length === 0}
            onClick={() => postCorrections([])}
          >
            Clear corrections
          </button>
          <span className={styles.muted}>
            {mode === "merge" && (pending ? "Now click the nook to merge into it." : "Click the room that stays.")}
            {mode === "wall" && (pending ? "Now click the other end of the wall." : "Click one end of the missing wall.")}
            {mode === "remove" && "Click the fixture that is not there."}
            {mode === "door" && "Click inside the swing of the door that is not there."}
            {mode === "walk" && "Click the room the wheelchair starts in."}
            {mode === "none" && `${reading.corrections.length} correction${reading.corrections.length === 1 ? "" : "s"} saved`}
          </span>
        </div>
      )}

      {reading && (
        <section className={styles.result}>
          <div className={styles.plan}>
            {/* eslint-disable-next-line @next/next/no-img-element -- served by our API, sized by the plan */}
            <img src={`/api/plans/${reading.id}/sheets/${reading.page}/image`} alt={`Sheet ${reading.name}`} />
            <svg
              className={styles.overlay}
              viewBox={`0 0 ${reading.width} ${reading.height}`}
              onClick={onPlanClick}
              style={{ cursor: mode === "none" ? undefined : "crosshair" }}
            >
              {reading.rooms.map((room, i) => (
                <polygon
                  key={i}
                  points={room.polygon_px.map(([x, y]) => `${x},${y}`).join(" ")}
                  fill={TYPE_COLOURS[room.room_type] ?? TYPE_COLOURS.other}
                  fillOpacity={0.45}
                  stroke={room.warnings.length ? "#d32f2f" : "#1d3557"}
                  strokeWidth={room.warnings.length ? 4 : 2}
                >
                  <title>{roomLabel(room, i)}</title>
                </polygon>
              ))}
              {(reading.fixtures ?? []).map((fixture, i) => (
                <polygon
                  key={`fixture-${i}`}
                  points={fixture.polygon_px.map(([x, y]) => `${x},${y}`).join(" ")}
                  fill={FIXTURE_COLOURS[fixture.kind]}
                  fillOpacity={0.25}
                  stroke={FIXTURE_COLOURS[fixture.kind]}
                  strokeWidth={2}
                >
                  <title>{fixture.outline_source === "vector" ? fixture.kind : `${fixture.kind} (outlined by ${fixture.outline_source === "sam" ? "SAM 3.1" : "Muse Spark"})`}</title>
                </polygon>
              ))}
              {(reading.fixtures ?? []).map((fixture, i) =>
                fixture.space && fixture.space.polygon_px.length > 0 ? (
                  <polygon
                    key={`space-${i}`}
                    points={fixture.space.polygon_px.map(([x, y]) => `${x},${y}`).join(" ")}
                    fill={fixture.space.fits ? "#2e7d32" : "#c62828"}
                    fillOpacity={0.15}
                    stroke={fixture.space.fits ? "#2e7d32" : "#c62828"}
                    strokeWidth={3}
                    strokeDasharray={fixture.space.to_confirm ? "8 6" : undefined}
                  >
                    <title>{fixture.space.verdict}</title>
                  </polygon>
                ) : null,
              )}
              {(reading.doors ?? []).map((door, i) => (
                <line
                  key={`door-${i}`}
                  x1={door.doorway_px[0][0]}
                  y1={door.doorway_px[0][1]}
                  x2={door.doorway_px[1][0]}
                  y2={door.doorway_px[1][1]}
                  stroke={doorColour(door)}
                  strokeWidth={9}
                  strokeLinecap="round"
                >
                  <title>{`${doorSides(door, reading.rooms)} · ${door.verdict}`}</title>
                </line>
              ))}
              {walk && reading.rooms.map((room, i) =>
                reachedSoFar.has(i) ? (
                  <polygon
                    key={`reached-${i}`}
                    points={room.polygon_px.map(([x, y]) => `${x},${y}`).join(" ")}
                    fill="#2e7d32"
                    fillOpacity={0.12}
                    stroke="#2e7d32"
                    strokeWidth={5}
                    pointerEvents="none"
                  />
                ) : null,
              )}
              {stopsSoFar.map((step, i) => (
                <g key={`stop-${i}`} pointerEvents="none">
                  <circle cx={step.point_px[0]} cy={step.point_px[1]} r={20} fill="#c62828" />
                  <text x={step.point_px[0]} y={step.point_px[1] + 9} textAnchor="middle" fontSize={26}
                        fontWeight={700} fill="#fff">!</text>
                </g>
              ))}
              {icon && (
                <g pointerEvents="none" transform={`translate(${icon[0]} ${icon[1]})`}>
                  <circle r={24} fill="#1d3557" stroke="#fff" strokeWidth={4} />
                  <text y={10} textAnchor="middle" fontSize={28} fill="#fff">♿</text>
                </g>
              )}
              {reading.rooms.map((room, i) =>
                room.circle_px && room.circle_m !== null && reading.px_per_m ? (
                  <circle
                    key={`circle-${i}`}
                    cx={room.circle_px[0]}
                    cy={room.circle_px[1]}
                    r={(room.circle_m / 2) * reading.px_per_m}
                    fill={room.conforme ? "#2e7d32" : "#c62828"}
                    fillOpacity={0.18}
                    stroke={room.conforme ? "#2e7d32" : "#c62828"}
                    strokeWidth={3}
                  >
                    <title>{room.verdict ?? roomLabel(room, i)}</title>
                  </circle>
                ) : null,
              )}
            </svg>
          </div>

          <aside>
            {!reading.checked && <p className={styles.muted}>{reading.reason}</p>}
            <h2>{reading.name} · {reading.rooms.length} rooms measured</h2>
            <p className={styles.muted}>
              Scale: {reading.scale ?? "not written"}
              {reading.scale_source && ` · ${SCALE_TEXT[reading.scale_source] ?? reading.scale_source}`}
            </p>
            {reading.accessible_wc != null && (
              <p className={reading.accessible_wc ? styles.badgeOk : styles.badgeBad}>
                {reading.accessible_wc
                  ? "Accessible WC: a toilet has a 0.80 × 1.30 m transfer space"
                  : "No toilet has a 0.80 × 1.30 m transfer space"}
              </p>
            )}
            {walk && walk.route.length > 0 && (
              <>
                <p className={walk.unreachable.length === 0 && walk.stops.length === 0 ? styles.badgeOk : styles.badgeBad}>
                  ♿ {walk.verdict}
                </p>
                <p>
                  <button type="button" onClick={() => play(walk)} disabled={playing}>
                    {clock > 0 ? "Replay the walk" : "Play the walk"}
                  </button>
                </p>
                {walk.stops.length > 0 && (
                  <ul className={styles.warnings}>
                    {walk.stops.map((stop, i) => (
                      <li key={i}>
                        {stop.kind === "door"
                          ? `Stopped at a door: ${stop.reason}`
                          : `${roomLabel(reading.rooms[stop.room ?? 0], stop.room ?? 0)}: ${stop.reason}`}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
            {reading.doors_ok != null && (() => {
              const doors = reading.doors ?? [];
              const judged = doors.filter((door) => door.ok !== null);
              const narrow = judged.filter((door) => !door.ok);
              return (
                <>
                  <p className={reading.doors_ok ? styles.badgeOk : styles.badgeBad}>
                    {reading.doors_ok
                      ? `All ${judged.length} doors are wide enough`
                      : `${narrow.length} door${narrow.length === 1 ? " is" : "s are"} too narrow`}
                  </p>
                  {narrow.length > 0 && (
                    <ul className={styles.warnings}>
                      {narrow.map((door) => {
                        const doorIndex = doors.indexOf(door);
                        return (
                          <li key={doorIndex}>
                            {doorSides(door, reading.rooms)}: {door.width_m.toFixed(2)} m, needs{" "}
                            {door.required_m?.toFixed(2)} m
                            {door.role === "entrance" && " (read as the entrance)"}{" "}
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() =>
                                postCorrections([
                                  ...reading.corrections,
                                  { kind: "override", target: "door", index: doorIndex, value: true },
                                ])
                              }
                            >
                              Override: mark wide enough
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </>
              );
            })()}
            {!explain ? (
              <p>
                <button type="button" onClick={explainFailures} disabled={explaining || busy}>
                  {explaining ? "Explaining…" : "Explain the failures"}
                </button>{" "}
                <span className={styles.muted}>
                  A plain-language reason and fix for each failure, double-checked by
                  Muse Spark Open.
                </span>
              </p>
            ) : explain.failures.length === 0 ? (
              <p className={styles.badgeOk}>Nothing to explain: every check passed.</p>
            ) : (
              <>
                <h3>Why it fails, and how to fix it</h3>
                <ul className={styles.warnings}>
                  {explain.failures.map((failure) => (
                    <li key={failure.id}>
                      <strong>{failure.subject}</strong>
                      <br />
                      {failure.reason}
                      <br />
                      <em>Fix: {failure.fix}</em>
                      <br />
                      {failure.verify.status === "verified" ? (
                        failure.verify.doubtful ? (
                          <span className={styles.badgeBad}>
                            ⚠ Doubtful — the verifier{" "}
                            {failure.verify.agree ? "is unsure" : "disagrees"} (
                            {Math.round(failure.verify.confidence * 100)}%):{" "}
                            {failure.verify.note}
                          </span>
                        ) : (
                          <span className={styles.badgeOk}>
                            ✓ Verified by Muse Spark Open (
                            {Math.round(failure.verify.confidence * 100)}%)
                          </span>
                        )
                      ) : (
                        <span className={styles.muted}>Not verified (no verifier key).</span>
                      )}{" "}
                      <span className={styles.muted}>
                        {failure.source === "template" ? "Written from the measurements." : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {reading.warnings.length > 0 && (
              <ul className={styles.warnings}>
                {reading.warnings.map((warning, i) => (
                  <li key={i}>⚠ {warning}</li>
                ))}
              </ul>
            )}
            <ol className={styles.rooms}>
              {reading.rooms.map((room, i) => (
                <li key={i}>
                  <strong>
                    <span
                      className={styles.swatch}
                      style={{ background: TYPE_COLOURS[room.room_type] ?? TYPE_COLOURS.other }}
                    />
                    {roomLabel(room, i)}
                  </strong>
                  <span>
                    {room.room_type} ({SOURCE_TEXT[room.type_source]})
                    {room.area_m2 !== null && ` · ${room.area_m2} m²`}
                    {room.written_area_m2 !== null && ` (written ${room.written_area_m2} m²)`}
                  </span>
                  {room.doors && room.doors.length > 0 && (
                    <span>
                      {room.doors.length} door{room.doors.length === 1 ? "" : "s"}
                    </span>
                  )}
                  {room.fixtures && room.fixtures.length > 0 && (
                    <span>Fixtures: {fixtureSummary(reading.fixtures ?? [], room.fixtures)}</span>
                  )}
                  {(room.fixtures ?? []).map((f) => {
                    const space = reading.fixtures?.[f]?.space;
                    return space ? (
                      <span key={`space-${f}`} className={space.fits ? styles.badgeOk : styles.badgeBad}>
                        {space.verdict}
                      </span>
                    ) : null;
                  })}
                  {room.verdict && (
                    <span className={room.conforme ? styles.badgeOk : styles.badgeBad}>{room.verdict}</span>
                  )}
                  {room.conforme !== null && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        postCorrections([
                          ...reading.corrections,
                          { kind: "override", target: "room", index: i, value: !room.conforme },
                        ])
                      }
                    >
                      {room.conforme ? "Override: mark not conforme" : "Override: mark conforme"}
                    </button>
                  )}
                  {room.outline_source !== "auto" && (
                    <span className={styles.badgeHand}>corrected by hand</span>
                  )}
                  {room.warnings.map((warning, j) => (
                    <span key={j} className={styles.error}>⚠ {warning}</span>
                  ))}
                </li>
              ))}
            </ol>
          </aside>
        </section>
      )}
    </div>
  );
}
