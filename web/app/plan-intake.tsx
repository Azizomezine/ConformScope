"use client";

import { useState, type MouseEvent } from "react";
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
  warnings: string[];
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

type Correction =
  | { kind: "merge"; point: Pt; target_point: Pt }
  | { kind: "wall"; start: Pt; end: Pt }
  | { kind: "remove_fixture"; point: Pt };

type PlanReading = {
  id: string;
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
  warnings: string[];
};

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

export function PlanIntake() {
  const [reading, setReading] = useState<PlanReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"none" | "merge" | "wall" | "remove">("none");
  const [pending, setPending] = useState<Pt | null>(null);

  async function postCorrections(corrections: Correction[]) {
    if (!reading) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/plans/${reading.id}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        setError(body?.detail ?? `Saving the correction failed (${response.status})`);
        return;
      }
      setReading(body);
      setPending(null);
      setMode("none");
    } catch {
      setError("Could not reach the ConformScope server.");
    } finally {
      setBusy(false);
    }
  }

  function onPlanClick(event: MouseEvent<SVGSVGElement>) {
    if (!reading || mode === "none" || busy) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const xPx = ((event.clientX - rect.left) / rect.width) * reading.width;
    const yPx = ((event.clientY - rect.top) / rect.height) * reading.height;
    const f = reading.pt_per_plan_px ?? 1;
    const pt: Pt = [Math.round(xPx * f * 10) / 10, Math.round(yPx * f * 10) / 10];
    if (mode === "remove") {
      postCorrections([...reading.corrections, { kind: "remove_fixture", point: pt }]);
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

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setReading(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/plans", { method: "POST", body: form });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        setError(body?.detail ?? `Upload failed (${response.status})`);
        return;
      }
      setReading(body);
    } catch {
      setError("Could not reach the ConformScope server.");
    } finally {
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
        {busy ? "Reading and measuring the plan…" : "Drop a plan (PDF or image)"}
      </label>

      {error && <p role="alert" className={styles.error}>{error}</p>}

      {reading && (
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
            disabled={busy || reading.corrections.length === 0}
            onClick={() => postCorrections([])}
          >
            Clear corrections
          </button>
          <span className={styles.muted}>
            {mode === "merge" && (pending ? "Now click the nook to merge into it." : "Click the room that stays.")}
            {mode === "wall" && (pending ? "Now click the other end of the wall." : "Click one end of the missing wall.")}
            {mode === "remove" && "Click the fixture that is not there."}
            {mode === "none" && `${reading.corrections.length} correction${reading.corrections.length === 1 ? "" : "s"} saved`}
          </span>
        </div>
      )}

      {reading && (
        <section className={styles.result}>
          <div className={styles.plan}>
            {/* eslint-disable-next-line @next/next/no-img-element -- served by our API, sized by the plan */}
            <img src={`/api/plans/${reading.id}/image`} alt="Uploaded plan" />
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
            <h2>{reading.rooms.length} rooms measured</h2>
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
