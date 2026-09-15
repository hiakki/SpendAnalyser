#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
GSTACK_INSTALL=""
for candidate in "${GSTACK_ROOT:-}" "$HOME/.codex/skills/gstack" "$HOME/.claude/skills/gstack" "$HOME/.agents/skills/.sources/gstack"; do
  if [[ -n "$candidate" && -x "$candidate/bin/gstack-skill-start" ]]; then
    GSTACK_INSTALL="$candidate"
    break
  fi
done
if [[ -z "$GSTACK_INSTALL" ]]; then
  echo "gstack installation missing. Set GSTACK_ROOT to an existing installation." >&2
  exit 1
fi

export GSTACK_ROOT="$GSTACK_INSTALL"
export GSTACK_HOME="$PROJECT_ROOT/.gstack"
export GSTACK_STATE_ROOT="$GSTACK_HOME"
export BROWSE_STATE_FILE="$GSTACK_HOME/browse.json"
export TMPDIR="$GSTACK_HOME/tmp"
mkdir -p "$TMPDIR"
if [[ ! -f "$GSTACK_HOME/config.yaml" ]]; then
  cp "$PROJECT_ROOT/scripts/gstack-config.yaml" "$GSTACK_HOME/config.yaml"
fi

case "${1:-doctor}" in
  doctor)
    printf 'gstack installation: %s\nstate: %s\n' "$GSTACK_INSTALL" "$GSTACK_HOME"
    for setting in telemetry artifacts_sync_mode update_check; do
      printf '%s: ' "$setting"
      "$GSTACK_INSTALL/bin/gstack-config" get "$setting"
      printf '\n'
    done
    [[ -x "$GSTACK_INSTALL/browse/dist/browse" ]] || { echo "gstack browse binary missing" >&2; exit 1; }
    printf 'browse: available\n'
    ;;
  start) shift; exec "$GSTACK_INSTALL/bin/gstack-skill-start" "$@" ;;
  end) shift; exec "$GSTACK_INSTALL/bin/gstack-skill-end" "$@" ;;
  learn) shift; exec "$GSTACK_INSTALL/bin/gstack-learnings-log" "$@" ;;
  browse) shift; exec "$GSTACK_INSTALL/browse/dist/browse" "$@" ;;
  *) echo "Usage: bash scripts/gstack.sh {doctor|start|end|learn|browse} [arguments]" >&2; exit 2 ;;
esac
