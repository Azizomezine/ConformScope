"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, LayoutGrid, Search, X } from "lucide-react";
import { PaneHeader } from "@/components/review/Workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { REQUIRED_DIAMETER_M, roomLabel, typeLabel, verdictOf, type Room, type Verdict } from "@/lib/plan";
import { cn } from "@/lib/utils";

type Filter = "all" | Verdict;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "conforme", label: "Pass" },
  { value: "non-conforme", label: "Fail" },
  { value: "pas-verifie", label: "Not checked" },
];

/** Lower-cased, accents gone: "sejour" finds "Séjour". */
const fold = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/**
 * The rooms of the sheet open, as cards (ported from pmr-checker). A card is a room,
 * never a rule: whether its turning circle fits is the only verdict it shows. What opens
 * inside a card is the page's to say, through `body`.
 */
export default function RoomsPane({ rooms, active, onPick, body, notices }: {
  rooms: Room[];
  active: number | null;
  onPick: (i: number | null) => void;
  body: (room: Room, i: number, open: boolean) => React.ReactNode;
  /** The tool's own remarks about this sheet, shown above the cards. */
  notices?: React.ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: rooms.length, conforme: 0, "non-conforme": 0, "pas-verifie": 0 };
    for (const r of rooms) c[verdictOf(r)]++;
    return c;
  }, [rooms]);

  const q = fold(query.trim());
  const shown = (r: Room, i: number) =>
    (filter === "all" || verdictOf(r) === filter) &&
    (!q || String(i + 1) === q || fold(roomLabel(r, i)).includes(q) || fold(typeLabel(r)).includes(q));
  const order = rooms.map((r, i) => (shown(r, i) ? i : -1)).filter((i) => i >= 0);
  const at = active === null ? -1 : order.indexOf(active);

  return (
    <section aria-label="Rooms" className="flex h-full min-h-0 flex-col bg-card">
      <PaneHeader icon={<LayoutGrid />} title="Rooms">
        <span className="font-mono text-xs text-muted-foreground">{rooms.length}</span>
      </PaneHeader>

      <div className="grid flex-none gap-3 border-b border-border p-3">
        <label className="relative block">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
                 aria-label="Search a room" placeholder="Search: number, name or type"
                 className="h-8 bg-background pl-8 text-xs" />
        </label>

        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="icon-sm" aria-label="Previous room"
                  disabled={order.length === 0 || at === 0}
                  onClick={() => onPick(order[at <= 0 ? order.length - 1 : at - 1])}>
            <ChevronLeft />
          </Button>
          <Select value={active === null ? "all" : String(active)}
                  onValueChange={(v) => onPick(v === "all" ? null : Number(v))}>
            <SelectTrigger size="sm" aria-label="Go to room" className="min-w-0 flex-1 bg-background text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Every room</SelectItem>
              {rooms.map((r, i) => (
                <SelectItem key={i} value={String(i)}>{i + 1} — {roomLabel(r, i)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon-sm" aria-label="Next room"
                  disabled={order.length === 0 || at === order.length - 1}
                  onClick={() => onPick(order[at + 1] ?? order[0])}>
            <ChevronRight />
          </Button>
        </div>

        <div role="radiogroup" aria-label="Filter by verdict" className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button key={f.value} type="button" role="radio" aria-checked={filter === f.value}
                    onClick={() => setFilter(f.value)}
                    className={cn(
                      "inline-flex h-6 items-center gap-1 rounded-md border border-border px-2 text-xs text-muted-foreground outline-none transition-colors",
                      "hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      "aria-checked:border-foreground/70 aria-checked:bg-secondary aria-checked:text-foreground")}>
              {filter === f.value && <Check aria-hidden className="size-3" />}
              {f.label}
              <span className="font-mono text-[10.5px] opacity-70">{counts[f.value]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="register min-h-0 flex-1 overflow-y-auto p-3 [scrollbar-width:thin]">
        {notices}

        {order.length === 0 && (
          <div className="grid place-items-center gap-2 py-10 text-center text-xs text-muted-foreground">
            {rooms.length === 0 ? "No rooms were measured on this sheet." : "No room matches."}
            {rooms.length > 0 && (
              <Button variant="ghost" size="xs" onClick={() => { setQuery(""); setFilter("all"); }}>
                <X />Show every room
              </Button>
            )}
          </div>
        )}

        <div className="grid gap-2">
          {order.map((i) => (
            <RoomCard key={i} room={rooms[i]} index={i} active={active === i}
                      onPick={() => onPick(active === i ? null : i)}>
              {body(rooms[i], i, active === i)}
            </RoomCard>
          ))}
        </div>
      </div>
    </section>
  );
}

const BADGE: Record<Verdict, { text: string; icon: React.ReactNode; className: string }> = {
  conforme: { text: "Pass", icon: <Check />, className: "border-conforme/50 text-conforme" },
  "non-conforme": { text: "Fail", icon: <X />, className: "border-non-conforme/50 text-non-conforme" },
  "pas-verifie": { text: "Not checked", icon: null, className: "border-transparent bg-secondary text-muted-foreground" },
};

const SAID: Record<Room["type_source"], string | null> = {
  text: "plan", fixture: "fixture", muse: "Muse", none: null,
};

function RoomCard({ room, index, active, onPick, children }: {
  room: Room;
  index: number;
  active: boolean;
  onPick: () => void;
  children: React.ReactNode;
}) {
  const verdict = verdictOf(room);
  const badge = BADGE[verdict];
  const said = SAID[room.type_source];

  // Picking a room on the drawing sets the same `active` this reads — the list has to
  // follow it there, or a click on a room whose card is out of view looks like nothing.
  const self = useRef<HTMLElement>(null);
  useEffect(() => {
    if (active) self.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [active]);

  return (
    <article ref={self}
             className={cn("overflow-hidden rounded-md border bg-background/50 transition-[border-color,box-shadow] duration-200 [transition-timing-function:cubic-bezier(0.23,1,0.32,1)] motion-reduce:transition-none",
                           active ? "border-primary/70 shadow-[0_0_0_1px_var(--primary)]" : "border-secondary")}>
      <button type="button" onClick={onPick} aria-expanded={active}
              className={cn(
                "entry grid w-full grid-cols-[1.75rem_1fr_auto] items-start gap-x-2 gap-y-1 px-3 py-2.5 text-left outline-none transition-colors",
                "hover:bg-secondary/70 focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-ring/50",
                active && "active bg-accent hover:bg-accent")}>
        <span className="no pt-px font-mono text-xs tabular-nums text-muted-foreground">{index + 1}</span>
        <span className="kind flex min-w-0 items-center gap-1.5 text-[13px] font-medium">
          <span className="truncate">{roomLabel(room, index)}</span>
          {said && <sup className={`said ${room.type_source}`}>{said}</sup>}
        </span>
        <span className={cn("mark inline-flex h-5 items-center gap-1 rounded-md border px-1.5 text-[11px] font-medium [&_svg]:size-3",
                            badge.className)}>
          {badge.icon}{badge.text}
        </span>
        <span className="col-start-2 col-end-4 flex flex-wrap gap-x-3 font-mono text-[11.5px] tabular-nums text-muted-foreground">
          <span>{typeLabel(room)}</span>
          {room.area_m2 !== null && <span className="area">{room.area_m2.toFixed(1)} m²</span>}
          {room.max_diameter_m !== null && (
            <span>free Ø <span className="text-foreground/80">{room.max_diameter_m.toFixed(2)} m</span></span>
          )}
          {room.conforme !== null && <span>needs Ø {REQUIRED_DIAMETER_M.toFixed(2)} m</span>}
        </span>
      </button>
      {children}
    </article>
  );
}
