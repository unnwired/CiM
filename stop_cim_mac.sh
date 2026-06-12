#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# stop_cim_mac.sh  –  Charts In Motion • Mac stop script
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'
info() { echo -e "${CYAN}[CiM]${RESET} $*"; }
success() { echo -e "${GREEN}[CiM]${RESET} $*"; }

stop_pid_file() {
  local label="$1" pidfile="$2"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      info "Stopping $label (PID $pid) …"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    else
      info "$label (PID $pid) is already stopped."
    fi
    rm -f "$pidfile"
  fi
}

info "Stopping Charts In Motion …"

# Try graceful backend shutdown via API first
curl -sf -X POST "http://127.0.0.1:8000/api/admin/stop-all" >/dev/null 2>&1 || true
sleep 1

stop_pid_file "Backend"  "runtime/logs/backend.pid"
stop_pid_file "Frontend" "runtime/logs/frontend.pid"
stop_pid_file "Electron" "runtime/logs/electron.pid"

# Kill any remaining uvicorn / react-scripts processes on those ports
for PORT in 8000 3000; do
  PID_ON_PORT=$(lsof -ti tcp:$PORT 2>/dev/null || true)
  if [[ -n "$PID_ON_PORT" ]]; then
    info "Killing process on port $PORT (PID $PID_ON_PORT) …"
    kill -9 $PID_ON_PORT 2>/dev/null || true
  fi
done

success "Charts In Motion stopped."
