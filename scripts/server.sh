#!/usr/bin/env bash
set -Eeuo pipefail

# Spend Analyser single server/ops script.
#
# Local setup, dependency install, checks, background process management,
# health checks, deploy/restart, and logs for the FastAPI backend plus Next.js
# frontend.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="${APP_NAME:-spendanalyser}"
NODE_MIN_VERSION="${NODE_MIN_VERSION:-20.9.0}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_BASE_URL="${SPENDA_BACKEND_BASE:-http://127.0.0.1:${BACKEND_PORT}}"
FRONTEND_BASE_URL="${SPENDA_FRONTEND_BASE:-http://localhost:${FRONTEND_PORT}}"
BACKEND_HEALTH_PATH="${BACKEND_HEALTH_PATH:-/health}"
SERVICE="${SERVICE:-all}"

INSTALL=1
BUILD=1
TEST=1
AUDIT=1
HEALTH=1
KILL_PORT=0
FOLLOW_LOGS=0
DRY_RUN=0

STATE_DIR="$ROOT_DIR/.server"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
FRONTEND_PID_FILE="$STATE_DIR/frontend.pid"
BACKEND_LOG_FILE="$STATE_DIR/backend.log"
FRONTEND_LOG_FILE="$STATE_DIR/frontend.log"

BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m'

log() { printf '\n%b[%s]%b %s\n' "$BLUE" "$APP_NAME" "$NC" "$*"; }
ok() { printf '%b[%s:ok]%b %s\n' "$GREEN" "$APP_NAME" "$NC" "$*"; }
warn() { printf '\n%b[%s:warn]%b %s\n' "$YELLOW" "$APP_NAME" "$NC" "$*" >&2; }
die() { printf '\n%b[%s:error]%b %s\n' "$RED" "$APP_NAME" "$NC" "$*" >&2; exit 1; }
exists() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<EOF
Usage:
  bash scripts/server.sh <command> [options]

Main commands:
  setup             Create backend venv, install Python and Node dependencies.
  deploy            Install deps, run checks, restart both services, health check.
  quick             Fast deploy: skip install/build/test/audit, restart, health.
  build             Run backend compile check and frontend production build.
  test              Run parser smoke test against the bundled sample statement.
  check             Run build, parser smoke test, and npm audit.
  health            Check backend and frontend health.
  start             Start backend and frontend in the background.
  dev               Start backend and frontend in watch mode in the foreground.
  stop              Stop background services started by this script.
  restart           Stop and start background services.
  status            Show process and health status.
  logs              Follow service logs.

Options:
  --service NAME          all, backend, or frontend. Default: ${SERVICE}
  --backend-port PORT    Default: ${BACKEND_PORT}
  --frontend-port PORT   Default: ${FRONTEND_PORT}
  --port PORT            Alias for --frontend-port.
  --host HOST            Default: ${HOST}
  --backend-url URL      Default: ${BACKEND_BASE_URL}
  --frontend-url URL     Default: ${FRONTEND_BASE_URL}
  --skip-install         Skip dependency install during deploy.
  --skip-build           Skip build during deploy/check.
  --skip-test            Skip parser smoke test during deploy/check.
  --skip-audit           Skip npm audit during deploy/check.
  --skip-health          Skip final health check.
  --kill-port            Kill non-script processes using selected service ports.
  --follow-logs          Tail logs after deploy/restart/start.
  --dry-run              Print plan and exit.
  -h, --help             Show this help.

Examples:
  bash scripts/server.sh setup
  bash scripts/server.sh build
  bash scripts/server.sh health
  bash scripts/server.sh start --kill-port
  bash scripts/server.sh dev
  bash scripts/server.sh restart --service backend
EOF
}

