#!/usr/bin/env bash
# hasi-run.sh — start the HASI autoresearch stack.
#
# What it does (in order):
#   1. Pre-flight check (binaries + skills installed by hasi-setup.sh).
#   2. Make sure HASI Node deps are installed (auto-install if missing/broken).
#   3. Start OpenClaw gateway if not already running.
#   4. Re-sync the bundle's skills into the workspace (cheap, keeps things consistent).
#   5. Start the Python conductor REST API on port 8780.
#   6. Start conductor_bridge.py (the OpenClaw agent dispatcher).
#   7. Start the HASI Next.js dashboard on port 3000.
#   8. Health-probe each leg + the UI↔conductor link.
#   9. Open the browser to the dashboard (unless --no-browser).
#
# Options:
#   -h, --help                Show this help.
#   --workspace <path>        Override $HOME/.openclaw/workspace.
#   --port-conductor <p>      Override 8780.
#   --port-hasi <p>           Override 3000.
#   --no-browser              Don't open the browser.
#   --no-sync                 Skip re-syncing skills from the bundle.
#   --skip-openclaw           Don't try to start the OpenClaw gateway (use if you started it yourself).
#   --rebuild                 Re-run `npm install` for hasi-ui before booting.
#   --verbose                 Print log paths and tail-on-failure.

set -euo pipefail

# ----------------------------- args ----------------------------------

OPEN_BROWSER=1
SYNC=1
START_OPENCLAW=1
REBUILD=0
VERBOSE=0
WS_OVERRIDE=""
PORT_CONDUCTOR="${PORT_CONDUCTOR:-8780}"
PORT_HASI="${PORT_HASI:-3000}"

usage() { sed -n '2,22p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --workspace)       WS_OVERRIDE="$2"; shift 2 ;;
    --port-conductor)  PORT_CONDUCTOR="$2"; shift 2 ;;
    --port-hasi)       PORT_HASI="$2"; shift 2 ;;
    --no-browser)      OPEN_BROWSER=0; shift ;;
    --no-sync)         SYNC=0; shift ;;
    --skip-openclaw)   START_OPENCLAW=0; shift ;;
    --rebuild)         REBUILD=1; shift ;;
    --verbose)         VERBOSE=1; shift ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# ----------------------------- paths ---------------------------------

HERE="$(cd "$(dirname "$0")" && pwd)"
WS="${WS_OVERRIDE:-$HOME/.openclaw/workspace}"
WS_SKILLS="$WS/skills"
WS_BRIDGE="$WS/conductor_bridge.py"
PROJECTS_ROOT="$WS/projects"
WORKDIR="$WS/.conductor"
HASI_DIR="$WS_SKILLS/autoresearch-conductor/hasi-ui"
CONDUCTOR_URL="http://127.0.0.1:${PORT_CONDUCTOR}"
HASI_URL="http://127.0.0.1:${PORT_HASI}"

mkdir -p "$WORKDIR" "$PROJECTS_ROOT"

# ----------------------------- helpers -------------------------------

c_step() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
c_ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
c_fail() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; }

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

wait_for_url() {
  local url="$1" max="${2:-30}" i=0
  while [ "$i" -lt "$max" ]; do
    curl -sf -m 2 "$url" >/dev/null 2>&1 && return 0
    sleep 1; i=$((i+1))
  done
  return 1
}

open_browser() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    ( sleep 1 && open "$url" ) >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null 2>&1; then
    ( sleep 1 && xdg-open "$url" ) >/dev/null 2>&1 &
  else
    c_warn "No 'open' or 'xdg-open' — visit $url manually."
  fi
}

# Are HASI's node_modules actually usable? A bare empty `node_modules/` (from a
# failed install) passes `[ -d ]` but `npx tsx server.ts` immediately crashes,
# which surfaces as "HASI UI not responding". Check for the next CLI binary AND
# the tsx loader — both are required to start the server.
hasi_deps_ok() {
  [ -d "$HASI_DIR/node_modules" ] || return 1
  [ -f "$HASI_DIR/node_modules/next/package.json" ] || return 1
  [ -f "$HASI_DIR/node_modules/.bin/tsx" ] || return 1
  return 0
}

install_hasi_deps() {
  if [ -x "$HASI_DIR/scripts/install.sh" ]; then
    ( cd "$HASI_DIR" && bash scripts/install.sh )
  else
    ( cd "$HASI_DIR" && npm install --no-audit --no-fund )
  fi
}

# ----------------------------- 1) pre-flight -------------------------

c_step "Pre-flight"
for bin in python3 node npx curl rsync lsof; do
  command -v "$bin" >/dev/null 2>&1 || { c_fail "Missing $bin on PATH — run ./hasi-setup.sh first."; exit 1; }
