"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Play, Square, Loader2, Activity, TrendingUp, TrendingDown, RotateCw, Terminal,
} from "lucide-react";
import { PanelShell } from "./panel-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { trpc } from "@/lib/trpc";
import type { ProjectDetail, TaskState, RunState } from "@/server/conductor";
import { useWsChannel } from "@/lib/ws";
import { IdeaStatusBadge } from "@/components/idea-status";
import { Lightbulb } from "lucide-react";

export function LoopPanel({
  slug, task, project,
}: { slug: string; task?: TaskState; project: ProjectDetail }) {
  const runQ = trpc.loop.state.useQuery({ slug }, { refetchInterval: 2500 });
  const logQ = trpc.loop.log.useQuery({ slug }, { refetchInterval: 2500 });
  const resultsQ = trpc.projects.results.useQuery({ slug }, { refetchInterval: 3000 });
  // Refetch the basket on every loop tick so PENDING → DOING → SELECTED/REJECTED
  // transitions show up here without the user having to switch to the Ideas tab.
  const ideasQ = trpc.ideas.list.useQuery({ slug }, { refetchInterval: 2500 });

  const [run, setRun] = React.useState<RunState | undefined>(runQ.data);
  React.useEffect(() => { if (runQ.data) setRun(runQ.data); }, [runQ.data]);
  useWsChannel<RunState>("run", slug, (d) => setRun(d));

  const startMut = trpc.loop.start.useMutation({
    onSuccess: () => toast.success("Loop started."),
    onError: (e) => toast.error(e.message),
  });
  const stopMut = trpc.loop.stop.useMutation({
    onSuccess: () => toast.message("Stop requested — finishing current iteration…"),
    onError: (e) => toast.error(e.message),
  });

  const running = run?.loop_running || project.loop_running;
  const phase = run?.phase ?? "idle";
  const busy = !!task?.active && task?.slug === slug && task?.stage === "loop";
  const stage = project.stages.find((s) => s.key === "loop");
  const enabled = stage?.enabled ?? false;

  const allIdeas = ideasQ.data?.ideas ?? [];
  const doingIdea = allIdeas.find((i) => i.status === "doing");
  const recentlyResolved = allIdeas
    .filter((i) => i.status === "selected" || i.status === "discarded")
    .slice(-3)
    .reverse();

  const rows = resultsQ.data?.rows ?? [];
  const header = resultsQ.data?.header ?? [];
  const statusIdx = header.findIndex((h) => h.toLowerCase() === "status" || h.toLowerCase() === "decision");
  const metricIdx = project.metric ? header.findIndex((h) => h === project.metric) : -1;
  const higher = project.direction !== "lower_is_better";  // default to higher-is-better if unspecified

  // Baseline = the first row (the "baseline" tag the setup stage commits).
  // Best metric = the BEST value among rows whose status is "keep" — discarded
  // / reverted runs must NOT count even if they technically had a better number,
  // because they were rolled back. Direction-aware (higher_is_better vs lower).
  const baselineMetric = metricIdx >= 0 && rows.length ? rows[0][metricIdx] : undefined;

  const keptRows = statusIdx >= 0
    ? rows.filter((r) => (r[statusIdx] ?? "").toLowerCase() === "keep")
    : [];
  const kept = keptRows.length;

  let bestMetric: string | undefined;
  if (metricIdx >= 0) {
    for (const r of keptRows) {
      const v = Number(r[metricIdx]);
      if (!Number.isFinite(v)) continue;
      if (bestMetric === undefined) { bestMetric = r[metricIdx]; continue; }
      const bv = Number(bestMetric);
      if ((higher && v > bv) || (!higher && v < bv)) bestMetric = r[metricIdx];
    }
  }

  const baselineNum = baselineMetric != null ? Number(baselineMetric) : NaN;
  const bestNum = bestMetric != null ? Number(bestMetric) : NaN;
  const improving = Number.isFinite(baselineNum) && Number.isFinite(bestNum)
    ? (higher ? bestNum > baselineNum : bestNum < baselineNum)
    : false;

  return (
    <PanelShell
      title="Experiment loop"
      subtitle="Autonomous iterations — pick an idea, edit the editable file, run, keep or revert."
      actions={
        running ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={() => stopMut.mutate({ slug })}
            disabled={stopMut.isPending}
            className="gap-1.5"
          >
            {stopMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
            Stop loop
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => startMut.mutate({ slug })}
            disabled={!enabled || busy || startMut.isPending}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Start loop
          </Button>
        )
      }
    >
      <div className="grid h-full min-h-0 grid-cols-[1fr_360px]">
        <div className="flex min-h-0 flex-col">
          <div className="grid grid-cols-3 gap-3 border-b border-border bg-card/20 p-4">
            <StatCard
              icon={<Activity className="h-3.5 w-3.5" />}
              label="Phase"
              value={<span className="capitalize">{phase}</span>}
            />
            <StatCard
              icon={<RotateCw className="h-3.5 w-3.5" />}
              label="Iterations"
              value={rows.length}
            />
            <StatCard
              icon={
                bestMetric == null
                  ? <TrendingDown className="h-3.5 w-3.5" />
                  : improving
                    ? <TrendingUp className="h-3.5 w-3.5" />
                    : <TrendingDown className="h-3.5 w-3.5" />
              }
              label={`Best ${project.metric ?? "metric"}`}
              value={
                bestMetric != null ? (
                  <span className={improving ? "text-primary" : "text-muted-foreground"}>
                    {bestMetric}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )
              }
              hint={
                bestMetric == null
                  ? `Baseline ${baselineMetric ?? "—"} · no keeps yet`
                  : `Baseline ${baselineMetric ?? "—"} · ${kept} kept` +
                    (improving && Number.isFinite(baselineNum) && Number.isFinite(bestNum)
                      ? `  (${higher ? "+" : ""}${(bestNum - baselineNum).toFixed(3)})`
                      : "")
              }
            />
          </div>

          {(doingIdea || recentlyResolved.length > 0) && (
            <div className="border-b border-border bg-card/20 px-4 py-3">
              {doingIdea ? (
                <div className="flex items-start gap-3">
                  <Lightbulb className="h-4 w-4 mt-0.5 text-primary shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
                        Now trying
                      </span>
                      <Badge variant="outline" className="text-[10px] font-mono">#{doingIdea.idx}</Badge>
                      <IdeaStatusBadge status={doingIdea.status} />
                    </div>
                    <p className="text-xs text-foreground/90 line-clamp-2">{doingIdea.text}</p>
                  </div>
                </div>
              ) : (
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
                  Last verdicts
                </div>
              )}
              {recentlyResolved.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {recentlyResolved.map((i) => (
                    <div
                      key={i.idx}
                      className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1"
                      title={i.text}
                    >
                      <span className="text-[10px] font-mono text-muted-foreground">#{i.idx}</span>
                      <IdeaStatusBadge status={i.status} showIcon={false} className="text-[9px] px-1.5" />
                      <span className="text-[10px] text-muted-foreground line-clamp-1 max-w-[260px]">{i.text}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 border-b border-border bg-card/10 px-4 py-2">
            <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium">run.log (tail)</span>
            {running && <Badge variant="success" className="gap-1 text-[10px]">
              <Loader2 className="h-2.5 w-2.5 animate-spin" /> live
            </Badge>}
          </div>
          <ScrollArea className="flex-1 thin-scroll bg-[oklch(0_0_0/0.03)] dark:bg-[oklch(0_0_0/0.3)]">
            <pre className="px-4 py-3 text-[11px] leading-snug font-mono whitespace-pre">
              <code>{logQ.data ?? "(no log yet)"}</code>
            </pre>
          </ScrollArea>
        </div>

        <aside className="min-h-0 flex flex-col border-l border-border bg-card/30">
          <div className="border-b border-border px-4 py-2 text-xs font-medium">results.tsv</div>
          <ScrollArea className="flex-1 thin-scroll">
            <div className="px-3 py-2 space-y-1">
              {rows.length === 0 && (
                <p className="text-[11px] text-muted-foreground italic px-1">No runs yet.</p>
              )}
              {rows.slice().reverse().map((r, i) => {
                const status = statusIdx >= 0 ? r[statusIdx] : "";
                const metric = metricIdx >= 0 ? r[metricIdx] : "";
                return (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded border border-border px-2 py-1.5 text-[11px]"
                  >
                    <span className="font-mono text-muted-foreground w-8">#{rows.length - i}</span>
                    <Badge
                      variant={status?.toLowerCase() === "keep" ? "success" : "muted"}
                      className="text-[10px]"
                    >
                      {status || "—"}
                    </Badge>
                    <span className="ml-auto font-mono">{metric || "—"}</span>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </aside>
      </div>
    </PanelShell>
  );
}

function StatCard({
  icon, label, value, hint,
}: { icon: React.ReactNode; label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card className="p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-0.5 text-base font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </Card>
  );
}
