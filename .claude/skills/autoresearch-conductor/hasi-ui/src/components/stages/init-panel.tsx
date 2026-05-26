"use client";

import * as React from "react";
import { FileText, CheckCircle2 } from "lucide-react";
import { PanelShell } from "./panel-shell";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Markdown } from "@/components/markdown";
import { trpc } from "@/lib/trpc";

export function InitPanel({ slug }: { slug: string }) {
  const spec = trpc.projects.spec.useQuery({ slug });
  return (
    <PanelShell
      title="SPEC.md"
      subtitle=".autoresearch/SPEC.md — the source of truth for this experiment"
      actions={
        <Badge variant="success" className="gap-1">
          <CheckCircle2 className="h-3 w-3" />
          Done
        </Badge>
      }
    >
      <ScrollArea className="h-full thin-scroll">
        <div className="mx-auto max-w-3xl px-8 py-6">
          {spec.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-7 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-32 w-full mt-6" />
            </div>
          ) : !spec.data ? (
            <EmptyState />
          ) : (
            <Markdown>{spec.data}</Markdown>
          )}
        </div>
      </ScrollArea>
    </PanelShell>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-muted-foreground">
      <FileText className="h-7 w-7" />
      <p>No SPEC yet. Use the New Project flow to create one.</p>
    </div>
  );
}
