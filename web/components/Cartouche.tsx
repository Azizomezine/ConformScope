import { cn } from "@/lib/utils";

/* The cartouche is a drawing's title block: a stack of ruled cells, each headed in the
   narrow lettering a draughtsman would use. Every block in the report pane is one of
   these cells, so they share one rhythm (ported from pmr-checker). */

export function Block({ className, ...props }: React.ComponentProps<"section">) {
  return <section className={cn("border-b border-border px-4 py-4", className)} {...props} />;
}

/** A cell's heading. */
export function Key({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "key font-lettering text-[10.5px] font-semibold uppercase tracking-[.14em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

/** A verdict as a pill: viridian when it passes, vermilion when it fails, grey when
 *  nothing was checked. The verdict colours mean pass and fail and nothing else. */
export function Mark({ ok, children, className }: {
  ok: boolean | null;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn(
      "mark inline-flex min-h-5 items-center gap-1 rounded-md border px-1.5 text-[11px] font-medium [&_svg]:size-3",
      ok === null ? "border-transparent bg-secondary text-muted-foreground"
        : ok ? "border-conforme/50 text-conforme" : "border-non-conforme/50 text-non-conforme",
      className)}>
      {children}
    </span>
  );
}
