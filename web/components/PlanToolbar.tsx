"use client";

import { useId, useState } from "react";
import {
  Eraser, Eye, EyeOff, Hand, Hash, MousePointer2, Pentagon, Route, Ruler, Scan,
  Square, Undo2, ZoomIn, ZoomOut, type LucideIcon,
} from "lucide-react";
import { LABELS, MeasureKind, needsScale } from "@/lib/measure";
import { cn } from "@/lib/utils";

/** What a press on the paper does. `select` is the sheet as it always was: a click
 *  opens a room, a drag pans. `pan` only ever pans, so the auditor can sweep across
 *  rooms without opening them. */
export type Tool = "select" | "pan" | MeasureKind;

export const ZOOM_MIN = 1;
export const ZOOM_MAX = 24;

const MEASURES: { kind: MeasureKind; icon: LucideIcon; hint: string }[] = [
  { kind: "distance", icon: Ruler, hint: "two clicks" },
  { kind: "perimeter", icon: Route, hint: "double-click to finish" },
  { kind: "area", icon: Pentagon, hint: "double-click to close" },
  { kind: "rectangle", icon: Square, hint: "two opposite corners" },
  { kind: "count", icon: Hash, hint: "one click per item" },
];

/**
 * The sheet's instruments, in a strip above it: zoom, the hand, the measuring tools,
 * the corrections, and the switch that lifts every overlay off the drawing.
 */
export default function PlanToolbar({
  zoom, onZoom, onFit, tool, onTool, bare, onBare,
  measureRefusal, canUndo, onUndo, canClear, onClear, extra,
}: {
  zoom: number;
  /** A new zoom factor, about the centre of the view. */
  onZoom: (k: number) => void;
  onFit: () => void;
  tool: Tool;
  onTool: (t: Tool) => void;
  /** Overlays lifted off: the plan as the architect drew it. */
  bare: boolean;
  onBare: (b: boolean) => void;
  /** Why tools that read a length are refused here, or null if they are not. A
   *  measurement on a guessed scale is a guess the eye would take for a reading. */
  measureRefusal: string | null;
  canUndo: boolean;
  onUndo: () => void;
  canClear: boolean;
  onClear: () => void;
  /** The page's own tools, after the measuring ones. */
  extra?: React.ReactNode;
}) {
  const refusedId = useId();
  const pct = Math.round(zoom * 100);
  const [draft, setDraft] = useState(String(pct));
  // The field follows the zoom whenever the zoom moves (adjusted during render).
  const [seen, setSeen] = useState(pct);
  if (seen !== pct) { setSeen(pct); setDraft(String(pct)); }

  function commit() {
    const n = Number(draft.replace(",", ".").replace("%", ""));
    if (Number.isFinite(n) && n > 0) onZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, n / 100)));
    else setDraft(String(pct));
  }

  return (
    <div role="toolbar" aria-label="Plan tools"
         className="plan-toolbar flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 text-foreground">
      <Group label="Zoom">
        <IconButton label="Zoom out" icon={ZoomOut}
                    onClick={() => onZoom(Math.max(ZOOM_MIN, zoom / 1.25))} disabled={zoom <= ZOOM_MIN} />
        <label className="flex h-7 items-center rounded-md bg-muted px-1.5 font-mono text-xs tabular-nums">
          <input aria-label="Zoom level" value={draft} inputMode="numeric"
                 className="w-9 bg-transparent text-right outline-none"
                 onChange={(e) => setDraft(e.target.value)}
                 onBlur={commit}
                 onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          <span className="text-muted-foreground">%</span>
        </label>
        <IconButton label="Zoom in" icon={ZoomIn}
                    onClick={() => onZoom(Math.min(ZOOM_MAX, zoom * 1.25))} disabled={zoom >= ZOOM_MAX} />
        <IconButton label="Whole sheet" icon={Scan} onClick={onFit} />
      </Group>

      <Divider />

      <Group label="Navigation">
        <IconButton label="Select" icon={MousePointer2}
                    pressed={tool === "select"} onClick={() => onTool("select")} />
        <IconButton label="Hand (pan without opening a room)" icon={Hand}
                    pressed={tool === "pan"} onClick={() => onTool("pan")} />
      </Group>

      <Divider />

      <Group label="Measure">
        {MEASURES.map(({ kind, icon, hint }) => {
          const refused = needsScale(kind) && measureRefusal != null;
          return (
            <IconButton key={kind} label={`${LABELS[kind]} — ${hint}`} icon={icon}
                        pressed={tool === kind} refused={refused}
                        describedBy={refused ? refusedId : undefined}
                        onClick={() => { if (!refused) onTool(tool === kind ? "select" : kind); }} />
          );
        })}
        {measureRefusal && <span id={refusedId} className="sr-only">{measureRefusal}</span>}
      </Group>

      <Divider />

      <Group label="Measurements">
        <IconButton label="Remove the last measurement" icon={Undo2} onClick={onUndo} disabled={!canUndo} />
        <IconButton label="Clear every measurement" icon={Eraser} onClick={onClear} disabled={!canClear} />
      </Group>

      {extra && <><Divider />{extra}</>}

      <div className="ml-auto" />
      <IconButton label="Hide the overlays" icon={bare ? EyeOff : Eye} pressed={bare} onClick={() => onBare(!bare)} />
    </div>
  );
}

export function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return <div role="group" aria-label={label} className="flex items-center gap-0.5">{children}</div>;
}

function Divider() {
  return <div aria-hidden className="mx-1 h-5 w-px shrink-0 bg-border" />;
}

export function IconButton({ label, icon: Icon, onClick, pressed, disabled, refused, describedBy }: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  pressed?: boolean;
  disabled?: boolean;
  /** aria-disabled, not disabled: a disabled button leaves the tab order, and with it
   *  the only place the refusal is explained. */
  refused?: boolean;
  describedBy?: string;
}) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
            disabled={disabled}
            aria-pressed={pressed}
            aria-disabled={refused || undefined}
            aria-describedby={describedBy}
            className={cn(
              "inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-[color,background-color,transform] duration-120 [transition-timing-function:cubic-bezier(0.23,1,0.32,1)] active:scale-[0.94] active:duration-100 motion-reduce:transition-none motion-reduce:active:scale-100",
              "hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
              "aria-pressed:bg-[var(--cobalt-soft)] aria-pressed:text-[var(--cobalt)]",
              "aria-disabled:cursor-not-allowed aria-disabled:opacity-40",
            )}>
      <Icon className="size-4" />
    </button>
  );
}
