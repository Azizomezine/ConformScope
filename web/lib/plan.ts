/* What the ConformScope API sends about a dossier and its sheets, and the few calls
   the check screen makes. Every point is in plan-image pixels: the sheet's PNG is the
   drawing, and its width × height is the SVG viewBox. */

export type Pt = [number, number];

export type Room = {
  name: string;
  room_type: string;
  type_source: "text" | "fixture" | "muse" | "none";
  area_m2: number | null;
  written_area_m2: number | null;
  polygon_px: Pt[];
  circle_m: number | null;
  circle_px: Pt | null;
  conforme: boolean | null;
  max_diameter_m: number | null;
  verdict: string | null;
  outline_source: string;
  fixtures?: number[];
  doors?: number[];
  warnings: string[];
};

export type Door = {
  rooms: [number | null, number | null];
  role: "interior" | "entrance" | "communs";
  width_m: number;
  measured_m: number;
  required_m: number | null;
  ok: boolean | null;
  verdict: string;
  doorway_px: Pt[];
  swing_px: Pt;
};

export type Space = {
  kind: "transfer" | "washbasin";
  fits: boolean;
  verdict: string;
  to_confirm: boolean;
  polygon_px: Pt[];
};

export type Fixture = {
  kind: "placard" | "appliance" | "washbasin" | "toilet";
  room: number | null;
  polygon_px: Pt[];
  outline_source: string;
  space: Space | null;
};

export type WalkStep = {
  point_px: Pt;
  room: number | null;
  door: number | null;
  event: "start" | "enter" | "through" | "back" | "blocked_door" | "cannot_turn";
};

export type Walk = {
  start: { room: number | null; door: number | null } | null;
  reached: number[];
  unreachable: { room: number; blocked_by: number | null }[];
  stops: { kind: "door" | "turn"; door: number | null; room: number | null; reason: string }[];
  route: WalkStep[];
  verdict: string;
};

export type Correction =
  | { kind: "merge"; point: Pt; target_point: Pt }
  | { kind: "wall"; start: Pt; end: Pt }
  | { kind: "remove_fixture"; point: Pt }
  | { kind: "remove_door"; point: Pt }
  | { kind: "override"; target: "room" | "door"; index: number; value: boolean };

export type Sheet = { page: number; title: string | null; name: string; annexe: boolean };

export type Dossier = { id: string; sheets: Sheet[] };

export type PlanReading = {
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

export type ExplainFailure = {
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

export type ExplainResult = {
  failures: ExplainFailure[];
  explained_by: string | null;
  verified_by: string | null;
};

/** A stage of a sheet's check, as the server streams it (issue #12). */
export type Stage = { stage: string; batch?: number; of?: number };

export const ROOM_TYPE_LABELS: Record<string, string> = {
  living: "Living room",
  bedroom: "Bedroom",
  kitchen: "Kitchen",
  bathroom: "Bathroom",
  wc: "WC",
  corridor: "Corridor",
  entrance: "Entrance",
  storage: "Storage",
  other: "Other",
};

export const SOURCE_TEXT: Record<Room["type_source"], string> = {
  text: "name on the plan",
  fixture: "toilet drawn",
  muse: "Muse Spark",
  none: "unknown",
};

export const SCALE_TEXT: Record<string, string> = {
  measured: "measured from the dimension lines",
  scale: "from the written scale",
  assumed: "assumed",
  cote: "from a written dimension",
  from_areas: "from the written areas",
};

export const REQUIRED_DIAMETER_M = 1.5;

export function roomLabel(room: Room | undefined, i: number) {
  return room?.name || `Room ${i + 1}`;
}

export function typeLabel(room: Room) {
  return ROOM_TYPE_LABELS[room.room_type] ?? room.room_type;
}

export type Verdict = "conforme" | "non-conforme" | "pas-verifie";

export const verdictOf = (room: Room): Verdict =>
  room.conforme === null ? "pas-verifie" : room.conforme ? "conforme" : "non-conforme";

/** Where a room's number is lettered and the walk enters it: its circle's centre, or
 *  the mean of its outline. */
export function centreOf(room: Room): Pt {
  if (room.circle_px) return room.circle_px;
  const n = room.polygon_px.length || 1;
  return [
    room.polygon_px.reduce((s, p) => s + p[0], 0) / n,
    room.polygon_px.reduce((s, p) => s + p[1], 0) / n,
  ];
}

export function insidePolygon([x, y]: Pt, polygon: Pt[]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function doorSides(door: Door, rooms: Room[]) {
  return door.rooms
    .map((i) => (i === null ? "outside the rooms" : roomLabel(rooms[i], i)))
    .join(" ↔ ");
}

export function fixtureSummary(fixtures: Fixture[], indices: number[] | undefined) {
  const counts = new Map<string, number>();
  for (const i of indices ?? []) {
    const kind = fixtures[i]?.kind;
    if (kind) counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts].map(([kind, n]) => (n === 1 ? kind : `${n} ${kind}s`)).join(", ");
}

export const sheetImageUrl = (id: string, page: number) => `/api/plans/${id}/sheets/${page}/image`;

export const NDJSON = { Accept: "application/x-ndjson" };

/** The check streams its stages as NDJSON (issue #12): one line per stage as it starts,
 *  heartbeats while a long one runs, then the result or an error. */
export async function streamed<T>(response: Response, onStage: (stage: Stage) => void): Promise<T> {
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

/** Send a dossier, reporting the fraction sent: fetch cannot say how far an upload
 *  has got, so this is an XMLHttpRequest. */
export function uploadDossier(file: File, onSent: (fraction: number) => void): Promise<Dossier> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/plans");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onSent(e.loaded / e.total); };
    xhr.onload = () => {
      const body = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body as Dossier);
      else reject(new Error(body?.detail ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new TypeError("Could not reach the ConformScope server."));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

/** The natural size of a sheet's image, to draw it before it is checked. */
export function sheetSize(id: string, page: number): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve([img.naturalWidth, img.naturalHeight]);
    img.onerror = () => reject(new Error("The sheet's image could not be loaded."));
    img.src = sheetImageUrl(id, page);
  });
}
