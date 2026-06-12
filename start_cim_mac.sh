#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_cim_mac.sh  –  Charts In Motion • Mac startup script
# ─────────────────────────────────────────────────────────────────────────────
# Usage:  bash start_cim_mac.sh            (browser mode)
#         bash start_cim_mac.sh --electron  (desktop / Electron mode)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ELECTRON_MODE=false
for arg in "$@"; do
  [[ "$arg" == "--electron" ]] && ELECTRON_MODE=true
done

# ── Ensure Homebrew Node/npm/npx are in PATH ──────────────────────────────────
for NODE_DIR in \
    "/opt/homebrew/Cellar/node/23.6.1/bin" \
    "/opt/homebrew/Cellar/node/25.6.0/bin" \
    "/opt/homebrew/bin" \
    "/usr/local/bin"; do
  [[ -f "$NODE_DIR/node" ]] && export PATH="$NODE_DIR:$PATH" && break
done

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[CiM]${RESET} $*"; }
success() { echo -e "${GREEN}[CiM]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[CiM]${RESET} $*"; }
error()   { echo -e "${RED}[CiM] ERROR:${RESET} $*" >&2; }

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Charts In Motion — Mac Launcher${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# ── 1. Resolve Python ─────────────────────────────────────────────────────────
PYTHON=""
if [[ -f ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
  info "Using existing virtualenv: .venv"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
  info "Using system python3: $(python3 --version)"
elif command -v python &>/dev/null; then
  PYTHON="python"
  info "Using system python: $(python --version)"
else
  error "Python not found. Install Python 3.11+ from https://python.org and try again."
  exit 1
fi

# ── 2. Create virtualenv if none exists ───────────────────────────────────────
if [[ ! -f ".venv/bin/python" ]]; then
  info "Creating virtualenv at .venv …"
  $PYTHON -m venv .venv
  PYTHON=".venv/bin/python"
  success "Virtualenv created."
fi

# ── 3. Install / verify backend dependencies ─────────────────────────────────
info "Checking backend dependencies …"
.venv/bin/pip install --quiet -r requirements_runtime.txt
success "Backend dependencies OK."

# ── 4. Ensure the database exists ────────────────────────────────────────────
if [[ ! -f "data/nse_data.db" ]]; then
  warn "Database not found. Running create_dev_db.py …"
  .venv/bin/python create_dev_db.py
  info "Seeding sample OHLCV data …"
  .venv/bin/python seed_ohlcv.py
  success "Database ready."
else
  info "Database found: data/nse_data.db"
fi

# ── 5. Check if frontend has a production build ───────────────────────────────
HAS_BUILD=false
[[ -f "frontend/build/index.html" ]] && HAS_BUILD=true

# ── 6. Start backend (uvicorn) ────────────────────────────────────────────────
BACKEND_PORT=8000
info "Starting FastAPI backend on port $BACKEND_PORT …"

mkdir -p runtime/logs

.venv/bin/python -m uvicorn server.server:app \
  --host 127.0.0.1 \
  --port $BACKEND_PORT \
  --log-level warning \
  > runtime/logs/backend.log 2>&1 &

BACKEND_PID=$!
echo "$BACKEND_PID" > runtime/logs/backend.pid
info "Backend PID: $BACKEND_PID  (logs → runtime/logs/backend.log)"

# ── 7. Wait for backend to become healthy ────────────────────────────────────
info "Waiting for backend to be ready …"
MAX_WAIT=45
WAITED=0
until curl -sf "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; do
  sleep 1
  WAITED=$((WAITED + 1))
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    error "Backend did not start within ${MAX_WAIT}s."
    error "Check runtime/logs/backend.log for details."
    kill "$BACKEND_PID" 2>/dev/null || true
    exit 1
  fi
done
success "Backend is ready at http://127.0.0.1:$BACKEND_PORT"

# ── 8. Frontend: build mode vs dev mode ──────────────────────────────────────
if $HAS_BUILD; then
  info "Production build detected — serving via backend."

  if $ELECTRON_MODE; then
    # ── Electron desktop mode (prod build) ────────────────────────────────
    info "Starting Electron desktop window …"
    cd desktop && npm install --silent && CIM_URL="http://127.0.0.1:$BACKEND_PORT" npx electron . &
    ELECTRON_PID=$!
    echo "$ELECTRON_PID" > "$SCRIPT_DIR/runtime/logs/electron.pid"
    cd "$SCRIPT_DIR"
    success "Electron started (PID $ELECTRON_PID)."
  else
    # ── Browser mode ──────────────────────────────────────────────────────
    sleep 1
    open "http://127.0.0.1:$BACKEND_PORT"
    success "Opened http://127.0.0.1:$BACKEND_PORT in your browser."
  fi

else
  # ── Development mode: start React dev server ─────────────────────────────
  info "No frontend build found — starting React dev server …"
  if ! command -v npm &>/dev/null; then
    error "npm not found. Install Node.js 18+ from https://nodejs.org"
    exit 1
  fi

  cd frontend
  if [[ ! -d "node_modules" ]]; then
    info "Installing frontend npm packages (first run, this may take a minute) …"
    npm install --silent
  fi

  BROWSER=none npm start > "$SCRIPT_DIR/runtime/logs/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  echo "$FRONTEND_PID" > "$SCRIPT_DIR/runtime/logs/frontend.pid"
  cd "$SCRIPT_DIR"

  info "Waiting for React dev server …"
  FWAIT=0
  until curl -sf "http://localhost:3000" >/dev/null 2>&1; do
    sleep 1
    FWAIT=$((FWAIT + 1))
    [[ $FWAIT -ge 60 ]] && { error "React dev server did not start in 60s. Check runtime/logs/frontend.log"; exit 1; }
  done

  success "React dev server ready at http://localhost:3000"
  open "http://localhost:3000"
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Charts In Motion is running!${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Backend  → ${CYAN}http://127.0.0.1:$BACKEND_PORT${RESET}"
$HAS_BUILD || echo -e "  Frontend → ${CYAN}http://localhost:3000${RESET}"
echo ""
echo -e "  To stop:  ${YELLOW}bash stop_cim_mac.sh${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# Keep script alive so Ctrl+C kills both servers
wait
