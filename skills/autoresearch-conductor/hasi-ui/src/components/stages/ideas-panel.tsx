"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Play, Lightbulb, FileUp, Check, X, Loader2, CheckCircle2, Trash2, BookOpen,
} from "lucide-react";
import { PanelShell } from "./panel-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { trpc } from "@/lib/trpc";
import type { StageRow, TaskState } from "@/server/conductor";
import { cn } from "@/lib/utils";
import { IdeaStatusBadge } from "@/components/idea-status";

export function IdeasPanel({
  slug, task, stage,
}: { slug: string; task?: TaskState; stage?: StageRow }) {
  const utils = trpc.useUtils();
  const listQ = trpc.ideas.list.useQuery({ slug }, { refetchInterval: 2000 });
  const proposalQ = trpc.ideas.proposal.useQuery({ slug }, { refetchInterval: 2000 });
  const execMut = trpc.ideas.execute.useMutation({
    onSuccess: () => toast.success("Collecting ideas…"),
    onError: (e) => toast.error(e.message),
  });
  const proposeMut = trpc.ideas.propose.useMutation({
    onSuccess: () => toast.success("Idea submitted for review."),
    onError: (e) => toast.error(e.message),
  });
  const confirmMut = trpc.ideas.confirm.useMutation({
    onSuccess: () => toast.success("Decision recorded."),
    onError: (e) => toast.error(e.message),
  });
  const removeFileMut = trpc.ideas.removeBasketFile.useMutation({
    onSuccess: () => { toast.success("Removed from basket."); listQ.refetch(); },
    onError: (e) => toast.error(e.message),
  });

  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const uploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("slug", slug);
        fd.append("file", file);
        const res = await fetch("/api/basket-upload", { method: "POST", body: fd });
        if (!res.ok) {
          let msg = `Upload failed (${res.status})`;
          try { msg = (await res.json()).error ?? msg; } catch {}
          toast.error(`${file.name}: ${msg}`);
        } else {
          toast.success(`Uploaded ${file.name}`);
        }
      }
      listQ.refetch();
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const busy = !!task?.active && task?.slug === slug && task?.stage === "ideas";
  const enabled = stage?.enabled ?? false;

  const prevBusy = React.useRef(busy);
  React.useEffect(() => {
    if (prevBusy.current && !busy) {
      utils.projects.detail.invalidate({ slug });
      utils.ideas.list.invalidate({ slug });
      utils.ideas.proposal.invalidate({ slug });
    }
    prevBusy.current = busy;
  }, [busy, slug, utils]);
  const ideas = listQ.data?.ideas ?? [];
  const counts = listQ.data?.counts ?? {};
  const files = listQ.data?.files ?? [];
  const proposal = proposalQ.data as { pending?: boolean; text?: string; verdict?: string; reason?: string } | undefined;

  const [paperLimit, setPaperLimit] = React.useState(10);
  const [ideaText, setIdeaText] = React.useState("");

  return (
    <PanelShell
      title="Idea basket"
      subtitle="Optional — curate the ideas the loop draws on. Empty basket means the loop generates its own."
      actions={
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={0}
            max={100}
            value={paperLimit}
            onChange={(e) => setPaperLimit(Number(e.target.value))}
            className="h-8 w-20 text-xs"
          />
          <Button
            size="sm"
            onClick={() => execMut.mutate({ slug, paperLimit })}
            disabled={!enabled || busy || execMut.isPending}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {busy ? "Working…" : "Collect from papers"}
          </Button>
        </div>
      }
    >
      <div className="grid h-full min-h-0 grid-cols-[1fr_320px]">
        {/* LEFT — idea list */}
        <ScrollArea className="h-full thin-scroll">
          <div className="px-6 py-4 space-y-3">
            <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
              <span>Total: <b className="text-foreground tabular-nums">{counts.total ?? ideas.length}</b></span>
              <span>Pending: <b className="text-foreground tabular-nums">{counts.pending ?? 0}</b></span>
              <span>Doing: <b className="text-foreground tabular-nums">{counts.doing ?? 0}</b></span>
              <span>Selected: <b className="text-foreground tabular-nums">{counts.selected ?? 0}</b></span>
              <span>Rejected: <b className="text-foreground tabular-nums">{counts.discarded ?? 0}</b></span>
            </div>

            {ideas.length === 0 && (
              <Card className="p-6 text-center text-sm text-muted-foreground">
                The basket is empty. The loop will use ideas it generates itself.
              </Card>
            )}

            {ideas.map((i) => (
              <Card key={i.idx} className="p-4">
                <div className="flex items-start gap-3">
                  <Lightbulb className="h-4 w-4 mt-0.5 text-primary shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                      <Badge variant="outline" className="text-[10px] font-mono">#{i.idx}</Badge>
                      <IdeaStatusBadge status={i.status} />
                      {i.source_cat && (
                        <Badge variant="muted" className="text-[10px]">{i.source_cat}</Badge>
                      )}
                    </div>
                    <p className="text-sm leading-snug">{i.text}</p>
                    {i.source && (
                      <p className="mt-2 text-[10px] text-muted-foreground truncate font-mono" title={i.source}>
                        {i.source}
                      </p>
                    )}
                    {i.commit && (
                      <p className="mt-1 text-[10px] text-muted-foreground font-mono">
                        commit {i.commit.slice(0, 7)}{i.result ? ` — ${i.result}` : ""}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </ScrollArea>

        {/* RIGHT — propose / review / files */}
        <aside className="flex min-h-0 flex-col border-l border-border bg-card/30">
          {proposal?.pending && (
            <div className="border-b border-border p-4 bg-warning/5">
              <div className="text-xs font-medium mb-1">Review needed</div>
              <p className="text-xs text-muted-foreground mb-2">{proposal.text}</p>
              {proposal.verdict && (
                <p className="text-[11px] italic text-muted-foreground mb-2">
                  HASI: {proposal.verdict}{proposal.reason ? ` — ${proposal.reason}` : ""}
                </p>
              )}
              <div className="flex gap-2">
                <Button size="sm" className="gap-1.5" onClick={() => confirmMut.mutate({ slug, accept: true })}>
                  <Check className="h-3.5 w-3.5" /> Accept
                </Button>
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => confirmMut.mutate({ slug, accept: false })}>
                  <X className="h-3.5 w-3.5" /> Reject
                </Button>
              </div>
            </div>
          )}

          <div className="p-4 border-b border-border space-y-2">
            <div className="text-xs font-medium">Propose your own</div>
            <Textarea
              rows={3}
              placeholder="A short idea, one sentence is fine"
              value={ideaText}
              onChange={(e) => setIdeaText(e.target.value)}
            />
            <Button
              size="sm"
              onClick={() => { proposeMut.mutate({ slug, text: ideaText }); setIdeaText(""); }}
              disabled={!ideaText.trim()}
              className="w-full gap-1.5"
            >
              Submit for review
            </Button>
          </div>

          <div className="p-4 flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 text-xs font-medium">
                <BookOpen className="h-3.5 w-3.5" />
                Basket files
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 text-xs"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileUp className="h-3 w-3" />}
                {uploading ? "Uploading…" : "Upload"}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.html,.htm,.md"
                className="hidden"
                onChange={(e) => uploadFiles(e.target.files)}
              />
            </div>
            <ScrollArea className="flex-1 thin-scroll -mx-1">
              <div className="px-1 space-y-1">
                {files.length === 0 && (
                  <p className="text-[11px] text-muted-foreground italic">
                    Drop PDFs or text files into <code>idea_basket/</code>. They'll show here.
                  </p>
                )}
                {files.map((f) => (
                  <div
                    key={f.name}
                    className={cn(
                      "flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs",
                    )}
                  >
                    <FileUp className="h-3 w-3 text-muted-foreground shrink-0" />
                    <span className="truncate flex-1 font-mono">{f.name}</span>
                    <Badge variant="muted" className="text-[10px]">{f.status}</Badge>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6"
                      title="Remove file"
                      onClick={() => removeFileMut.mutate({ slug, filename: f.name })}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </aside>
      </div>
    </PanelShell>
  );
}