parse_args() {
  COMMAND="${1:-}"
  if [[ -z "$COMMAND" || "$COMMAND" == "-h" || "$COMMAND" == "--help" ]]; then
    usage
    exit 0
  fi
  shift || true

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --service) SERVICE="${2:-}"; [[ -n "$SERVICE" ]] || die "--service needs value"; shift 2 ;;
      --service=*) SERVICE="${1#*=}"; shift ;;
      --backend-port) BACKEND_PORT="${2:-}"; [[ -n "$BACKEND_PORT" ]] || die "--backend-port needs value"; BACKEND_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"; shift 2 ;;
      --backend-port=*) BACKEND_PORT="${1#*=}"; BACKEND_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"; shift ;;
      --frontend-port|--port) FRONTEND_PORT="${2:-}"; [[ -n "$FRONTEND_PORT" ]] || die "$1 needs value"; FRONTEND_BASE_URL="http://localhost:${FRONTEND_PORT}"; shift 2 ;;
      --frontend-port=*|--port=*) FRONTEND_PORT="${1#*=}"; FRONTEND_BASE_URL="http://localhost:${FRONTEND_PORT}"; shift ;;
      --host) HOST="${2:-}"; [[ -n "$HOST" ]] || die "--host needs value"; shift 2 ;;
      --host=*) HOST="${1#*=}"; shift ;;
      --backend-url) BACKEND_BASE_URL="${2:-}"; [[ -n "$BACKEND_BASE_URL" ]] || die "--backend-url needs value"; shift 2 ;;
      --backend-url=*) BACKEND_BASE_URL="${1#*=}"; shift ;;
      --frontend-url) FRONTEND_BASE_URL="${2:-}"; [[ -n "$FRONTEND_BASE_URL" ]] || die "--frontend-url needs value"; shift 2 ;;
      --frontend-url=*) FRONTEND_BASE_URL="${1#*=}"; shift ;;
      --skip-install) INSTALL=0; shift ;;
      --skip-build) BUILD=0; shift ;;
      --skip-test) TEST=0; shift ;;
      --skip-audit) AUDIT=0; shift ;;
      --skip-health) HEALTH=0; shift ;;
      --kill-port) KILL_PORT=1; shift ;;
      --follow-logs) FOLLOW_LOGS=1; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  case "$SERVICE" in
    all|backend|frontend) ;;
    *) die "--service must be all, backend, or frontend" ;;
  esac

  case "$COMMAND" in
    setup)
      BUILD=0
      TEST=0
      AUDIT=0
      HEALTH=0
      ;;
    quick)
      INSTALL=0
      BUILD=0
      TEST=0
      AUDIT=0
      ;;
    build)
      INSTALL=0
      TEST=0
      AUDIT=0
      HEALTH=0
      ;;
    test)
      INSTALL=0
      BUILD=0
      AUDIT=0
      HEALTH=0
      ;;
    check|qa|qa-all)
      INSTALL=0
      HEALTH=0
      ;;
  esac
}

selected() {
  [[ "$SERVICE" == "all" || "$SERVICE" == "$1" ]]
}

ensure_runtime_dir() {
  mkdir -p "$STATE_DIR"
}

ensure_python() {
  exists "$PYTHON_BIN" || die "${PYTHON_BIN} is required but was not found in PATH."
}

ensure_node() {
  exists node || die "node is required but was not found in PATH."
  exists npm || die "npm is required but was not found in PATH."

  local ok_version
  ok_version="$(NODE_MIN_VERSION="$NODE_MIN_VERSION" node <<'NODE'
const current = process.versions.node.split('.').map(Number);
const minimum = process.env.NODE_MIN_VERSION.split('.').map(Number);
const ok = current[0] > minimum[0]
  || (current[0] === minimum[0] && current[1] > minimum[1])
  || (current[0] === minimum[0] && current[1] === minimum[1] && current[2] >= minimum[2]);
process.stdout.write(ok ? '1' : '0');
NODE
)"
  if [[ "$ok_version" != "1" ]]; then
    die "Node ${NODE_MIN_VERSION}+ is required. Current: $(node -v)"
  fi
}

backend_python() {
  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT_DIR/backend/.venv/bin/python"
  else
    printf '%s\n' "$PYTHON_BIN"
  fi
}

next_bin() {
  local bin="$ROOT_DIR/frontend/node_modules/.bin/next"
  [[ -x "$bin" ]] || die "Next.js binary not found. Run: bash scripts/server.sh setup"
  printf '%s\n' "$bin"
}

backend_health_url() {
  printf '%s%s' "${BACKEND_BASE_URL%/}" "$BACKEND_HEALTH_PATH"
}

