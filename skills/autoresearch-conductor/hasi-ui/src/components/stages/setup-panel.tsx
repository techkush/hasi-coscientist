"use client";

import * as React from "react";
import { toast } from "sonner";
import { Play, GitBranch, CheckCircle2, Loader2, Tag, Database } from "lucide-react";
import { PanelShell } from "./panel-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { trpc } from "@/lib/trpc";
import type { StageRow, TaskState } from "@/server/conductor";

export function SetupPanel({
  slug, task, stage,
}: { slug: string; task?: TaskState; stage?: StageRow }) {
  const utils = trpc.useUtils();
  const resultQ = trpc.setup.result.useQuery({ slug }, { refetchInterval: 2000 });
  const execMut = trpc.setup.execute.useMutation({
    onSuccess: () => toast.success("Setup queued."),
    onError: (e) => toast.error(e.message),
  });

  const busy = !!task?.active && task?.slug === slug && task?.stage === "setup";
  const enabled = stage?.enabled ?? false;
  const done = stage?.done ?? false;

  // When the task stops being busy AND result has populated, the agent finished —
  // force-refresh project detail right then so the sidebar flips Setup→Done and
  // unlocks Ideas without waiting for the 2s poll tick. This is what was making
  // the user reload manually.
  const prevBusy = React.useRef(busy);
  React.useEffect(() => {
    if (prevBusy.current && !busy) {
      utils.projects.detail.invalidate({ slug });
      utils.projects.list.invalidate();
    }
    prevBusy.current = busy;
  }, [busy, slug, utils]);
  const result = (resultQ.data ?? {}) as {
    run_tag?: string; branch?: string; baseline_tag?: string;
    baseline_metric?: number; metric?: string; ok?: boolean; message?: string;
  };

  return (
    <PanelShell
      title="Setup the run"
      subtitle="Create the autoresearch branch, baseline commit, and any benchmark assets."
      actions={
        done ? (
          <Badge variant="success" className="gap-1"><CheckCircle2 className="h-3 w-3" /> Done</Badge>
        ) : (
          <Button
            size="sm"
            onClick={() => execMut.mutate({ slug })}
            disabled={!enabled || busy || execMut.isPending}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {busy ? "Setting up…" : "Execute — Setup"}
          </Button>
        )
      }
    >
      <ScrollArea className="h-full thin-scroll">
        <div className="mx-auto max-w-3xl px-8 py-6 space-y-4">
          {busy && (
            <div className="flex items-center gap-2 rounded-md border border-border bg-card p-3 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              {task?.message ?? "Preparing the run…"}
            </div>
          )}

          {!done && !busy && (
            <p className="text-sm text-muted-foreground">
              Setup commits a clean baseline on the experiment branch, runs the baseline once,
              and confirms the project is ready for the loop.
            </p>
          )}

          {done && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <KvCard icon={<GitBranch className="h-4 w-4" />} label="Branch" value={result.branch ?? `autoresearch/${result.run_tag ?? "?"}`} />
              <KvCard icon={<Tag className="h-4 w-4" />} label="Run tag" value={result.run_tag ?? "—"} />
              <KvCard icon={<Tag className="h-4 w-4" />} label="Baseline tag" value={result.baseline_tag ?? "ar-baseline"} />
              <KvCard icon={<Database className="h-4 w-4" />} label={`Baseline ${result.metric ?? "metric"}`} value={result.baseline_metric ?? "—"} />
            </div>
          )}

          {result.message && (
            <Card className="p-4 text-sm whitespace-pre-wrap font-mono text-muted-foreground">
              {result.message}
            </Card>
          )}
        </div>
      </ScrollArea>
    </PanelShell>
  );
}

function KvCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-mono text-sm break-all">{String(value)}</div>
    </Card>
  );
}
