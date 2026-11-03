"use client";

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { Block } from "@/components/Cartouche";
import { Button } from "@/components/ui/button";
import { usePreferences } from "@/app/preferences";

/** The auditor's "I'm done reviewing, give me the report" moment (ported from
 *  pmr-checker): downloads the PDF the server builds from the stored readings of every
 *  sheet checked so far, corrections and overrides included. It never measures again. */
export default function ExportReport({ planId, fileName }: {
  planId: string;
  /** The file the auditor uploaded: the report's title. */
  fileName?: string | null;
}) {
  const { t } = usePreferences();
  const [busy, setBusy] = useState(false);
  const [fault, setFault] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setFault(null);
    try {
      const query = fileName ? `?name=${encodeURIComponent(fileName)}` : "";
      const response = await fetch(`/api/plans/${planId}/report.pdf${query}`);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? t("export.serverAnswered", { status: response.status }));
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `conformscope-report-${(fileName ?? planId).replace(/\.[^.]+$/, "")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setFault(t("export.failed", { detail: error instanceof TypeError ? t("export.unreachable") : (error as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Block>
      <Button type="button" className="w-full font-lettering uppercase tracking-[.12em]"
              onClick={download} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <FileDown />}
        {busy ? t("export.busy") : t("export.button")}
      </Button>
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        {t("export.body")}
      </p>
      {fault && <p className="fault mt-2 text-xs text-destructive" role="alert">{fault}</p>}
    </Block>
  );
}
