/**
 * Thin fetch wrapper over the Python conductor REST API (port 8780 by default).
 * The Python side is the source of truth for state, gating, and the control-file
 * bus that drives the Claude agent. We just proxy.
 */

const BASE = process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780";

export class ConductorError extends Error {
  constructor(public status: number, public body: string) {
    super(`conductor ${status}: ${body.slice(0, 200)}`);
  }
}

async function call(
  method: "GET" | "POST",
  path: string,
  opts: { query?: Record<string, string | number | undefined>; body?: unknown; raw?: boolean } = {}
) {
  const url = new URL(path, BASE);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const init: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ConductorError(0, `network error contacting ${url}: ${(e as Error).message}`);
  }
  const text = await res.text();
  if (!res.ok) throw new ConductorError(res.status, text);
  if (opts.raw) return text;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const conductor = {
  // global
  task: () => call("GET", "/api/task") as Promise<TaskState>,
  state: () => call("GET", "/api/state"),
  projects: () => call("GET", "/api/projects") as Promise<{ projects: ProjectCard[] }>,

  // new-project intake
  newState: () => call("GET", "/api/new/state"),
  newQuestions: () => call("GET", "/api/new/questions"),
  newVariations: () => call("GET", "/api/new/variations"),
  newSpec: (id: number) => call("GET", "/api/new/spec", { query: { id }, raw: true }) as Promise<string>,
  newStart: (body: { idea: string; name?: string; domain?: string }) =>
    call("POST", "/api/new/start", { body }),
  newAnswers: (answers: Record<string, string>) =>
    call("POST", "/api/new/answers", { body: { answers } }),
  newChange: (body: { text: string; base_id?: number }) =>
    call("POST", "/api/new/change", { body }),
  newConfirm: (id: number) => call("POST", "/api/new/confirm", { body: { id } }),

  // per-project
  project: (slug: string) => call("GET", "/api/project", { query: { slug } }) as Promise<ProjectDetail>,
  spec: (slug: string) => call("GET", "/api/spec", { query: { slug }, raw: true }) as Promise<string>,
  results: (slug: string) => call("GET", "/api/results", { query: { slug } }) as Promise<{
    header: string[];
    rows: string[][];
  }>,
  genPlan: (slug: string) => call("GET", "/api/gen/plan", { query: { slug } }),
  genManifest: (slug: string) => call("GET", "/api/gen/manifest", { query: { slug } }) as Promise<GenManifest>,
  genFile: (slug: string, path: string) =>
    call("GET", "/api/gen/file", { query: { slug, path }, raw: true }) as Promise<string>,
  genChatProposal: (slug: string) =>
    call("GET", "/api/gen/chat_proposal", { query: { slug } }) as Promise<GenChatProposal>,
  setupResult: (slug: string) => call("GET", "/api/setup/result", { query: { slug } }),
  runState: (slug: string) => call("GET", "/api/run/state", { query: { slug } }) as Promise<RunState>,
  runLog: (slug: string) => call("GET", "/api/run/log", { query: { slug }, raw: true }) as Promise<string>,
  ideasList: (slug: string) => call("GET", "/api/ideas/list", { query: { slug } }) as Promise<IdeasPayload>,
  ideasIdeaMd: (slug: string) =>
    call("GET", "/api/ideas/idea_md", { query: { slug }, raw: true }) as Promise<string>,
  ideasProposal: (slug: string) => call("GET", "/api/ideas/proposal", { query: { slug } }),
  analyzeSummary: (slug: string) => call("GET", "/api/analyze/summary", { query: { slug } }) as Promise<AnalyzeSummary>,

  // POST mutations
  genExecute: (slug: string) => call("POST", "/api/gen/execute", { query: { slug } }),
  genChat: (slug: string, text: string) => call("POST", "/api/gen/chat", { query: { slug }, body: { text } }),
  genChatConfirm: (slug: string, accept: boolean, force = false) =>
    call("POST", "/api/gen/chat/confirm", { query: { slug }, body: { accept, force } }),
  genDone: (slug: string) => call("POST", "/api/gen/done", { query: { slug } }),
  setupExecute: (slug: string) => call("POST", "/api/setup/execute", { query: { slug } }),
  ideasExecute: (slug: string, paperLimit: number) =>
    call("POST", "/api/ideas/execute", { query: { slug }, body: { paper_limit: paperLimit } }),
  ideasPropose: (slug: string, text: string) =>
    call("POST", "/api/ideas/propose", { query: { slug }, body: { text } }),
  ideasConfirm: (slug: string, accept: boolean, force = false) =>
    call("POST", "/api/ideas/confirm", { query: { slug }, body: { accept, force } }),
  ideasDelete: (slug: string, name: string) =>
    call("POST", "/api/ideas/delete", { query: { slug }, body: { name } }),
  loopStart: (slug: string) => call("POST", "/api/run/loop/start", { query: { slug } }),
  loopStop: (slug: string) => call("POST", "/api/run/loop/stop", { query: { slug } }),
  analyzeExecute: (slug: string) => call("POST", "/api/analyze/execute", { query: { slug } }),
};

// ---- Types we mirror from the Python responses (best-effort, lenient) -------

export interface TaskState {
  active: boolean;
  slug?: string;
  stage?: string;
  phase?: "idle" | "queued" | "running" | "done" | "error";
  message?: string;
  progress?: number;
  steps?: { t: string; done: boolean }[];
  started?: string;
  updated?: string;
}

export interface ProjectCard {
  slug: string;
  name: string;
  description: string;
  created?: string;
  updated?: string;
  loop_running?: boolean;
  done_count?: number;
}

export interface StageRow {
  key: "init" | "generate" | "setup" | "ideas" | "loop" | "analyze";
  label: string;
  enabled: boolean;
  done: boolean;
  status?: string;
}

export interface ProjectDetail {
  slug: string;
  name: string;
  description: string;
  metric?: string;
  direction?: string;
  run_tag?: string;
  loop_running?: boolean;
  has_report?: boolean;
  stages: StageRow[];
  summary?: Record<string, unknown>;
}

export interface GenManifest {
  rev?: number;
  files: { path: string; bytes?: number; kind?: string; note?: string }[];
  validation?: Record<string, unknown>;
  chat?: { role: string; text: string; ts?: string }[];
}

export interface GenChatProposal {
  pending: boolean;
  original?: string;
  summary?: string;
  aligned?: boolean;
  opinion?: string;
  reason?: string;
  files?: string[];
}

export interface RunState {
  phase: string;
  loop_running?: boolean;
  message?: string;
  iter?: number;
}

export interface IdeasPayload {
  /**
   * Shape matches what idea_lib.read_ideas returns. Each idea is a one-paragraph
   * description (`text`) with a numeric `idx` (1-based, the ledger order); there
   * is no separate title/detail — we synthesize a short label client-side.
   */
  ideas: {
    idx: number;
    text: string;
    status?: "pending" | "doing" | "selected" | "rejected";
    source?: string;
    source_cat?: string;
    commit?: string | null;
    result?: string | null;
    note?: string | null;
  }[];
  counts: Record<string, number>;
  files: { name: string; status: string }[];
}

export interface AnalyzeSummary {
  total?: number;
  kept?: number;
  discarded?: number;
  crashed?: number;
  baseline?: Record<string, number>;
  best?: Record<string, number>;
  improvements?: { metric: string; delta: number; direction: string }[];
  report_path?: string;
}
