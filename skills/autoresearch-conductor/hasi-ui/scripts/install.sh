#!/usr/bin/env bash
# One-shot install of the HASI dashboard dependencies. Pinned to pnpm if
# available, otherwise falls back to npm.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v pnpm >/dev/null 2>&1; then
  pnpm install --frozen-lockfile=false
elif command -v npm >/dev/null 2>&1; then
  npm install --no-audit --no-fund
else
  echo "ERROR: need pnpm or npm on PATH" >&2
  exit 1
fi

if [ ! -f .env.local ] && [ -f .env.example ]; then
  cp .env.example .env.local
  echo "Created .env.local from .env.example — review it before starting."
fi

echo "✓ HASI dashboard ready."
echo "  Run:  pnpm dev   (or  npm run dev)"
