"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Play, FolderTree, Code2, MessageSquare, Send, ExternalLink, Loader2, CheckCircle2,
  RefreshCw, FileCode, AlertTriangle,
} from "lucide-react";
import { PanelShell } from "./panel-shell";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { trpc } from "@/lib/trpc";
import { useWsChannel } from "@/lib/ws";
import type { StageRow, TaskState, GenManifest, GenChatProposal } from "@/server/conductor";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle } from "lucide-react";

interface Props {
  slug: string;
  task?: TaskState;
  stage?: StageRow;
}

export function GeneratePanel({ slug, task, stage }: Props) {
  const manifestQ = trpc.generate.manifest.useQuery({ slug }, { refetchInterval: false });
  const [manifest, setManifest] = React.useState<GenManifest | undefined>(manifestQ.data);
  React.useEffect(() => { if (manifestQ.data) setManifest(manifestQ.data); }, [manifestQ.data]);
  useWsChannel<GenManifest>("manifest", slug, (m) => setManifest(m));

  const [activePath, setActivePath] = React.useState<string | undefined>();
  React.useEffect(() => {
    if (!activePath && manifest?.files?.[0]?.path) setActivePath(manifest.files[0].path);
  }, [manifest, activePath]);

  const fileQ = trpc.generate.file.useQuery(
    { slug, path: activePath ?? "" },
    { enabled: !!activePath }
  );

  // Refresh the file content when the watcher reports a hit on this path.
  const utils = trpc.useUtils();
  useWsChannel<{ changed: string[] }>("files", slug, ({ changed }) => {
    if (activePath && changed.some((c) => c === activePath || c.endsWith(activePath))) {
      utils.generate.file.invalidate({ slug, path: activePath });
      utils.generate.manifest.invalidate({ slug });
    }
  });

  const executeMut = trpc.generate.execute.useMutation({
    onSuccess: () => toast.success("Build queued — generating files."),
    onError: (e) => toast.error(e.message),
  });
  const chatMut = trpc.generate.chat.useMutation({
    onSuccess: () => toast.message("Checking alignment with the SPEC…"),
    onError: (e) => toast.error(e.message),
  });
  const chatConfirmMut = trpc.generate.chatConfirm.useMutation({
    onError: (e) => toast.error(e.message),
  });
  const openVS = trpc.system.openInVSCode.useMutation({
    onSuccess: (r) => r.ok ? toast.success("Opening VS Code…") : toast.error(`VS Code: ${r.error}`),
    onError: (e) => toast.error(e.message),
  });

  // Poll the server-side proposal — the agent writes this after reasoning about
  // alignment with SPEC.md. Until pending is true, no dialog shows.
  const proposalQ = trpc.generate.chatProposal.useQuery(
    { slug },
    { refetchInterval: 2000, refetchIntervalInBackground: true }
  );
  const proposal = proposalQ.data as GenChatProposal | undefined;

  const [chatInput, setChatInput] = React.useState("");
  const busy = !!task?.active && task?.slug === slug && task?.stage === "generate";

  // Refresh project state the moment the agent's task clears, so the sidebar
  // flips Generate→Done and unlocks Setup without the user having to reload.
  const prevBusy = React.useRef(busy);
  React.useEffect(() => {
    if (prevBusy.current && !busy) {
      utils.projects.detail.invalidate({ slug });
      utils.generate.manifest.invalidate({ slug });
      utils.generate.chatProposal.invalidate({ slug });
    }
    prevBusy.current = busy;
  }, [busy, slug, utils]);
  const enabled = stage?.enabled ?? false;
  const done = stage?.done ?? false;
  const files = manifest?.files ?? [];
  const isPython = activePath?.endsWith(".py");

  async function submitChat() {
    if (!chatInput.trim()) return;
    // Server-side two-phase: the agent will read SPEC.md, decide alignment,
    // and write gen_chat_proposal.json. Our proposalQ poll picks it up and the
    // dialog opens. We don't gate locally — the agent's verdict is the source
    // of truth.
    await chatMut.mutateAsync({ slug, text: chatInput.trim() });
    setChatInput("");
  }

  async function acceptProposal(force = false) {
    await chatConfirmMut.mutateAsync({ slug, accept: true, force });
    toast.success(force ? "Forcing the change…" : "Applying the change…");
    proposalQ.refetch();
  }

  async function rejectProposal() {
    await chatConfirmMut.mutateAsync({ slug, accept: false });
    toast.message("Request dropped.");
    proposalQ.refetch();
  }

  return (
    <PanelShell
      title="Generate experiment"
      subtitle={done ? "Files generated. Edit freely or chat to refine." : "Build the runnable experiment from SPEC.md"}
      actions={
        <>
          <Button
            size="sm"
            variant="outline"
            onClick={() => openVS.mutate({ slug })}
            disabled={openVS.isPending}
            className="gap-1.5"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open in VS Code
          </Button>
          {!done ? (
            <Button
              size="sm"
              onClick={() => executeMut.mutate({ slug })}
              disabled={!enabled || busy || executeMut.isPending}
              className="gap-1.5"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {busy ? "Building…" : "Execute — Build"}
            </Button>
          ) : (
            <Badge variant="success" className="gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Done
            </Badge>
          )}
        </>
      }
    >
      {busy && (
        <div className="border-b border-border bg-card/40 px-5 py-2 text-xs text-muted-foreground flex items-center gap-2">
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
          {task?.message ?? "Working…"}
        </div>
      )}

      {files.length === 0 && !busy ? (
        <EmptyGenerate enabled={enabled} onExecute={() => executeMut.mutate({ slug })} />
      ) : (
        <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_260px]">
          {/* Center column — file viewer + chat. min-w-0 is critical: without it,
              a long Python line in the <pre> below would push the grid wider
              than the panel and shove the file tree off-screen. */}
          <div className="flex min-h-0 min-w-0 flex-col border-r border-border">
            <div className="flex items-center gap-2 border-b border-border bg-card/20 px-4 py-2 min-w-0">
              <FileCode className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="text-xs font-mono truncate flex-1">{activePath ?? "(select a file)"}</span>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 gap-1 text-xs shrink-0"
                onClick={() => { if (activePath) utils.generate.file.invalidate({ slug, path: activePath }); }}
              >
                <RefreshCw className="h-3 w-3" />
                Refresh
              </Button>
            </div>
            {/* The overflow-auto wrapper around <pre> gives us both vertical AND
                horizontal scroll inside the column without breaking the grid. */}
            <div className="flex-1 min-h-0 min-w-0 overflow-auto thin-scroll">
              <pre className={cn(
                "px-5 py-4 text-xs leading-relaxed font-mono",
                isPython && "language-python"
              )}>
                <code>{fileQ.isLoading ? "(loading…)" : (fileQ.data as string) ?? ""}</code>
              </pre>
            </div>
            <div className="border-t border-border bg-card/30 px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-medium">Request a change</span>
                {busy && <Badge variant="muted" className="text-[10px]">disabled while building</Badge>}
              </div>
              <Textarea
                rows={2}
                placeholder="e.g. switch the optimizer to AdamW and cap epochs at 5"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={busy}
                className="resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitChat();
                }}
              />
              <div className="mt-2 flex items-center justify-end">
                <Button size="sm" onClick={submitChat} disabled={busy || !chatInput.trim()} className="gap-1.5">
                  <Send className="h-3.5 w-3.5" />
                  Send
                </Button>
              </div>
            </div>
          </div>

          {/* Right column — file tree */}
          <FileTreePanel
            files={files}
            activePath={activePath}
            onSelect={setActivePath}
          />
        </div>
      )}

      <AlignmentReviewDialog
        proposal={proposal}
        onAccept={() => acceptProposal(false)}
        onForce={() => acceptProposal(true)}
        onReject={rejectProposal}
        busy={chatConfirmMut.isPending}
      />
    </PanelShell>
  );
}

