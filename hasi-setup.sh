#!/usr/bin/env bash
# hasi-setup.sh — one-time installer for the HASI autoresearch stack.
#
# What it does (in order):
#   1. Verify prerequisites (python3, node, npm, curl, rsync, lsof).
#   2. Install OpenClaw if the `openclaw` CLI is not on PATH.
#   3. Remind the user to run `openclaw onboard` (interactive, one-time).
#   4. Sync the bundle's skills/ into the OpenClaw workspace.
#   5. Install the bundle's bridge into the workspace.
#   6. Install HASI dashboard Node dependencies.
#   7. Prepare the Docker stack (optional — used if you can't run native).
#
# Options:
#   -h, --help              Show this help.
#   --workspace <path>      Override $HOME/.openclaw/workspace.
#   --no-install-openclaw   Skip OpenClaw install (assume it's already there).
#   --no-install-deps       Skip the hasi-ui `npm install`.
#   --no-docker             Don't copy Docker assets into the workspace.
#   --force                 Re-do every step even if it looks done.
#
# Safe to re-run. Idempotent.

set -euo pipefail

# ----------------------------- args ----------------------------------

INSTALL_OPENCLAW=1
INSTALL_DEPS=1
WITH_DOCKER=1
FORCE=0
WS_OVERRIDE=""

usage() { sed -n '2,22p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --workspace) WS_OVERRIDE="$2"; shift 2 ;;
    --no-install-openclaw) INSTALL_OPENCLAW=0; shift ;;
    --no-install-deps)     INSTALL_DEPS=0; shift ;;
    --no-docker)           WITH_DOCKER=0; shift ;;
    --force)               FORCE=1; shift ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# ----------------------------- paths ---------------------------------

HERE="$(cd "$(dirname "$0")" && pwd)"
WS="${WS_OVERRIDE:-$HOME/.openclaw/workspace}"
WS_SKILLS="$WS/skills"
WS_BRIDGE="$WS/conductor_bridge.py"
WS_DOCKER="$WS/.docker"

mkdir -p "$WS"

# ----------------------------- helpers -------------------------------

c_step() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
c_ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
c_warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
c_fail() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; }

need_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    c_fail "Missing required binary on PATH: $1"
    [ -n "${2:-}" ] && echo "    Install hint: $2"
    return 1
  fi
}

# ----------------------------- 1) prerequisites ----------------------

c_step "Pre-flight"
ok=1
need_bin python3 "macOS: comes with Xcode CLT; Linux: sudo apt install python3" || ok=0
need_bin node "Install Node 22.19+ from https://nodejs.org or nvm" || ok=0
need_bin npm  "Bundled with Node"                                  || ok=0
need_bin curl ""                                                   || ok=0
need_bin rsync ""                                                  || ok=0
need_bin lsof ""                                                   || ok=0
[ "$ok" = "1" ] || { c_fail "Resolve the missing tools above, then re-run."; exit 1; }

NODE_MAJOR="$(node -e 'process.stdout.write(String(process.versions.node.split(".")[0]))')"
if [ "$NODE_MAJOR" -lt 22 ]; then
  c_warn "node $(node --version) detected. OpenClaw needs >= 22.19. Use nvm to install v22.22.3+."
fi
c_ok "python3=$(command -v python3)  node=$(node --version)  workspace=$WS"

# ----------------------------- 2) install OpenClaw -------------------

c_step "OpenClaw CLI"
if command -v openclaw >/dev/null 2>&1; then
  c_ok "openclaw already installed: $(command -v openclaw)  ($(openclaw --version 2>/dev/null || echo unknown))"
elif [ "$INSTALL_OPENCLAW" = "0" ]; then
  c_fail "openclaw not on PATH and --no-install-openclaw was passed. Install it from https://openclaw.ai and retry."
  exit 1
else
  c_step "Running the official OpenClaw installer (curl | bash)…"
  curl -fsSL https://openclaw.ai/install.sh | bash
  hash -r 2>/dev/null || true
  if ! command -v openclaw >/dev/null 2>&1; then
    c_fail "openclaw still not on PATH after install. Add the install directory to PATH and retry."
    exit 1
  fi
  c_ok "openclaw installed: $(command -v openclaw)"
fi

# ----------------------------- 3) onboarding hint --------------------