frontend_health_url() {
  printf '%s/' "${FRONTEND_BASE_URL%/}"
}

health_responds_backend() {
  exists curl || return 1
  curl -fsS "$(backend_health_url)" >/dev/null 2>&1
}

health_responds_frontend() {
  exists curl || return 1
  curl -fsS "$(frontend_health_url)" >/dev/null 2>&1
}

pid_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

show_plan() {
  cat <<EOF
Plan:
  command: ${COMMAND}
  root: ${ROOT_DIR}
  service: ${SERVICE}
  host: ${HOST}
  backend_port: ${BACKEND_PORT}
  frontend_port: ${FRONTEND_PORT}
  backend_url: ${BACKEND_BASE_URL}
  frontend_url: ${FRONTEND_BASE_URL}
  install: ${INSTALL}
  build: ${BUILD}
  test: ${TEST}
  audit: ${AUDIT}
  health: ${HEALTH}
  kill_port: ${KILL_PORT}
EOF
}

install_deps() {
  [[ "$INSTALL" == "1" ]] || { ok "Skipping install."; return 0; }

  if selected backend; then
    ensure_python
    log "Installing backend dependencies..."
    cd "$ROOT_DIR/backend"
    [[ -d .venv ]] || "$PYTHON_BIN" -m venv .venv
    .venv/bin/python -m pip install -q --upgrade pip
    .venv/bin/python -m pip install -q -r requirements.txt
    cd "$ROOT_DIR"
    ok "Backend dependencies ready."
  fi

  if selected frontend; then
    ensure_node
    log "Installing frontend dependencies..."
    cd "$ROOT_DIR/frontend"
    npm install
    cd "$ROOT_DIR"
    ok "Frontend dependencies ready."
  fi
}

build_app() {
  [[ "$BUILD" == "1" ]] || { ok "Skipping build checks."; return 0; }

  if selected backend; then
    ensure_python
    log "Running backend compile check..."
    cd "$ROOT_DIR"
    "$(backend_python)" -m compileall backend/app
  fi

  if selected frontend; then
    ensure_node
    log "Running frontend production build..."
    cd "$ROOT_DIR/frontend"
    NEXT_PUBLIC_BACKEND_URL="$BACKEND_BASE_URL" npm run build
    cd "$ROOT_DIR"
  fi
}

test_app() {
  [[ "$TEST" == "1" ]] || { ok "Skipping tests."; return 0; }

  if selected backend; then
    ensure_python
    log "Running parser smoke test..."
    cd "$ROOT_DIR/backend"
    "$(backend_python)" - <<'PY'
from pathlib import Path

from app.parsers import parse_file

sample = Path("samples/canara_sample.pdf")
result = parse_file(sample)
assert result.rows, f"expected parsed rows from {sample}"
print(f"parsed {len(result.rows)} rows from {sample}")
PY
    cd "$ROOT_DIR"
  fi

  if selected frontend; then
    ok "No frontend test script configured; frontend is covered by build."
  fi
}

audit_app() {
  [[ "$AUDIT" == "1" ]] || { ok "Skipping npm audit."; return 0; }

  if selected frontend; then
    ensure_node
    log "Running frontend npm audit..."
    cd "$ROOT_DIR/frontend"
    npm audit --omit=dev
    cd "$ROOT_DIR"
  else
    ok "Skipping npm audit for backend-only service."
  fi
}

check_app() {
  build_app
  test_app
  audit_app
}

kill_port_process() {
  local port="$1"
  [[ "$KILL_PORT" == "1" ]] || return 0
  exists lsof || die "lsof is required for --kill-port."

  local pids
  pids="$(lsof -ti tcp:"$port" || true)"
  [[ -n "$pids" ]] || return 0

  warn "Killing process(es) on port ${port}: ${pids}"
  kill $pids || true
  sleep 1
}

wait_for_backend_health() {
  for _ in {1..30}; do
    health_responds_backend && return 0
    sleep 1
  done
  return 1
}

wait_for_frontend_health() {
  for _ in {1..30}; do
    health_responds_frontend && return 0
    sleep 1
  done
  return 1
}

