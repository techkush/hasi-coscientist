# HASI — Hybrid Autonomous Scientific Intelligence (Dashboard)

Next.js 15 + tRPC + WebSocket dashboard that drives the autoresearch pipeline.
It is a *thin* layer over the existing Python conductor server (port 8780) —
all business logic, gating, the control-file bus, and Claude agent invocation
stay on the Python side.

## Stack

- Next.js 15 (App Router, custom server) + React 19
- Tailwind v4 + ShadCN-style component primitives, custom oklch theme
- tRPC v11 + TanStack Query (typed RPC, batched HTTP)
- WebSocket gateway (`/ws`) on the same Node process — polls Python conductor at
  1.5s and pushes events to subscribed clients; chokidar watches each subscribed
  project's filesystem for live updates
- `next-themes` for light/dark toggle
- `sonner` for toasts

## Architecture

```
┌──────────────────────────────────────────────┐
│ Browser (React)                              │
│   tRPC client → /api/trpc                    │
│   WebSocket client → /ws                     │
└──────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────┐
│ Next.js custom server (this app)             │
│   - tRPC routers (proxy to Python REST)      │
│   - WebSocket gateway (polls + watches)      │
│   - /database/projects.json mirror           │
│   - VS Code launcher (host-side)             │
└──────────────────────────────────────────────┘
                │  HTTP
                ▼
┌──────────────────────────────────────────────┐
│ Python conductor (port 8780)                 │
│   conductor_server.py + control-file bus     │
└──────────────────────────────────────────────┘
                │  control files
                ▼
┌──────────────────────────────────────────────┐
│ conductor_bridge.py → Claude agent sessions  │
└──────────────────────────────────────────────┘
```

## Running

```bash
./scripts/install.sh   # one-shot npm/pnpm install + .env.local
pnpm dev               # or: npm run dev
```

The Python conductor must already be running on `CONDUCTOR_URL` (defaults to
`http://127.0.0.1:8780`). The wrapper `openclaw-docker/conductor-start.sh`
boots both and opens the browser.

## Layout

- `src/app/page.tsx` — home (project grid + New Project sheet)
- `src/app/projects/[slug]/page.tsx` — pipeline screen (sidebar + per-stage panels)
- `src/components/stages/*` — one panel per pipeline stage
- `src/server/routers/*` — tRPC routers, one per stage
- `src/server/conductor.ts` — fetch wrapper around the Python REST API
- `src/server/ws/gateway.ts` — WebSocket gateway (poll + watch)
- `server.ts` — boots Next.js + the WS gateway in a single process

## How updates propagate

- The Python conductor remains the only writer for project state, results.tsv,
  SPEC.md, and the idea basket.
- The Next.js server polls the conductor every 1.5s for `task` + each
  subscribed project's detail / run state / generate manifest, and pushes
  what it gets over the WebSocket.
- `chokidar` watches the workspace per project; file change events are fanned
  out to subscribed clients so the Generate file viewer refreshes when the user
  edits in VS Code.
- Polling falls back to TanStack Query refetchInterval if the WS is offline.

## Open in VS Code

`POST /system.openInVSCode` shells out to `code <project_root>`. The `code` CLI
must be on PATH on the host. Inside a Docker container this won't reach the
host desktop — there is no portable workaround.
