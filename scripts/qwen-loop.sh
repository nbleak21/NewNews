#!/bin/bash
# Unattended build-out loop: one TASKS.md item per iteration, via Qwen Code.
#
# Qwen Code (https://github.com/QwenLM/qwen-code) is an agentic tool-calling CLI
# purpose-built for Qwen3-Coder's tool-call format. Unlike Aider (which wants
# whole-file edit blocks), it EXECUTES the model's shell/edit/write tool calls —
# which is what this SWE-agent-trained model expects (it otherwise emits
# <tool_call>run_shell_command and references /testbed, doing nothing in Aider).
# It explores the repo with its own tools, so no files are passed in.
#
# Usage:   scripts/qwen-loop.sh [max_iterations]        (default 15)
# Env:     MAX_ITERATIONS      same as the argument
#          ITER_TIMEOUT_MIN    kill one qwen run after this long (default 30)
#          LLAMA_BASE_URL      OpenAI-compatible base URL (default :8081/v1)
#          QWEN_MODEL          model id the server serves (default qwen3-coder-next)
#          NTFY_TOPIC          optional; also read from .env
#
# SERVER: llama-server must be serving Qwen3-Coder-Next at $LLAMA_BASE_URL.
#   See the header of scripts/aider-loop.sh for the exact llama-server command.
#
# GUARDRAILS: --yolo auto-approves ALL tool calls, but they run inside Qwen
#   Code's macOS Seatbelt sandbox (--sandbox sandbox-exec, profile
#   permissive-open: writes confined to this project + temp, network allowed for
#   the local model and uv). Verified: `uv run pytest` works confined. Defence
#   in depth on top of the sandbox:
#     - the loop refuses a dirty tree and `git reset --hard` on a failed iteration
#     - a .git/hooks/pre-push hook blocks pushes (see install-guardrails note below)
#     - the prompt forbids git push/commit, rm -rf, and out-of-repo writes
#     - run it on a dedicated branch
#   (Note: tools.executionSandbox in settings.json is Linux-only — bwrap/landlock;
#   macOS uses the sandbox-exec Seatbelt backend wired above.)
#
#   install the pre-push guard once:
#     printf '#!/bin/sh\necho "push blocked by qwen-loop guardrail" >&2; exit 1\n' \
#       > .git/hooks/pre-push && chmod +x .git/hooks/pre-push
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Keep the Mac awake for the whole loop: re-exec this script under caffeinate.
if [ -z "${NEWNEWS_CAFFEINATED:-}" ]; then
  export NEWNEWS_CAFFEINATED=1
  exec caffeinate -dims "$0" "$@"
fi

MAX_ITERATIONS="${1:-${MAX_ITERATIONS:-15}}"
ITER_TIMEOUT_MIN="${ITER_TIMEOUT_MIN:-30}"
LLAMA_BASE_URL="${LLAMA_BASE_URL:-http://127.0.0.1:8081/v1}"
QWEN_MODEL="${QWEN_MODEL:-qwen3-coder-next}"

# Qwen Code reads these three at startup to select the OpenAI-compatible provider
# (all three must be set and non-empty). The key is a placeholder; llama-server
# ignores it. Telemetry is off so a local-first setup stays local.
export OPENAI_BASE_URL="$LLAMA_BASE_URL"
export OPENAI_API_KEY="${OPENAI_API_KEY:-local-llama-no-key}"
export OPENAI_MODEL="$QWEN_MODEL"
export QWEN_CODE_SUPPRESS_YOLO_WARNING=1
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

PROMPT="You are completing exactly ONE task in this git repository. Do the steps in order; do not skip any.
1. Read AGENTS.md in full. It is the authority on rules, commands, style and workflow.
2. Read TASKS.md. Find the FIRST line beginning with '- [ ]' (the first unchecked task). That single task is your entire job; ignore every other task.
3. Re-read that task's description and its 'Done when' line so you know exactly what done means.
4. Write or update the tests for this task FIRST, under tests/. Use fixtures in tests/fixtures/; never touch the network in tests.
5. Implement the minimal code to make those tests pass. Keep all changes scoped to this one task. Follow AGENTS.md style: type hints, small pure functions, logging not print, every config value has a default.
6. Run the full suite with your shell tool: uv run pytest
7. ONLY if every test passes: change that task's '- [ ]' to '- [x]' in TASKS.md, and APPEND a dated entry at the very END of PROGRESS.md — after the last existing entry, newest last. Do NOT insert it near the top or above older entries. Use the template at the top of that file.
8. If you are blocked or cannot finish, do NOT guess: append the blocker to PROGRESS.md and stop.
Do not modify any other unchecked task. Never run 'git push' or 'git commit' (the loop handles commits). Never run 'rm -rf' outside build/ or state/, and never write outside this repository."

mkdir -p logs
LOG="logs/qwen-loop-$(date +%Y-%m-%d).log"

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
  curl -fsS -m 10 -H "Title: NewNews qwen loop" -d "$1" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
    || log "WARN ntfy ping failed"
}

# Run one Qwen Code session with a watchdog (macOS has no `timeout` command).
# -p "<prompt>" --yolo: headless, auto-approve every tool call. The agent reads,
# edits, and runs the tests itself; the loop below is the real pass/fail gate.
run_agent() {
  qwen -p "$PROMPT" --yolo --sandbox sandbox-exec >> "$LOG" 2>&1 &
  local pid=$!
  ( sleep $((ITER_TIMEOUT_MIN * 60)); kill "$pid" 2>/dev/null ) &
  local watchdog=$!
  local status=0
  wait "$pid" || status=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  return "$status"
}

for tool in qwen uv git; do
  command -v "$tool" >/dev/null || { log "ERROR $tool not found on PATH"; exit 1; }
done
git rev-parse --git-dir >/dev/null 2>&1 || { log "ERROR not a git repo"; exit 1; }
if [ -n "$(git status --porcelain)" ]; then
  log "ERROR working tree not clean; commit or stash first (the loop uses git reset --hard)"
  exit 1
fi
if ! curl -fsS -m 5 "${LLAMA_BASE_URL%/v1}/health" >/dev/null 2>&1; then
  log "ERROR model server not reachable at $LLAMA_BASE_URL (start llama-server first)"
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
  [ "$agent_status" -eq 0 ] || log "WARN qwen exited with status $agent_status"

  if uv run pytest >> "$LOG" 2>&1; then
    git add -A
    if ! git diff --cached --quiet; then
      git commit -q -m "qwen-loop: iteration $i (tests pass)" >> "$LOG" 2>&1
    fi
    after=$(unchecked)
    passed=$((passed + 1))
    log "PASS iteration $i: tests pass, $after unchecked, HEAD $(git rev-parse --short HEAD)"
    if [ "$after" -ge "$before" ]; then
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

summary="NewNews qwen loop stopped: $stop_reason. passed=$passed failed=$failed unchecked=$(unchecked). Log: $LOG"
log "$summary"
notify "$summary"
