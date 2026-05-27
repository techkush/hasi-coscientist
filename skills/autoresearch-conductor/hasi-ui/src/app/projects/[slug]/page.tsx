"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { TopBar } from "@/components/top-bar";
import { StageSidebar } from "@/components/stage-sidebar";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { InitPanel } from "@/components/stages/init-panel";
import { GeneratePanel } from "@/components/stages/generate-panel";
import { SetupPanel } from "@/components/stages/setup-panel";
import { IdeasPanel } from "@/components/stages/ideas-panel";
import { LoopPanel } from "@/components/stages/loop-panel";
import { AnalyzePanel } from "@/components/stages/analyze-panel";
import { trpc } from "@/lib/trpc";
import { useWsChannel } from "@/lib/ws";
import { titleCase } from "@/lib/utils";
import type { StageRow, TaskState, ProjectDetail } from "@/server/conductor";

export default function ProjectPage() {
  const { slug } = useParams<{ slug: string }>();
  // Poll project detail every 2s as a safety net even though WS pushes the
  // same data: if a WS event is missed (drop, late connect, gateway restart),
  // the sidebar still flips Setup→Done and unlocks Ideas without the user
  // having to reload. Task state polls a bit faster because it gates Execute
  // buttons across the page.
  const projectQ = trpc.projects.detail.useQuery({ slug }, { refetchInterval: 2000 });
  const taskQ = trpc.projects.task.useQuery(undefined, { refetchInterval: 1500 });

  const [stage, setStage] = React.useState<StageRow["key"]>("init");
  const [project, setProject] = React.useState<ProjectDetail | undefined>(projectQ.data);
  const [task, setTask] = React.useState<TaskState | undefined>(taskQ.data);

  React.useEffect(() => { if (projectQ.data) setProject(projectQ.data); }, [projectQ.data]);
  React.useEffect(() => { if (taskQ.data) setTask(taskQ.data); }, [taskQ.data]);

  // Live updates from WebSocket — replace the polled values.
  useWsChannel<ProjectDetail>("project", slug, (d) => setProject(d));
  useWsChannel<TaskState>("task", undefined, (d) => setTask(d));

  // Once we know the project, default to the first un-done stage that's enabled
  // (or "init" if everything is fresh).
  React.useEffect(() => {
    if (!project) return;
    const target = project.stages.find((s) => s.enabled && !s.done) ?? project.stages[0];
    if (target) setStage((cur) => (cur === "init" && !project.stages.find((s) => s.key === "init")?.done ? cur : target.key));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.slug]);

  if (!project) {
    return (
      <>
        <TopBar scope={slug} backHref="/" />
        <main className="flex h-[70vh] items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </main>
      </>
    );
  }

  const goal = describeGoal(project);
  const runningHere = !!task?.active && task?.slug === slug;
  const progress = computeProgress(task);

  return (
    <>
      <TopBar scope={slug} backHref="/" backLabel="Projects" />

      <div className="mx-auto max-w-[1500px] px-4 md:px-6 pt-6 pb-3">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight truncate">
              {project.name}
            </h1>
            <p className="text-sm text-muted-foreground italic mt-0.5">{goal}</p>
            <p className="text-sm mt-2 max-w-3xl">{project.description}</p>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            {project.metric && (
              <Badge variant="muted" className="font-mono text-[11px]">
                {project.metric} · {project.direction ?? "n/a"}
              </Badge>
            )}
            {project.loop_running && (
              <Badge variant="success" className="gap-1 text-[11px]">
                <Loader2 className="h-3 w-3 animate-spin" /> Loop running
              </Badge>
            )}
          </div>
        </div>

        {runningHere && (
          <div className="mt-4 rounded-md border border-border bg-card p-3">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              <span className="font-medium">{titleCase(task?.stage)}</span>
              <span className="text-muted-foreground">— {task?.message}</span>
            </div>
            <div className="mt-2">
              <Progress value={progress} indeterminate={progress === undefined} />
            </div>
          </div>
        )}
      </div>

      <Separator />

      <main className="mx-auto flex h-[calc(100vh-12rem)] max-w-[1500px] gap-0">
        <StageSidebar stages={project.stages} active={stage} onSelect={setStage} task={task} />

        <section className="flex-1 min-w-0 overflow-hidden">
          {stage === "init" && <InitPanel slug={slug} />}
          {stage === "generate" && (
            <GeneratePanel slug={slug} task={task} stage={findStage(project, "generate")} />
          )}
          {stage === "setup" && (
            <SetupPanel slug={slug} task={task} stage={findStage(project, "setup")} />
          )}
          {stage === "ideas" && (
            <IdeasPanel slug={slug} task={task} stage={findStage(project, "ideas")} />
          )}
          {stage === "loop" && (
            <LoopPanel slug={slug} task={task} project={project} />
          )}
          {stage === "analyze" && (
            <AnalyzePanel slug={slug} task={task} stage={findStage(project, "analyze")} />
          )}
        </section>
      </main>
    </>
  );
}

function findStage(project: ProjectDetail, key: StageRow["key"]) {
  return project.stages.find((s) => s.key === key);
}

function describeGoal(p: ProjectDetail) {
  if (p.metric && p.direction) {
    const dir = p.direction === "higher_is_better" ? "↑" : p.direction === "lower_is_better" ? "↓" : "·";
    return `Optimize ${p.metric} ${dir}`;
  }
  // Pull a 3–4-word goal from description if we can.
  if (!p.description) return "—";
  return p.description.split(/[.,]/)[0].split(/\s+/).slice(0, 6).join(" ");
}

function computeProgress(task?: TaskState): number | undefined {
  if (!task?.steps?.length) return task?.progress != null ? task.progress * 100 : undefined;
  const done = task.steps.filter((s) => s.done).length;
  return Math.round((done / task.steps.length) * 100);
}