done

if [ ! -d "$WS_SKILLS/autoresearch-conductor" ] || [ ! -f "$HASI_DIR/server.ts" ]; then
  c_fail "Workspace skills not installed — run ./hasi-setup.sh first."
  exit 1
fi

if [ "$START_OPENCLAW" = "1" ] && ! command -v openclaw >/dev/null 2>&1; then
  c_fail "openclaw CLI not on PATH — run ./hasi-setup.sh first (or pass --skip-openclaw)."
  exit 1
fi
c_ok "node=$(node --version)  python3=$(command -v python3)  workspace=$WS"

# ----------------------------- 2) HASI Node deps ---------------------

c_step "HASI Node dependencies"
if [ "$REBUILD" = "1" ]; then
  c_warn "--rebuild: forcing a fresh install"
  install_hasi_deps
  hasi_deps_ok || { c_fail "Install completed but deps still incomplete — see npm output above."; exit 1; }
  c_ok "reinstalled"
elif hasi_deps_ok; then
  c_ok "already installed ($HASI_DIR/node_modules)"
else
  if [ -d "$HASI_DIR/node_modules" ]; then
    c_warn "node_modules exists but is incomplete (likely a previous failed install) — reinstalling"
  else
    c_warn "node_modules missing — first run? installing now (this can take a few minutes)"
  fi
  install_hasi_deps
  hasi_deps_ok || { c_fail "Install completed but deps still incomplete — see npm output above."; exit 1; }
  c_ok "installed"
fi

# ----------------------------- 3) OpenClaw gateway -------------------

c_step "OpenClaw gateway (:18789)"
if curl -sf -m 2 http://127.0.0.1:18789/healthz >/dev/null 2>&1; then
  c_ok "already running"
elif [ "$START_OPENCLAW" = "0" ]; then
  c_warn "Not started (--skip-openclaw) — the bridge will fail until you start it."
else
  mkdir -p "$HOME/.openclaw/logs"
  nohup openclaw gateway >>"$HOME/.openclaw/logs/host-gateway.log" 2>&1 &
  c_ok "starting (pid $!)"
  wait_for_url http://127.0.0.1:18789/healthz 20 || c_warn "gateway not yet healthy — continuing"
fi

# ----------------------------- 4) re-sync skills ---------------------

if [ "$SYNC" = "1" ]; then
  c_step "Re-sync skills/ → $WS_SKILLS"
  rsync -a --delete \
    --exclude='node_modules' --exclude='.next' --exclude='__pycache__' \
    --exclude='.DS_Store' --exclude='*.pyc' \
    "$HERE/skills/" "$WS_SKILLS/"
  cp "$HERE/bridge/conductor_bridge.py" "$WS_BRIDGE"
  c_ok "skills + bridge refreshed"
fi

# ----------------------------- 5) Python conductor -------------------

c_step "Python conductor REST API (:$PORT_CONDUCTOR)"
if pgrep -f "conductor_server.py --port $PORT_CONDUCTOR" >/dev/null 2>&1; then
  c_ok "already running (pid $(pgrep -f "conductor_server.py --port $PORT_CONDUCTOR" | head -1))"
elif port_in_use "$PORT_CONDUCTOR"; then
  c_fail "port $PORT_CONDUCTOR is in use by something else — free it or pass --port-conductor."
  exit 1
else
  nohup python3 "$WS_SKILLS/autoresearch-conductor/conductor_server.py" \
    --port "$PORT_CONDUCTOR" --workdir "$WORKDIR" --workspace "$PROJECTS_ROOT" \
    >>"$WORKDIR/server.log" 2>&1 &
  c_ok "started (pid $!) — log: $WORKDIR/server.log"
fi

# ----------------------------- 6) conductor bridge -------------------

c_step "Conductor bridge"
if pgrep -f "conductor_bridge.py --workdir" >/dev/null 2>&1; then
  c_ok "already running (pid $(pgrep -f "conductor_bridge.py --workdir" | head -1))"
else
  AGENT_CMD="openclaw"
  command -v openclaw >/dev/null 2>&1 || AGENT_CMD="echo openclaw-missing"
  nohup python3 "$WS_BRIDGE" \
    --workdir "$WORKDIR" --workspace "$PROJECTS_ROOT" --agent main \
    --agent-cmd "$AGENT_CMD" \
    >>"$WORKDIR/bridge.log" 2>&1 &
  c_ok "started (pid $!) — log: $WORKDIR/bridge.log"
fi

# ----------------------------- 7) HASI dashboard ---------------------

