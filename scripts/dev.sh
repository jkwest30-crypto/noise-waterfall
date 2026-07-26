#!/usr/bin/env bash
# Starts both halves of the app and opens it in your browser.
#
#   ./start.command      double-click in Finder
#   npm start            from a terminal
#   bash scripts/dev.sh  directly
#
# Ctrl-C stops both servers. Pass --no-open to skip launching the browser.
set -uo pipefail
cd "$(dirname "$0")/.."

VITE_PORT=5373
ENGINE_PORT=8317
OPEN_BROWSER=1
[ "${1:-}" = "--no-open" ] && OPEN_BROWSER=0

say()  { printf '\033[36m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# Resolve Node ourselves rather than trusting PATH. A non-interactive shell
# never sources nvm, so it can inherit an old default Node -- which then fails
# deep inside Vite's own source ("Unexpected token '||='") instead of saying the
# version is wrong.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 20 >/dev/null 2>&1 || true

MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$MAJOR" -lt 18 ]; then
  fail "Node 18+ required, found $(node -v 2>/dev/null || echo none)."
  fail "Fix with:  nvm install 20 && nvm alias default 20"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  fail "No .venv found. Set it up with:"
  fail "  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

if [ ! -d node_modules ]; then
  fail "No node_modules. Set it up with:  npm install"
  exit 1
fi

# Fail loudly on a busy port rather than letting Vite drift to another one.
# Another project on this machine uses 5173, and a silent fallback once meant a
# whole test run happened against somebody else's app.
for port in "$VITE_PORT" "$ENGINE_PORT"; do
  # -sTCP:LISTEN matters. A plain `lsof -ti:$port` also matches *client*
  # sockets, so any browser tab that has ever connected -- even a closed
  # connection lingering in the OS table -- would look like a conflict and
  # refuse to start the app that owns the port.
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    fail "Port $port is already in use by something that is listening on it."
    fail "If the app is already running, open http://localhost:$VITE_PORT"
    fail "To see what has it:  lsof -nP -iTCP:$port -sTCP:LISTEN"
    exit 1
  fi
done

say "Starting the engine on :$ENGINE_PORT ..."
.venv/bin/python -m uvicorn waterfall.api.app:app --port "$ENGINE_PORT" \
  --reload --reload-dir src --log-level warning &
ENGINE_PID=$!
# Tie the engine's lifetime to this script's, so Ctrl-C never strands a Python
# process holding the port.
trap 'kill $ENGINE_PID 2>/dev/null; exit 0' EXIT INT TERM

for _ in $(seq 1 40); do
  curl -sf "http://localhost:$ENGINE_PORT/health" >/dev/null 2>&1 && break
  sleep 0.25
done
if ! curl -sf "http://localhost:$ENGINE_PORT/health" >/dev/null 2>&1; then
  fail "The engine did not start. Check its dependencies:"
  fail "  .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

if [ "$OPEN_BROWSER" = "1" ]; then
  ( sleep 2.5; open "http://localhost:$VITE_PORT" >/dev/null 2>&1 || true ) &
fi

say ""
say "  Waterfall is at  http://localhost:$VITE_PORT"
say "  Press Listen to hear it. Ctrl-C here stops both servers."
say ""

npx vite --port "$VITE_PORT" --strictPort
