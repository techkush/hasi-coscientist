"use client";

import * as React from "react";
import Link from "next/link";
import { Activity, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatTimeAgo } from "@/lib/utils";
import type { DbProject } from "@/server/db";

const STATUS_BADGE: Record<
  DbProject["status"],
  { label: string; variant: "muted" | "success" | "warning" | "outline"; icon: React.ReactNode }
> = {
  pending: { label: "Pending", variant: "outline", icon: <CircleDashed className="h-3 w-3" /> },
  in_progress: { label: "In progress", variant: "warning", icon: <Activity className="h-3 w-3" /> },
  looping: { label: "Looping", variant: "success", icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  done: { label: "Done", variant: "success", icon: <CheckCircle2 className="h-3 w-3" /> },
};

export function ProjectCard({ project }: { project: DbProject }) {
  const badge = STATUS_BADGE[project.status] ?? STATUS_BADGE.pending;
  return (
    <Link href={`/projects/${encodeURIComponent(project.slug)}`} className="group">
      <Card
        className={cn(
          "h-full transition-all duration-200",
          "hover:border-primary/40 hover:shadow-md hover:-translate-y-0.5",
          "flex flex-col"
        )}
      >
        <div className="flex items-start justify-between gap-3 p-5 pb-3">
          <div className="min-w-0">
            <h3 className="font-semibold tracking-tight text-base truncate group-hover:text-primary transition-colors">
              {project.name}
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate font-mono">
              {project.slug}
            </p>
          </div>
          <Badge variant={badge.variant} className="gap-1 shrink-0">
            {badge.icon}
            {badge.label}
          </Badge>
        </div>

        <p className="px-5 pb-5 text-sm text-muted-foreground line-clamp-3 grow">
          {project.description || "No description yet."}
        </p>

        <div className="border-t border-border px-5 py-3 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{formatTimeAgo(project.created)}</span>
          {(project.done_count ?? 0) > 0 && (
            <span className="font-medium text-foreground">
              {project.done_count} kept
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
}