c_step "HASI dashboard (Next.js, :$PORT_HASI)"
if port_in_use "$PORT_HASI"; then
  # Don't blindly trust whatever is on :3000 — a leftover crashed process from
  # a previous run will hold the port and 500 on every request, then the
  # health probe below times out at 180s with no log to look at. Identify the
  # process and decide.
  occupier_pid=$(lsof -nP -iTCP:"$PORT_HASI" -sTCP:LISTEN -t 2>/dev/null | head -1)
  occupier_cmd=$(ps -o command= -p "$occupier_pid" 2>/dev/null | head -c 200)
  http_status=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "$HASI_URL/" 2>/dev/null || echo "000")

  if [ "$http_status" = "200" ] && echo "$occupier_cmd" | grep -q "hasi-ui"; then
    c_ok "already running on :$PORT_HASI (pid $occupier_pid)"
  else
    c_fail "Port $PORT_HASI is held by something that isn't a healthy HASI UI:"
    echo "    pid:        $occupier_pid"
    echo "    command:    $occupier_cmd"
    echo "    HTTP /:     $http_status (expected 200 once compiled)"
    echo ""
    echo "    Fix: ./hasi-stop.sh --force          (kills stale UI on :$PORT_HASI)"
    echo "    Or:  ./hasi-run.sh --port-hasi 3001  (use a different port)"
    exit 1
  fi
else
  # Deps are guaranteed by step 2 — this is a paranoia check in case the
  # node_modules tree was wiped between steps.
  hasi_deps_ok || { c_fail "HASI deps disappeared between step 2 and step 7 — re-run with --rebuild."; exit 1; }
  cd "$HASI_DIR"
  CONDUCTOR_URL="$CONDUCTOR_URL" \
  WORKSPACE_ROOT="$PROJECTS_ROOT" \
  HASI_DATABASE_DIR="$WS/database" \
  PORT="$PORT_HASI" \
    nohup npx tsx server.ts >>"$WORKDIR/hasi-ui.log" 2>&1 &
  echo "$!" > "$WORKDIR/hasi-ui.pid"
  c_ok "started (pid $!) — log: $WORKDIR/hasi-ui.log"
fi

# ----------------------------- 8) health probes ----------------------

c_step "Health probes"

if wait_for_url "$CONDUCTOR_URL/api/state" 20; then
  c_ok "conductor:  $CONDUCTOR_URL  ($(curl -s "$CONDUCTOR_URL/api/state" | head -c 60))"
else
  c_fail "conductor not responding at $CONDUCTOR_URL/api/state"
  [ "$VERBOSE" = "1" ] && tail -20 "$WORKDIR/server.log"
  exit 1
fi

# First cold Next.js compile (TS + Tailwind + tRPC) can take 2-3 minutes on
# slow hardware. Give it 180s before we declare a fail.
if wait_for_url "$HASI_URL/" 180; then
  c_ok "HASI UI:    $HASI_URL"
else
  c_fail "HASI UI not responding at $HASI_URL after 180s"
  echo "    Tail of the UI log:" >&2
  tail -30 "$WORKDIR/hasi-ui.log" >&2 || true
  echo "    Full log: $WORKDIR/hasi-ui.log" >&2
  exit 1
fi

# UI↔conductor link probe (tRPC health.conductor)
TMP=$(mktemp)
if curl -sf -m 5 "$HASI_URL/api/trpc/health.conductor?input=%7B%7D" -o "$TMP"; then
  if grep -q '"ok":true' "$TMP"; then
    c_ok "UI ↔ conductor bridge link OK"
  else
    c_warn "UI ↔ conductor probe NOT OK:"
    cat "$TMP"; echo
  fi
else
  c_warn "UI reached but its health endpoint didn't respond — probably an older bundle. Continuing."
fi
rm -f "$TMP"

# OpenClaw bridge sanity: at least one of the gateway / openclaw CLI must be live
if curl -sf -m 2 http://127.0.0.1:18789/healthz >/dev/null 2>&1; then
  c_ok "OpenClaw gateway: healthy"
else
  c_warn "OpenClaw gateway not healthy on :18789 — Execute buttons will fail until it is."
fi

# ----------------------------- 9) browser ----------------------------

if [ "$OPEN_BROWSER" = "1" ]; then
  open_browser "$HASI_URL"
  c_ok "Opening $HASI_URL in your browser…"
else
  c_ok "Up. Open $HASI_URL when you're ready."
fi

cat <<EOF

  Logs:
    conductor:  $WORKDIR/server.log
    bridge:     $WORKDIR/bridge.log
    HASI UI:    $WORKDIR/hasi-ui.log
    gateway:    $HOME/.openclaw/logs/host-gateway.log
  Stop:         ./hasi-stop.sh
EOF