function FileTreePanel({
  files, activePath, onSelect,
}: { files: GenManifest["files"]; activePath?: string; onSelect: (p: string) => void }) {
  const grouped = React.useMemo(() => {
    const map = new Map<string, typeof files>();
    for (const f of files) {
      const dir = f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : "(root)";
      const arr = map.get(dir) ?? [];
      arr.push(f);
      map.set(dir, arr);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [files]);

  return (
    <aside className="flex min-h-0 min-w-0 flex-col bg-sidebar/40 shrink-0">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
        <FolderTree className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs font-medium">Files ({files.length})</span>
      </div>
      <ScrollArea className="flex-1 thin-scroll">
        <div className="p-2">
          {grouped.map(([dir, list]) => (
            <div key={dir} className="mb-3">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {dir}
              </div>
              {list.map((f) => (
                <button
                  key={f.path}
                  onClick={() => onSelect(f.path)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs font-mono truncate",
                    activePath === f.path
                      ? "bg-primary text-primary-foreground"
                      : "hover:bg-sidebar-accent"
                  )}
                >
                  <Code2 className="h-3 w-3 shrink-0" />
                  <span className="truncate">{f.path.split("/").pop()}</span>
                  {f.kind && (
                    <span className="ml-auto text-[10px] opacity-70 shrink-0">{f.kind}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>
    </aside>
  );
}

function EmptyGenerate({ enabled, onExecute }: { enabled: boolean; onExecute: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-12 text-center">
      <Code2 className="h-8 w-8 text-muted-foreground" />
      <h3 className="text-base font-medium">Ready to materialize</h3>
      <p className="max-w-md text-sm text-muted-foreground">
        Click "Execute — Build" to translate SPEC.md into the runnable experiment files
        (program.md, measure.py, approach.py, …).
      </p>
      <Button onClick={onExecute} disabled={!enabled} className="mt-3 gap-1.5">
        <Play className="h-4 w-4" />
        Execute — Build
      </Button>
    </div>
  );
}

function AlignmentReviewDialog({
  proposal, onAccept, onForce, onReject, busy,
}: {
  proposal?: GenChatProposal;
  onAccept: () => void;
  onForce: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  const open = !!proposal?.pending;
  const aligned = proposal?.aligned !== false; // undefined treated as aligned
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !busy) onReject(); }}>
      <DialogContent className="sm:max-w-xl" hideClose>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {aligned ? (
              <>
                <CheckCircle className="h-4 w-4 text-primary" />
                Change ready — aligned with the SPEC
              </>
            ) : (
              <>
                <AlertTriangle className="h-4 w-4 text-destructive" />
                Heads-up — this change may not align with the goal
              </>
            )}
          </DialogTitle>
          <DialogDescription>
            HASI read <code>SPEC.md</code> and reviewed your request. Confirm to apply, or cancel to drop it.
          </DialogDescription>
        </DialogHeader>

        {proposal?.original && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Your request
            </div>
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm whitespace-pre-wrap">
              {proposal.original}
            </div>
          </div>
        )}

        {proposal?.summary && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Planned change
            </div>
            <div className="rounded-md border border-border bg-card p-3 text-sm whitespace-pre-wrap">
              {proposal.summary}
            </div>
            {proposal.files && proposal.files.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {proposal.files.map((f) => (
                  <code key={f} className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono">{f}</code>
                ))}
              </div>
            )}
          </div>
        )}

        <div
          className={cn(
            "rounded-md border p-3 text-sm",
            aligned
              ? "border-primary/30 bg-primary/5"
              : "border-destructive/40 bg-destructive/10"
          )}
        >
          <div className="flex items-center gap-2 font-medium">
            {aligned ? (
              <CheckCircle className="h-3.5 w-3.5 text-primary" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-destructive" />
            )}
            {proposal?.opinion ?? (aligned ? "Aligned with the goal" : "Not aligned with the goal")}
          </div>
          {proposal?.reason && (
            <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap">
              {proposal.reason}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onReject} disabled={busy}>
            Cancel
          </Button>
          {aligned ? (
            <Button onClick={onAccept} disabled={busy}>
              Apply change
            </Button>
          ) : (
            <Button onClick={onForce} disabled={busy} variant="destructive">
              Apply anyway
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
