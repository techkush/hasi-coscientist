"use client";

import * as React from "react";
import { Plus, Search, FolderOpen } from "lucide-react";
import { TopBar } from "@/components/top-bar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectCard } from "@/components/project-card";
import { NewProjectSheet } from "@/components/new-project-sheet";
import { trpc } from "@/lib/trpc";

export default function HomePage() {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const list = trpc.projects.list.useQuery(undefined, { refetchInterval: 5000 });

  const projects = (list.data ?? []).filter((p) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      p.slug.toLowerCase().includes(q) ||
      (p.description ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <>
      <TopBar
        right={
          <Button size="sm" onClick={() => setOpen(true)} className="gap-1.5">
            <Plus className="h-4 w-4" />
            New project
          </Button>
        }
      />

      <main className="mx-auto max-w-7xl px-4 md:px-6 py-8">
        <section className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Research projects</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Drive the autoresearch pipeline. Each project owns its own spec, experiment, ideas, and
            loop results.
          </p>
        </section>

        <div className="mb-6 flex items-center gap-3">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects…"
              className="pl-9"
            />
          </div>
          <div className="text-xs text-muted-foreground">
            {list.isLoading ? "Loading…" : `${projects.length} project${projects.length === 1 ? "" : "s"}`}
          </div>
        </div>

        {list.isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-44 w-full" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <EmptyState onCreate={() => setOpen(true)} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {projects.map((p) => (
              <ProjectCard key={p.slug} project={p} />
            ))}
          </div>
        )}
      </main>

      <NewProjectSheet
        open={open}
        onOpenChange={setOpen}
        onCreated={() => {
          setOpen(false);
          list.refetch();
        }}
      />
    </>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="mt-12 flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-card/50 p-10 text-center">
      <FolderOpen className="h-8 w-8 text-muted-foreground" />
      <h2 className="text-base font-medium">No projects yet</h2>
      <p className="max-w-sm text-sm text-muted-foreground">
        Start with a single research idea. HASI will turn it into a SPEC.md, generate the
        experiment, then iterate on it autonomously.
      </p>
      <Button onClick={onCreate} className="mt-2 gap-1.5">
        <Plus className="h-4 w-4" />
        Create your first project
      </Button>
    </div>
  );
}
