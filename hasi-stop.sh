#!/usr/bin/env bash
# hasi-stop.sh — stop the HASI autoresearch stack.
#
# Stops, in order:
#   1. HASI Next.js dashboard.
#   2. conductor_bridge.py (any pending agent dispatch is cancelled).
#   3. Python conductor REST API.
#   4. Any in-flight OpenClaw agent sessions the bridge spawned.
#   5. (with --gateway) the OpenClaw gateway too.
#
# Options:
#   -h, --help        Show this help.
#   --workspace <p>   Override $HOME/.openclaw/workspace.
#   --gateway         Also stop the OpenClaw gateway on :18789.
#   --clear           Delete $WS/.conductor/ runtime dir (task.json, logs, request files).
#   --force           Use SIGKILL if a process doesn't exit after SIGTERM.

set -euo pipefail

# ----------------------------- args ----------------------------------

STOP_GATEWAY=0
CLEAR_WORKDIR=0
FORCE=0
WS_OVERRIDE=""

usage() { sed -n '2,16p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --workspace) WS_OVERRIDE="$2"; shift 2 ;;
    --gateway)   STOP_GATEWAY=1; shift ;;
    --clear)     CLEAR_WORKDIR=1; shift ;;
    --force)     FORCE=1; shift ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# ----------------------------- paths ---------------------------------

WS="${WS_OVERRIDE:-$HOME/.openclaw/workspace}"
WORKDIR="$WS/.conductor"

# ----------------------------- helpers -------------------------------

c_ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
c_step() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }

stop_pattern() {
  local label="$1" pat="$2"
  local pids; pids=$(pgrep -f "$pat" 2>/dev/null || true)
  if [ -z "$pids" ]; then
    c_ok "$label: not running"
    return
  fi
  for pid in $pids; do
    kill "$pid" 2>/dev/null && printf "  killed pid %s (%s)\n" "$pid" "$label"
  done
  # wait up to 5s for graceful exit
  local i=0
  while [ "$i" -lt 5 ]; do
    pgrep -f "$pat" >/dev/null 2>&1 || { c_ok "$label: stopped"; return; }
    sleep 1; i=$((i+1))
  done
  if [ "$FORCE" = "1" ]; then
    for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
      kill -9 "$pid" 2>/dev/null && printf "  SIGKILL pid %s (%s)\n" "$pid" "$label"
    done
    c_ok "$label: force-stopped"
  else
    c_warn "$label: still running after 5s — re-run with --force to SIGKILL"
  fi
}

# ----------------------------- 1) HASI UI ----------------------------

c_step "HASI dashboard (Next.js)"
# Be specific: the tsx-launched server.ts under hasi-ui/. Falls back to a port-based kill.
stop_pattern "hasi-ui" "npx tsx .*hasi-ui.*server\.ts"
stop_pattern "hasi-ui (alt)" "node .*hasi-ui.*server\.ts"
# Last-resort: anything listening on the port
HASI_PORT="${PORT_HASI:-3000}"
if command -v lsof >/dev/null 2>&1; then
  for pid in $(lsof -nP -iTCP:"$HASI_PORT" -sTCP:LISTEN -t 2>/dev/null || true); do
    kill "$pid" 2>/dev/null && printf "  killed pid %s (hasi-ui via port %s)\n" "$pid" "$HASI_PORT"
  done
fi
rm -f "$WORKDIR/hasi-ui.pid"

# ----------------------------- 2) conductor bridge -------------------

c_step "Conductor bridge"
stop_pattern "conductor_bridge.py" "conductor_bridge\.py --workdir"

# ----------------------------- 3) conductor server -------------------

c_step "Python conductor REST API"
stop_pattern "conductor_server.py" "conductor_server\.py --port"

# ----------------------------- 4) OpenClaw agent sessions ------------

c_step "OpenClaw agent sessions (any the bridge spawned)"
# The bridge runs: openclaw agent --agent main --session-key … (or the older node /app/dist/index.js form)
stop_pattern "openclaw agent" "openclaw agent --agent"
stop_pattern "openclaw agent (docker)" "node .*dist/index\.js agent --agent"

# ----------------------------- 5) OpenClaw gateway (optional) --------

if [ "$STOP_GATEWAY" = "1" ]; then
  c_step "OpenClaw gateway"
  stop_pattern "openclaw gateway" "openclaw gateway"
else
  printf "  (gateway left running — pass --gateway to also stop it)\n"
fi

# ----------------------------- 6) optional workdir cleanup -----------

if [ "$CLEAR_WORKDIR" = "1" ]; then
  c_step "Clearing $WORKDIR"
  rm -rf "$WORKDIR"
  c_ok "workdir cleared"
fi

# ----------------------------- summary -------------------------------

echo
remaining=$(pgrep -f "conductor_server\.py|conductor_bridge\.py|hasi-ui.*server\.ts|openclaw agent --agent" 2>/dev/null | wc -l | tr -d ' ')
if [ "$remaining" = "0" ]; then
  c_ok "Everything stopped."
else
  c_warn "$remaining HASI/conductor processes still alive — try ./hasi-stop.sh --force"
fi
