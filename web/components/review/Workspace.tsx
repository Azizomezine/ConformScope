"use client";

import { useSyncExternalStore } from "react";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

/** Below this width the panes stack instead of sitting side by side. */
const NARROW = "(max-width: 899px)";

function useNarrow(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const q = window.matchMedia(NARROW);
      q.addEventListener("change", onChange);
      return () => q.removeEventListener("change", onChange);
    },
    () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(NARROW).matches,
    () => false,
  );
}

/**
 * The check screen's panes, left to right: the plan, the rooms, and the report (ported
 * from pmr-checker). On a desktop they are resizable side by side; on a narrow screen
 * they stack, plan first, and the page scrolls.
 */
export default function Workspace({ plan, rooms, report, reportOpen }: {
  plan: React.ReactNode;
  rooms: React.ReactNode;
  report: React.ReactNode;
  reportOpen: boolean;
}) {
  const narrow = useNarrow();

  if (narrow) {
    return (
      <div className="workspace flex flex-1 flex-col overflow-y-auto">
        <div className="h-[60vh] flex-none">{plan}</div>
        {reportOpen && <div className="border-t border-border">{report}</div>}
        <div className="border-t border-border">{rooms}</div>
      </div>
    );
  }

  return (
    <ResizablePanelGroup orientation="horizontal" className="workspace min-h-0 flex-1">
      <ResizablePanel id="plan" defaultSize={reportOpen ? "52" : "70"} minSize="30">
        {plan}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="rooms" defaultSize={reportOpen ? "24" : "30"} minSize="18" maxSize="45">
        {rooms}
      </ResizablePanel>
      {reportOpen && (
        <>
          <ResizableHandle withHandle />
          <ResizablePanel id="report" defaultSize="24" minSize="16" maxSize="40">
            {report}
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
  );
}

/** A pane's own header row, the same height in every pane. */
export function PaneHeader({ icon, title, children }: {
  icon?: React.ReactNode;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex h-10 flex-none items-center justify-between gap-2 border-b border-border px-3">
      <h2 className="flex items-center gap-2 text-sm font-medium [&_svg]:size-4 [&_svg]:text-muted-foreground">
        {icon}{title}
      </h2>
      {children}
    </div>
  );
}