start_backend() {
  ensure_runtime_dir
  ensure_python

  if pid_running "$BACKEND_PID_FILE"; then
    ok "Backend is already running with PID $(cat "$BACKEND_PID_FILE")."
    return 0
  fi

  if health_responds_backend && [[ "$KILL_PORT" != "1" ]]; then
    die "Backend already responds at $(backend_health_url), but no script PID exists. Use --kill-port or choose another --backend-port."
  fi

  kill_port_process "$BACKEND_PORT"

  log "Starting backend on ${BACKEND_BASE_URL}..."
  (
    cd "$ROOT_DIR/backend"
    SPENDA_CORS_ORIGINS="${SPENDA_CORS_ORIGINS:-http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}}" \
      nohup "$(backend_python)" -m uvicorn app.main:app --host "$HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG_FILE" 2>&1 &
    echo "$!" >"$BACKEND_PID_FILE"
  )

  if wait_for_backend_health; then
    ok "Backend started with PID $(cat "$BACKEND_PID_FILE")."
    ok "Backend logs: ${BACKEND_LOG_FILE}"
  else
    warn "Backend failed to pass health check. Last log lines:"
    tail -n 80 "$BACKEND_LOG_FILE" >&2 || true
    rm -f "$BACKEND_PID_FILE"
    exit 1
  fi
}

start_frontend() {
  ensure_runtime_dir
  ensure_node

  if [[ ! -f "$ROOT_DIR/frontend/.next/BUILD_ID" ]]; then
    die "Frontend build not found. Run: bash scripts/server.sh build --service frontend"
  fi

  if pid_running "$FRONTEND_PID_FILE"; then
    ok "Frontend is already running with PID $(cat "$FRONTEND_PID_FILE")."
    return 0
  fi

  if health_responds_frontend && [[ "$KILL_PORT" != "1" ]]; then
    die "Frontend already responds at $(frontend_health_url), but no script PID exists. Use --kill-port or choose another --frontend-port."
  fi

  kill_port_process "$FRONTEND_PORT"

  log "Starting frontend on ${FRONTEND_BASE_URL}..."
  (
    cd "$ROOT_DIR/frontend"
    NEXT_PUBLIC_BACKEND_URL="$BACKEND_BASE_URL" \
      nohup "$(next_bin)" start -p "$FRONTEND_PORT" -H "$HOST" >"$FRONTEND_LOG_FILE" 2>&1 &
    echo "$!" >"$FRONTEND_PID_FILE"
  )

  if wait_for_frontend_health; then
    ok "Frontend started with PID $(cat "$FRONTEND_PID_FILE")."
    ok "Frontend logs: ${FRONTEND_LOG_FILE}"
  else
    warn "Frontend failed to pass health check. Last log lines:"
    tail -n 80 "$FRONTEND_LOG_FILE" >&2 || true
    rm -f "$FRONTEND_PID_FILE"
    exit 1
  fi
}

start_app() {
  selected backend && start_backend
  selected frontend && start_frontend

  if [[ "$HEALTH" == "1" ]]; then
    health_check
  fi
}

stop_pid() {
  local label="$1"
  local pid_file="$2"

  if ! pid_running "$pid_file"; then
    ok "${label} is not running by this script."
    rm -f "$pid_file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  log "Stopping ${label} with PID ${pid}..."
  kill "$pid"

  for _ in {1..20}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$pid_file"
      ok "${label} stopped."
      return 0
    fi
    sleep 0.5
  done

  warn "${label} did not stop cleanly; sending SIGKILL."
  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$pid_file"
}

stop_app() {
  selected frontend && stop_pid "Frontend" "$FRONTEND_PID_FILE"
  selected backend && stop_pid "Backend" "$BACKEND_PID_FILE"
}

restart_app() {
  stop_app
  start_app
}

health_check() {
  exists curl || die "curl is required for health checks."

  if selected backend; then
    log "Checking backend health at $(backend_health_url)..."
    curl -fsS "$(backend_health_url)"
    echo
    ok "Backend health check passed."
  fi

  if selected frontend; then
    log "Checking frontend at $(frontend_health_url)..."
    curl -fsS "$(frontend_health_url)" >/dev/null
    ok "Frontend health check passed."
  fi
}

