#!/bin/bash
# Unattended build-out loop: one TASKS.md item per iteration, via OpenCode.
#
# Usage:   scripts/agent-loop.sh [max_iterations]        (default 15)
# Env:     MAX_ITERATIONS      same as the argument
#          ITER_TIMEOUT_MIN    kill one opencode run after this long (default 60)
#          OPENCODE_MODEL      passed as --model provider/model (default: your opencode config)
#          AGENT_LOOP_AUTO=1   pass --auto to opencode (see warning below)
#          NTFY_TOPIC          optional; also read from .env
#
# Each iteration:
#   1. stop if TASKS.md has no unchecked "- [ ]" items
#   2. opencode run "<prompt>"
#   3. run the tests; pass -> commit, fail -> git reset --hard to last good commit
#
# HINT: flags below were checked against `opencode run --help` (opencode v2.3.0).
# Re-check after upgrading OpenCode; do not add flags from memory.
# HINT: WARNING about --auto: it "auto-approves permissions that are not
# explicitly denied", which turns every "ask" rule in opencode.json (network
# installs, paths outside the repo) into "allow". It is OFF by default here.
# HINT: failed iterations are DISCARDED (reset --hard + clean of untracked,
# non-ignored files). The loop refuses to start with uncommitted changes so it
# can never throw away your own work.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Keep the Mac awake for the whole loop: re-exec this script under caffeinate.
if [ -z "${NEWNEWS_CAFFEINATED:-}" ]; then
  export NEWNEWS_CAFFEINATED=1
  exec caffeinate -dims "$0" "$@"
fi

MAX_ITERATIONS="${1:-${MAX_ITERATIONS:-15}}"
ITER_TIMEOUT_MIN="${ITER_TIMEOUT_MIN:-60}"
# HINT: a small / local model needs the whole workflow spelled out. A terse
# "complete the next task" prompt makes weaker models no-op. Keep these steps
# explicit and numbered. (Validated: MiMo 4-bit needs this; strong models are
# fine either way.)
PROMPT="You are completing exactly ONE task in this git repository. Do the steps in order; do not skip any.
1. Use your read tool to read AGENTS.md in full. It is the authority on rules, commands, style and workflow.
2. Use your read tool to read TASKS.md. Find the FIRST line beginning with '- [ ]' (the first unchecked task). That single task is your entire job; ignore every other task.
3. Re-read that task's description and its 'Done when' line so you know exactly what done means.
4. Write or update the tests for this task FIRST, under tests/. Use fixtures in tests/fixtures/; never touch the network in tests.
5. Implement the minimal code to make those tests pass. Keep all changes scoped to this one task. Follow AGENTS.md style: type hints, small pure functions, logging not print, every config value has a default.
6. Run the full suite: uv run pytest
7. ONLY if every test passes: change that task's '- [ ]' to '- [x]' in TASKS.md, and append a dated entry to PROGRESS.md using the template at the top of that file.
8. If you are blocked or cannot finish, do NOT guess: append the blocker to PROGRESS.md and stop.
Do not modify any other unchecked task. Never run git push."

mkdir -p logs
LOG="logs/agent-loop-$(date +%Y-%m-%d).log"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

unchecked() {
  local n
  n=$(grep -c '^[[:space:]]*- \[ \]' TASKS.md 2>/dev/null) || true
  echo "${n:-0}"
}

notify() {
  [ -n "${NTFY_TOPIC:-}" ] || return 0
  curl -fsS -m 10 -H "Title: NewNews agent loop" -d "$1" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
    || log "WARN ntfy ping failed"
}

# Run one opencode session with a watchdog (macOS has no `timeout` command).
run_agent() {
  local args=(run)
  [ -n "${OPENCODE_MODEL:-}" ] && args+=(--model "$OPENCODE_MODEL")
  [ "${AGENT_LOOP_AUTO:-0}" = "1" ] && args+=(--auto)
  args+=("$PROMPT")

  opencode "${args[@]}" >> "$LOG" 2>&1 &
  local pid=$!
  ( sleep $((ITER_TIMEOUT_MIN * 60)); kill "$pid" 2>/dev/null ) &
  local watchdog=$!
  local status=0
  wait "$pid" || status=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  return "$status"
}

for tool in opencode uv git; do
  command -v "$tool" >/dev/null || { log "ERROR $tool not found on PATH"; exit 1; }
done
git rev-parse --git-dir >/dev/null 2>&1 || { log "ERROR not a git repo"; exit 1; }
if [ -n "$(git status --porcelain)" ]; then
  log "ERROR working tree not clean; commit or stash first (the loop uses git reset --hard)"
  exit 1
fi

passed=0
failed=0
stop_reason="reached max iterations ($MAX_ITERATIONS)"

for ((i = 1; i <= MAX_ITERATIONS; i++)); do
  before=$(unchecked)
  if [ "$before" -eq 0 ]; then
    stop_reason="no unchecked tasks left"
    break
  fi

  good_commit=$(git rev-parse HEAD)
  log "=== iteration $i/$MAX_ITERATIONS: $before unchecked, last good commit ${good_commit:0:8} ==="

  agent_status=0
  run_agent || agent_status=$?
  [ "$agent_status" -eq 0 ] || log "WARN opencode exited with status $agent_status"

  if uv run pytest >> "$LOG" 2>&1; then
    git add -A
    if ! git diff --cached --quiet; then
      git commit -q -m "agent-loop: iteration $i (tests pass)" >> "$LOG" 2>&1
    fi
    after=$(unchecked)
    passed=$((passed + 1))
    log "PASS iteration $i: tests pass, $after unchecked, HEAD $(git rev-parse --short HEAD)"
    if [ "$after" -ge "$before" ]; then
      # No task was checked off: the agent is probably blocked (see PROGRESS.md).
      stop_reason="no task completed in iteration $i (check PROGRESS.md for a blocker)"
      break
    fi
  else
    failed=$((failed + 1))
    log "FAIL iteration $i: tests failed; resetting to ${good_commit:0:8}"
    git reset --hard "$good_commit" >> "$LOG" 2>&1
    git clean -fd >> "$LOG" 2>&1
    if [ "$failed" -ge 3 ]; then
      stop_reason="3 failed iterations"
      break
    fi
  fi
done

summary="NewNews agent loop stopped: $stop_reason. passed=$passed failed=$failed unchecked=$(unchecked). Log: $LOG"
log "$summary"
notify "$summary"
