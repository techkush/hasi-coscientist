/**
 * WebSocket gateway. The Python conductor doesn't push — it just exposes JSON
 * endpoints. We poll it on a single timer here and fan out the result to every
 * connected client as a structured event. We also use chokidar to watch each
 * subscribed project's files and push file-changed events so the Generate
 * panel can refresh without round-tripping.
 *
 * Message protocol (server → client):
 *   { ch: "task",    data: TaskState }
 *   { ch: "project", slug, data: ProjectDetail }
 *   { ch: "run",     slug, data: RunState }
 *   { ch: "manifest",slug, data: GenManifest }
 *   { ch: "files",   slug, data: { changed: string[] } }
 *   { ch: "results", slug, data: { rows: number } }
 *
 * Message protocol (client → server):
 *   { op: "subscribe",   slug? }
 *   { op: "unsubscribe", slug? }
 */

import path from "node:path";
import { WebSocketServer, type WebSocket } from "ws";
import chokidar, { type FSWatcher } from "chokidar";
import { conductor } from "../conductor";

const WORKSPACE = process.env.WORKSPACE_ROOT ?? "/home/node/.openclaw/workspace";
const POLL_MS = 1500;

interface ClientState {
  ws: WebSocket;
  slugs: Set<string>;
}

interface ProjectWatch {
  watcher: FSWatcher;
  refs: number;
  buffered: Set<string>;
  flushTimer?: NodeJS.Timeout;
}

const clients = new Set<ClientState>();
const watches = new Map<string, ProjectWatch>();

function send(ws: WebSocket, payload: unknown) {
  if (ws.readyState !== ws.OPEN) return;
  try {
    ws.send(JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

function broadcastForSlug(slug: string, payload: unknown) {
  for (const c of clients) {
    if (c.slugs.has(slug)) send(c.ws, payload);
  }
}

function broadcastGlobal(payload: unknown) {
  for (const c of clients) send(c.ws, payload);
}

async function pollOnce() {
  // global task
  conductor.task().then((task) => broadcastGlobal({ ch: "task", data: task })).catch(() => {});

  // per-subscribed-slug detail + run state + manifest (only one in-flight per slug per tick)
  const slugs = new Set<string>();
  for (const c of clients) for (const s of c.slugs) slugs.add(s);
  for (const slug of slugs) {
    conductor.project(slug)
      .then((data) => broadcastForSlug(slug, { ch: "project", slug, data }))
      .catch(() => {});
    conductor.runState(slug)
      .then((data) => broadcastForSlug(slug, { ch: "run", slug, data }))
      .catch(() => {});
    conductor.genManifest(slug)
      .then((data) => broadcastForSlug(slug, { ch: "manifest", slug, data }))
      .catch(() => {});
  }
}

function ensureWatch(slug: string) {
  const existing = watches.get(slug);
  if (existing) {
    existing.refs += 1;
    return;
  }
  const root = path.join(WORKSPACE, slug);
  const watcher = chokidar.watch(root, {
    ignoreInitial: true,
    ignored: [
      /(^|[\/\\])\../,        // dotfiles (except .autoresearch handled below)
      /node_modules/,
      /__pycache__/,
      /\.next/,
      /dist|build/,
    ],
    awaitWriteFinish: { stabilityThreshold: 200, pollInterval: 50 },
  });
  const w: ProjectWatch = { watcher, refs: 1, buffered: new Set() };
  const onChange = (full: string) => {
    const rel = path.relative(root, full).split(path.sep).join("/");
    if (!rel || rel.startsWith("..")) return;
    w.buffered.add(rel);
    if (w.flushTimer) return;
    w.flushTimer = setTimeout(() => {
      const changed = Array.from(w.buffered);
      w.buffered.clear();
      w.flushTimer = undefined;
      broadcastForSlug(slug, { ch: "files", slug, data: { changed } });
    }, 150);
  };
  watcher
    .on("add", onChange)
    .on("change", onChange)
    .on("unlink", onChange);
  watches.set(slug, w);
}

function releaseWatch(slug: string) {
  const w = watches.get(slug);
  if (!w) return;
  w.refs -= 1;
  if (w.refs <= 0) {
    w.watcher.close().catch(() => {});
    watches.delete(slug);
  }
}

let pollTimer: NodeJS.Timeout | null = null;

export function attachWebSocket(server: import("node:http").Server) {
  const wss = new WebSocketServer({ server, path: "/ws" });

  wss.on("connection", (ws) => {
    const state: ClientState = { ws, slugs: new Set() };
    clients.add(state);

    ws.on("message", (raw) => {
      let msg: { op?: string; slug?: string } = {};
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      if (msg.op === "subscribe" && msg.slug) {
        if (!state.slugs.has(msg.slug)) {
          state.slugs.add(msg.slug);
          ensureWatch(msg.slug);
        }
      } else if (msg.op === "unsubscribe" && msg.slug) {
        if (state.slugs.delete(msg.slug)) releaseWatch(msg.slug);
      }
    });

    ws.on("close", () => {
      for (const s of state.slugs) releaseWatch(s);
      clients.delete(state);
    });

    send(ws, { ch: "hello", data: { ok: true, poll_ms: POLL_MS } });
  });

  if (!pollTimer) {
    pollTimer = setInterval(() => {
      pollOnce().catch(() => {});
    }, POLL_MS);
  }
}