status_app() {
  if selected backend; then
    if pid_running "$BACKEND_PID_FILE"; then
      ok "Backend is running with PID $(cat "$BACKEND_PID_FILE")."
    elif health_responds_backend; then
      warn "Backend health responds, but no script PID file exists."
      warn "Backend is probably running outside this script."
    else
      ok "Backend is not running."
    fi
    printf 'Backend URL: %s\n' "$BACKEND_BASE_URL"
  fi

  if selected frontend; then
    if pid_running "$FRONTEND_PID_FILE"; then
      ok "Frontend is running with PID $(cat "$FRONTEND_PID_FILE")."
    elif health_responds_frontend; then
      warn "Frontend responds, but no script PID file exists."
      warn "Frontend is probably running outside this script."
    else
      ok "Frontend is not running."
    fi
    printf 'Frontend URL: %s\n' "$FRONTEND_BASE_URL"
  fi

  health_responds_backend || true
  health_responds_frontend || true
}

follow_logs() {
  ensure_runtime_dir
  selected backend && touch "$BACKEND_LOG_FILE"
  selected frontend && touch "$FRONTEND_LOG_FILE"

  if [[ "$SERVICE" == "backend" ]]; then
    tail -f "$BACKEND_LOG_FILE"
  elif [[ "$SERVICE" == "frontend" ]]; then
    tail -f "$FRONTEND_LOG_FILE"
  else
    tail -f "$BACKEND_LOG_FILE" "$FRONTEND_LOG_FILE"
  fi
}

setup_app() {
  install_deps
}

deploy_app() {
  setup_app
  check_app
  restart_app
  status_app
  if [[ "$FOLLOW_LOGS" == "1" ]]; then
    follow_logs
  fi
}

dev_backend() {
  ensure_python
  cd "$ROOT_DIR/backend"
  SPENDA_CORS_ORIGINS="${SPENDA_CORS_ORIGINS:-http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}}" \
    exec "$(backend_python)" -m uvicorn app.main:app --reload --host "$HOST" --port "$BACKEND_PORT"
}

dev_frontend() {
  ensure_node
  cd "$ROOT_DIR/frontend"
  NEXT_PUBLIC_BACKEND_URL="$BACKEND_BASE_URL" exec "$(next_bin)" dev -p "$FRONTEND_PORT" -H "$HOST"
}

dev_app() {
  if [[ "$SERVICE" == "backend" ]]; then
    dev_backend
  elif [[ "$SERVICE" == "frontend" ]]; then
    dev_frontend
  else
    ensure_runtime_dir
    log "Starting backend and frontend in foreground watch mode..."
    (
      cd "$ROOT_DIR/backend"
      SPENDA_CORS_ORIGINS="${SPENDA_CORS_ORIGINS:-http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}}" \
        "$(backend_python)" -m uvicorn app.main:app --reload --host "$HOST" --port "$BACKEND_PORT"
    ) &
    local backend_pid=$!

    (
      cd "$ROOT_DIR/frontend"
      NEXT_PUBLIC_BACKEND_URL="$BACKEND_BASE_URL" "$(next_bin)" dev -p "$FRONTEND_PORT" -H "$HOST"
    ) &
    local frontend_pid=$!

    trap 'kill "$backend_pid" "$frontend_pid" >/dev/null 2>&1 || true' EXIT INT TERM
    wait
  fi
}

main() {
  parse_args "$@"

  if [[ "$DRY_RUN" == "1" ]]; then
    show_plan
    exit 0
  fi

  case "$COMMAND" in
    setup) setup_app ;;
    deploy) deploy_app ;;
    quick) deploy_app ;;
    build) build_app ;;
    test) test_app ;;
    check|qa|qa-all) check_app ;;
    health) health_check ;;
    start)
      start_app
      if [[ "$FOLLOW_LOGS" == "1" ]]; then
        follow_logs
      fi
      ;;
    dev) dev_app ;;
    stop) stop_app ;;
    restart)
      restart_app
      if [[ "$FOLLOW_LOGS" == "1" ]]; then
        follow_logs
      fi
      ;;
    status) status_app ;;
    logs) follow_logs ;;
    *) die "Unknown command: ${COMMAND}" ;;
  esac
}

main "$@"
