"use client";

import * as React from "react";
import { Circle, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Single source of truth for idea status rendering.
 *
 * basket.py uses 4 states under the hood: pending | doing | selected | discarded.
 * We surface them to the user as:
 *   PENDING   — idle, in the basket, never tried
 *   DOING     — currently being attempted in this loop iteration
 *   SELECTED  — picked + kept (the iteration improved the metric)
 *   REJECTED  — picked + reverted (didn't improve; "discarded" in basket.py)
 *
 * Anything else (e.g. legacy "rejected") falls back to PENDING styling so the
 * UI never shows a blank label.
 */

export type IdeaStatus = "pending" | "doing" | "selected" | "discarded" | "rejected" | string;

interface Meta {
  label: string;
  variant: "muted" | "warning" | "success" | "destructive" | "outline";
  Icon: React.ComponentType<{ className?: string }>;
  spin?: boolean;
}

const TABLE: Record<string, Meta> = {
  pending:   { label: "PENDING",  variant: "muted",       Icon: Circle },
  doing:     { label: "DOING",    variant: "warning",     Icon: Loader2, spin: true },
  selected:  { label: "SELECTED", variant: "success",     Icon: CheckCircle2 },
  discarded: { label: "REJECTED", variant: "destructive", Icon: XCircle },
  rejected:  { label: "REJECTED", variant: "destructive", Icon: XCircle },
};

export function ideaStatusMeta(status?: IdeaStatus): Meta {
  return TABLE[(status ?? "pending").toLowerCase()] ?? TABLE.pending;
}

export function IdeaStatusBadge({
  status,
  className,
  showIcon = true,
}: {
  status?: IdeaStatus;
  className?: string;
  showIcon?: boolean;
}) {
  const m = ideaStatusMeta(status);
  return (
    <Badge
      variant={m.variant}
      className={cn(
        "gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider tabular-nums",
        className
      )}
    >
      {showIcon && <m.Icon className={cn("h-2.5 w-2.5", m.spin && "animate-spin")} />}
      {m.label}
    </Badge>
  );
}
