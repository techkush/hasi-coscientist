"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Play, FileText, Download, Loader2, AlertTriangle, BarChart3,
} from "lucide-react";
import { PanelShell } from "./panel-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { trpc } from "@/lib/trpc";
import type { StageRow, TaskState } from "@/server/conductor";

export function AnalyzePanel({
  slug, task, stage,
}: { slug: string; task?: TaskState; stage?: StageRow }) {
  const utils = trpc.useUtils();
  const reportUrlQ = trpc.analyze.reportUrl.useQuery({ slug });
  const keptQ = trpc.analyze.keptCount.useQuery({ slug }, { refetchInterval: 3000 });
  const execMut = trpc.analyze.execute.useMutation({
    onSuccess: (r) => {
      if (r.ok) toast.success("Generating report…");
      else if (r.reason === "need-at-least-2-keeps") setShowNoResults(true);
    },
    onError: (e) => toast.error(e.message),
  });

  const [showNoResults, setShowNoResults] = React.useState(false);
  const busy = !!task?.active && task?.slug === slug && task?.stage === "analyze";

  const prevBusy = React.useRef(busy);
  React.useEffect(() => {
    if (prevBusy.current && !busy) {
      utils.projects.detail.invalidate({ slug });
      utils.analyze.summary.invalidate({ slug });
    }
    prevBusy.current = busy;
  }, [busy, slug, utils]);
  const reportUrl = reportUrlQ.data as string | undefined;
  const enabled = stage?.enabled ?? false;
  const done = stage?.done ?? false;
  const kept = keptQ.data ?? 0;

  return (
    <PanelShell
      title="Analyze & report"
      subtitle="Summarize the loop run and generate report.pdf."
      actions={
        <>
          {done && reportUrl && (
            <>
              <Button asChild size="sm" variant="outline" className="gap-1.5">
                <a href={reportUrl} target="_blank" rel="noreferrer">
                  <Download className="h-3.5 w-3.5" />
                  Download report.pdf
                </a>
              </Button>
              <Button asChild size="sm" variant="outline" className="gap-1.5">
                <a href={reportUrl} target="_blank" rel="noreferrer">
                  <FileText className="h-3.5 w-3.5" />
                  Open in new tab
                </a>
              </Button>
            </>
          )}
          <Button
            size="sm"
            onClick={() => {
              if (kept < 2) { setShowNoResults(true); return; }
              execMut.mutate({ slug });
            }}
            disabled={!enabled || busy || execMut.isPending}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {busy ? "Generating…" : done ? "Regenerate" : "Generate report"}
          </Button>
        </>
      }
    >
      {done && reportUrl ? (
        <iframe
          src={reportUrl}
          title="report.pdf"
          className="h-full w-full"
          style={{ border: "0", background: "var(--muted)" }}
        />
      ) : (
        <ScrollArea className="h-full thin-scroll">
          <div className="mx-auto max-w-4xl px-8 py-6 space-y-5">
            {!busy && (
              <Card className="p-4 flex items-start gap-3">
                <BarChart3 className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold">Ready to summarise</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    We'll read <code>results.tsv</code>, count keeps and reverts, render per-metric
                    charts, and write a single-page <code>report.pdf</code>.
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Detected <b className="text-foreground">{kept}</b> kept run{kept === 1 ? "" : "s"} so far.
                  </p>
                </div>
              </Card>
            )}

            {busy && (
              <div className="flex items-center gap-2 rounded-md border border-border bg-card p-3 text-sm">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                {task?.message ?? "Generating the report…"}
              </div>
            )}
          </div>
        </ScrollArea>
      )}

      <Dialog open={showNoResults} onOpenChange={setShowNoResults}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive" />
              No kept results yet
            </DialogTitle>
            <DialogDescription>
              The report needs at least <b>2</b> experiments with status&nbsp;
              <code>keep</code> in <code>results.tsv</code>. There{" "}
              {kept === 1 ? "is currently 1" : `are currently ${kept}`}.
              Run the loop to gather more results, then try again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={() => setShowNoResults(false)}>Got it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PanelShell>
  );
}