c_step "Onboarding check"
if [ -f "$HOME/.openclaw/openclaw.json" ]; then
  c_ok "OpenClaw config found at \$HOME/.openclaw/openclaw.json — onboarding is done."
else
  c_warn "OpenClaw is not yet onboarded. After this script finishes, run:"
  echo "      ! openclaw onboard"
  echo "    (the '!' prefix runs it interactively in your shell session — you'll be asked for an Anthropic API key and a few options)."
fi

# ----------------------------- 4) sync skills ------------------------

c_step "Sync skills/ → $WS_SKILLS"
if [ ! -d "$HERE/skills" ]; then
  c_fail "Bundle is missing skills/ — re-clone the repo."
  exit 1
fi
rsync -a --delete \
  --exclude='node_modules' --exclude='.next' --exclude='__pycache__' \
  --exclude='.DS_Store' --exclude='*.pyc' --exclude='.pytest_cache' \
  "$HERE/skills/" "$WS_SKILLS/"
c_ok "synced $(find "$WS_SKILLS" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') skills"

# ----------------------------- 5) bridge -----------------------------

c_step "Install conductor bridge"
if [ ! -f "$HERE/bridge/conductor_bridge.py" ]; then
  c_fail "Bundle is missing bridge/conductor_bridge.py"
  exit 1
fi
cp "$HERE/bridge/conductor_bridge.py" "$WS_BRIDGE"
c_ok "bridge → $WS_BRIDGE"

# ----------------------------- 6) hasi-ui deps -----------------------

HASI_DIR="$WS_SKILLS/autoresearch-conductor/hasi-ui"
c_step "HASI dashboard dependencies"
if [ ! -d "$HASI_DIR" ]; then
  c_fail "hasi-ui not found at $HASI_DIR — bundle is incomplete."
  exit 1
fi
if [ "$INSTALL_DEPS" = "0" ]; then
  c_warn "Skipped (--no-install-deps). Remember to run 'npm install' inside $HASI_DIR before hasi-run.sh."
elif [ -d "$HASI_DIR/node_modules" ] && [ "$FORCE" = "0" ]; then
  c_ok "node_modules already present (use --force to reinstall)"
else
  if [ -x "$HASI_DIR/scripts/install.sh" ]; then
    ( cd "$HASI_DIR" && bash scripts/install.sh )
  else
    ( cd "$HASI_DIR" && npm install )
  fi
  c_ok "hasi-ui dependencies installed"
fi

# ----------------------------- 7) Docker assets ----------------------

c_step "Docker assets (optional)"
if [ "$WITH_DOCKER" = "0" ]; then
  c_warn "Skipped (--no-docker)."
elif [ ! -d "$HERE/docker" ]; then
  c_warn "Bundle has no docker/ directory — skipping."
else
  mkdir -p "$WS_DOCKER"
  cp -f "$HERE/docker/docker-compose.yml"       "$WS_DOCKER/docker-compose.yml"
  cp -f "$HERE/docker/docker-compose.extra.yml" "$WS_DOCKER/docker-compose.extra.yml"
  if [ ! -f "$WS_DOCKER/.env" ]; then
    if [ -f "$HERE/docker/.env.example" ]; then
      cp "$HERE/docker/.env.example" "$WS_DOCKER/.env"
      c_warn "Wrote $WS_DOCKER/.env from .env.example — edit it to add your API key before using Docker mode."
    else
      cat > "$WS_DOCKER/.env" <<'EOF'
# Edit this file to enable Docker mode for OpenClaw.
# OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest
# OPENCLAW_GATEWAY_TOKEN=
# OPENCLAW_GATEWAY_BIND=lan
# ANTHROPIC_API_KEY=
EOF
      c_warn "Wrote a blank $WS_DOCKER/.env — fill in keys before using Docker mode."
    fi
  fi
  c_ok "docker assets → $WS_DOCKER"
fi

# ----------------------------- done ----------------------------------

cat <<EOF

$(c_ok "Setup complete.")

  Skills:         $WS_SKILLS
  Bridge:         $WS_BRIDGE
  HASI UI:        $HASI_DIR
  Docker assets:  $WS_DOCKER   (used only in Docker mode)

Next:
  1. If you haven't onboarded OpenClaw yet:    ! openclaw onboard
  2. Start the stack:                          ./hasi-run.sh
  3. Stop everything:                          ./hasi-stop.sh
EOF
