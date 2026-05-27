"use client";

import * as React from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, MessageSquare, Send, FileText, Check, X } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Markdown } from "@/components/markdown";
import { trpc } from "@/lib/trpc";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

type Phase =
  | "intake"        // user fills idea/name/domain
  | "thinking"      // server is working (spec being generated or revised)
  | "review"        // SPEC is rendered; user can revise or confirm
  | "creating"      // user confirmed; conductor is materializing the project
  | "done";         // project created; ready to close

const DOMAINS = [
  { value: "", label: "Let HASI infer" },
  { value: "ml-training", label: "ML training" },
  { value: "algorithm", label: "Algorithm / heuristic" },
  { value: "optimization", label: "Optimization" },
  { value: "config-tuning", label: "Config tuning" },
  { value: "other", label: "Other / general" },
];

export function NewProjectSheet({ open, onOpenChange, onCreated }: Props) {
  const [idea, setIdea] = React.useState("");
  const [name, setName] = React.useState("");
  const [domain, setDomain] = React.useState("");
  const [phase, setPhase] = React.useState<Phase>("intake");
  const [revision, setRevision] = React.useState("");
  const [activeVariation, setActiveVariation] = React.useState(1);
  const [history, setHistory] = React.useState<{ role: "user" | "assistant"; text: string }[]>([]);

  const newState = trpc.newProject.state.useQuery(undefined, {
    enabled: open && phase !== "intake" && phase !== "done",
    refetchInterval: phase === "thinking" || phase === "creating" ? 1500 : false,
  });
  const variations = trpc.newProject.variations.useQuery(undefined, {
    enabled: open && (phase === "review" || phase === "thinking"),
    refetchInterval: phase === "thinking" ? 1500 : 5000,
  });
  const specQuery = trpc.newProject.spec.useQuery(
    { id: activeVariation },
    { enabled: open && phase === "review" && activeVariation > 0 }
  );

  const startMut = trpc.newProject.start.useMutation();
  const reviseMut = trpc.newProject.revise.useMutation();
  const confirmMut = trpc.newProject.confirm.useMutation();
  const listRefresh = trpc.projects.list.useQuery(undefined, { enabled: false });

  // Watch the server-side new/state phase to advance the UI.
  // Phases written by the Python conductor side: thinking, questions, review,
  // confirming, confirmed, error.
  React.useEffect(() => {
    const state = newState.data as { phase?: string } | undefined;
    if (!state) return;
    if (phase === "thinking" && state.phase === "review") {
      setPhase("review");
    } else if (phase === "creating" && state.phase === "confirmed") {
      setPhase("done");
      onCreated?.();
      listRefresh.refetch();
    } else if (state.phase === "error") {
      toast.error("The conductor returned an error — check the bridge log.");
    }
  }, [newState.data, phase, onCreated, listRefresh]);

  const variationList = ((variations.data as { variations?: { id: number; label: string }[] })?.variations) ?? [];

  // Reset state whenever the sheet opens.
  React.useEffect(() => {
    if (!open) return;
    setIdea("");
    setName("");
    setDomain("");
    setPhase("intake");
    setRevision("");
    setActiveVariation(1);
    setHistory([]);
  }, [open]);

  const locked = phase === "thinking" || phase === "creating";

  async function handleStart() {
    if (!idea.trim()) {
      toast.error("Tell HASI what you want to research.");
      return;
    }
    setPhase("thinking");
    setHistory([{ role: "user", text: idea }]);
    try {
      await startMut.mutateAsync({ idea, name: name || undefined, domain: domain || undefined });
    } catch (e) {
      toast.error((e as Error).message);
      setPhase("intake");
    }
  }

  async function handleRevise() {
    if (!revision.trim()) return;
    const text = revision.trim();
    setHistory((h) => [...h, { role: "user", text }]);
    setRevision("");
    setPhase("thinking");
    try {
      await reviseMut.mutateAsync({ text, base_id: activeVariation });
    } catch (e) {
      toast.error((e as Error).message);
      setPhase("review");
    }
  }

  async function handleConfirm() {
    setPhase("creating");
    try {
      await confirmMut.mutateAsync({ id: activeVariation });
    } catch (e) {
      toast.error((e as Error).message);
      setPhase("review");
    }
  }

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (locked) return;     // sheet locked while a background task runs
        onOpenChange(o);
      }}
    >
      <SheetContent locked={locked} className="sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            New research project
          </SheetTitle>
          <SheetDescription>
            HASI turns your idea into a SPEC.md, then materializes the experiment.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-hidden">
          {phase === "intake" && (
            <IntakeForm
              idea={idea} setIdea={setIdea}
              name={name} setName={setName}
              domain={domain} setDomain={setDomain}
            />
          )}

          {phase === "thinking" && <Thinking message={(newState.data as { message?: string })?.message ?? "Reading your idea…"} />}

          {(phase === "review" || phase === "creating") && (
            <ReviewPanel
              variations={variationList}
              activeId={activeVariation}
              setActiveId={setActiveVariation}
              specText={(specQuery.data as string) ?? "(loading)"}
              history={history}
              revision={revision}
              setRevision={setRevision}
              onRevise={handleRevise}
              locked={phase === "creating"}
            />
          )}

          {phase === "done" && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <Check className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold">Project created</h3>
              <p className="max-w-sm text-sm text-muted-foreground">
                Your SPEC.md is committed under <code className="font-mono">projects/&lt;slug&gt;/.autoresearch/SPEC.md</code>.
              </p>
            </div>
          )}
        </div>

        <SheetFooter>
          {phase === "intake" && (
            <>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={handleStart} disabled={!idea.trim() || startMut.isPending} className="gap-1.5">
                {startMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Create project
              </Button>
            </>
          )}
          {phase === "review" && (
            <>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={handleConfirm} className="gap-1.5">
                <Check className="h-4 w-4" />
                Confirm &amp; create
              </Button>
            </>
          )}
          {phase === "thinking" && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Working — this window can't close until it finishes.
            </div>
          )}
          {phase === "creating" && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Creating the project files…
            </div>
          )}
          {phase === "done" && (
            <Button onClick={() => onOpenChange(false)} className="gap-1.5">
              <X className="h-4 w-4" />
              Close
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function IntakeForm({
  idea, setIdea, name, setName, domain, setDomain,
}: {
  idea: string; setIdea: (v: string) => void;
  name: string; setName: (v: string) => void;
  domain: string; setDomain: (v: string) => void;
}) {
  return (
    <ScrollArea className="h-full">
      <div className="space-y-5 px-6 py-5">
        <div className="space-y-1.5">
          <Label htmlFor="idea">Research idea *</Label>
          <Textarea
            id="idea"
            placeholder="e.g. Train a tiny transformer on TinyStories and improve perplexity at fixed compute."
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            rows={5}
          />
          <p className="text-[11px] text-muted-foreground">
            One sentence is enough. HASI will ask follow-ups if it needs them.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="name">Project name (optional)</Label>
          <Input
            id="name"
            placeholder="auto-named from your idea if blank"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="domain">Domain hint (optional)</Label>
          <select
            id="domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {DOMAINS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
        </div>
      </div>
    </ScrollArea>
  );
}

function Thinking({ message }: { message: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-10 text-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <div>
        <h3 className="text-base font-medium">{message}</h3>
        <p className="text-sm text-muted-foreground mt-1">
          This may take a minute or two. Keep the window open.
        </p>
      </div>
    </div>
  );
}

function ReviewPanel({
  variations, activeId, setActiveId, specText, history, revision, setRevision, onRevise, locked,
}: {
  variations: { id: number; label: string }[];
  activeId: number; setActiveId: (id: number) => void;
  specText: string;
  history: { role: "user" | "assistant"; text: string }[];
  revision: string; setRevision: (v: string) => void;
  onRevise: () => void;
  locked: boolean;
}) {
  return (
    <div className="grid h-full min-h-0 grid-cols-1 md:grid-cols-[1.4fr_1fr]">
      {/* LEFT — SPEC.md */}
      <div className="flex min-h-0 flex-col border-r border-border">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2">
          <FileText className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">SPEC.md preview</span>
          <div className="ml-auto flex items-center gap-1">
            {variations.length > 0 &&
              variations.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setActiveId(v.id)}
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium border transition-colors ${
                    v.id === activeId
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-accent"
                  }`}
                >
                  v{v.id}
                </button>
              ))}
          </div>
        </div>
        <ScrollArea className="flex-1 thin-scroll">
          <div className="px-5 py-4">
            <Markdown>{specText}</Markdown>
          </div>
        </ScrollArea>
      </div>

      {/* RIGHT — revise chat */}
      <div className="flex min-h-0 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2">
          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Revise</span>
        </div>
        <ScrollArea className="flex-1 thin-scroll">
          <div className="space-y-2 px-4 py-3">
            {history.length === 0 && (
              <p className="text-xs text-muted-foreground italic">
                Ask for changes to the SPEC — "use cross-entropy as the metric", "limit to 10 minutes per run", etc.
              </p>
            )}
            {history.map((m, i) => (
              <div
                key={i}
                className={`rounded-md border px-3 py-2 text-xs ${
                  m.role === "user"
                    ? "border-primary/30 bg-primary/5"
                    : "border-border bg-card"
                }`}
              >
                <div className="font-medium mb-0.5 text-muted-foreground">
                  {m.role === "user" ? "You" : "HASI"}
                </div>
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
        <div className="border-t border-border p-3 space-y-2">
          <Textarea
            placeholder="Describe the change…"
            rows={3}
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
            disabled={locked}
            className="resize-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onRevise();
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <Badge variant="muted" className="text-[10px]">⌘ + Enter to send</Badge>
            <Button size="sm" onClick={onRevise} disabled={!revision.trim() || locked} className="gap-1.5">
              <Send className="h-3.5 w-3.5" />
              Revise
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
