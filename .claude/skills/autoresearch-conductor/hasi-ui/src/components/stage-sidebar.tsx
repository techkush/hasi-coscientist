"use client";

import * as React from "react";
import { Check, CircleDot, Lock, AlertCircle, Loader2 } from "lucide-react";
import { cn, titleCase } from "@/lib/utils";
import type { StageRow, TaskState } from "@/server/conductor";

const STAGES: { key: StageRow["key"]; label: string; hint: string }[] = [
  { key: "init",     label: "Init",     hint: "Write SPEC.md" },
  { key: "generate", label: "Generate", hint: "Materialize files" },
  { key: "setup",    label: "Setup",    hint: "Branch + baseline" },
  { key: "ideas",    label: "Ideas",    hint: "Curate idea basket" },
  { key: "loop",     label: "Loop",     hint: "Run experiments" },
  { key: "analyze",  label: "Analyze",  hint: "Generate report" },
];

interface Props {
  stages: StageRow[];
  active: StageRow["key"];
  onSelect: (k: StageRow["key"]) => void;
  task?: TaskState;
}

export function StageSidebar({ stages, active, onSelect, task }: Props) {
  const stageMap = new Map(stages.map((s) => [s.key, s]));
  const activeRunning = task?.active && task?.phase === "running";
  return (
    <aside className="w-64 shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="px-4 pt-5 pb-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Pipeline
        </div>
      </div>
      <nav className="px-2 pb-4">
        {STAGES.map((meta, i) => {
          const stage = stageMap.get(meta.key);
          const enabled = stage?.enabled ?? false;
          const done = stage?.done ?? false;
          const isActive = active === meta.key;
          const isRunning = activeRunning && task?.stage === meta.key;
          return (
            <button
              key={meta.key}
              onClick={() => enabled && onSelect(meta.key)}
              disabled={!enabled}
              className={cn(
                "group relative flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-all",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/60",
                !enabled && "opacity-50 cursor-not-allowed"
              )}
            >
              <StepBadge n={i + 1} done={done} running={isRunning} enabled={enabled} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium truncate">{meta.label}</span>
                  {isRunning && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
                </div>
                <div className="text-[11px] text-muted-foreground truncate">
                  {titleCase(stage?.status) || meta.hint}
                </div>
              </div>
              {!enabled && <Lock className="h-3 w-3 text-muted-foreground shrink-0 mt-1" />}
            </button>
          );
        })}
      </nav>

      {task?.active && (
        <div className="mx-3 mb-3 rounded-md border border-border bg-card p-3 text-xs">
          <div className="flex items-center gap-2 font-medium">
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
            {task.phase === "queued" ? "Queued" : "Running"}
          </div>
          <p className="mt-1 text-muted-foreground line-clamp-2">{task.message}</p>
        </div>
      )}
    </aside>
  );
}

function StepBadge({
  n, done, running, enabled,
}: { n: number; done: boolean; running: boolean; enabled: boolean }) {
  if (running) {
    return (
      <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
      </span>
    );
  }
  if (done) {
    return (
      <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Check className="h-3 w-3" />
      </span>
    );
  }
  if (!enabled) {
    return (
      <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full border border-border text-muted-foreground">
        <AlertCircle className="h-3 w-3" />
      </span>
    );
  }
  return (
    <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full border border-border text-xs font-medium">
      {n}
    </span>
  );
}
