#!/bin/bash
# Unattended build-out loop: one TASKS.md item per iteration, via Aider.
#
# This is the Aider-based sibling of scripts/agent-loop.sh (OpenCode). It exists
# because for a LOCAL model on llama.cpp (Qwen3-Coder-Next), Aider's text
# edit-blocks are far more reliable than OpenCode's native JSON tool-calls,
# which hit a documented write-tool JSON bug with this exact stack. Aider never
# touches llama.cpp's tool-call path, so that failure mode disappears.
#
# Usage:   scripts/aider-loop.sh [max_iterations]        (default 15)
# Env:     MAX_ITERATIONS      same as the argument
#          ITER_TIMEOUT_MIN    kill one aider run after this long (default 30)
#          LLAMA_BASE_URL      OpenAI-compatible base URL (default :8081/v1)
#          AIDER_MODEL         model id as Aider sees it (default openai/qwen3-coder-next)
#          NTFY_TOPIC          optional; also read from .env
#
# Each iteration:
#   1. stop if TASKS.md has no unchecked "- [ ]" items
#   2. aider --message "<prompt>"  (edits files; self-corrects via --auto-test)
#   3. run the tests; pass -> commit, fail -> git reset --hard to last good commit
#
# ---------------------------------------------------------------------------
# SERVER (run this once, separately, before the loop — e.g. via launchd):
#   llama-server \
#     --model /Users/agent/models/Qwen3-Coder-Next-GGUF/UD-Q8_K_XL/Qwen3-Coder-Next-UD-Q8_K_XL-00001-of-00003.gguf \
#     --alias qwen3-coder-next \
#     --host 127.0.0.1 --port 8081 \
#     --jinja \
#     --ctx-size 262144 \
#     --n-gpu-layers 999 \
#     --temp 0.2 --top-p 0.8
#   (--jinja is harmless here: Aider doesn't use tool-calls, but it keeps the
#    server usable by OpenCode too. llama-server auto-loads shards 2 and 3 from
#    the 00001 path. Tune --ctx-size down if KV cache memory is a concern.)
#
# WHY --edit-format whole (not diff): a benchmark found qwen3-coder scored
#   100/100 in whole mode and 0/100 in diff mode (a false-negative: correct code,
#   unparsed diff). Aider's own Qwen3 llama.cpp runs show whole mode at a 100%
#   correct-edit-format rate. Do NOT switch to diff without re-testing.
#
# GUARDRAILS (replacing opencode.json's deny engine): Aider's surface is narrow
#   by design — it edits the files added to the chat, runs ONLY the --test-cmd
#   below, and commits; it does not run arbitrary shell and never pushes. For
#   defence in depth, add a pre-push git hook that blocks pushes, and always run
#   this loop on a dedicated branch.
#
# CONTEXT WINDOW: if Aider warns "unknown context window", point it at a
#   .aider.model.metadata.json that sets this model's context_window (262144)
#   via --model-metadata-file, so it uses the full window instead of a small
#   default. Left out here to keep the first run simple.
# ---------------------------------------------------------------------------
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
AIDER_MODEL="${AIDER_MODEL:-openai/qwen3-coder-next}"
# Tells Aider this model's context window (262144) and that it is free, instead
# of it warning "unknown context window ... using sane defaults" and guessing.
AIDER_MODEL_METADATA="${AIDER_MODEL_METADATA:-/Users/agent/models/qwen3-coder-next.aider.metadata.json}"

# Aider needs *a* key for the OpenAI-compatible path even though llama-server
# ignores it. A placeholder is fine; this is a local server.
export OPENAI_API_KEY="${OPENAI_API_KEY:-local-llama-no-key}"

# A tool-trained model following edit-blocks does not need the heavy
# "one tool call per turn" discipline the OpenCode prompt carries — Aider parses
# edits from plain text. Keep the task steps explicit; that helps any model.
PROMPT="You are completing exactly ONE task in this git repository. Do the steps in order; do not skip any.
1. Read AGENTS.md in full. It is the authority on rules, commands, style and workflow.
2. Read TASKS.md. Find the FIRST line beginning with '- [ ]' (the first unchecked task). That single task is your entire job; ignore every other task.
3. Re-read that task's description and its 'Done when' line so you know exactly what done means.
4. Write or update the tests for this task FIRST, under tests/. Use fixtures in tests/fixtures/; never touch the network in tests.
5. Implement the minimal code to make those tests pass. Keep all changes scoped to this one task. Follow AGENTS.md style: type hints, small pure functions, logging not print, every config value has a default.
6. Make sure the full suite passes: uv run pytest
7. ONLY if every test passes: change that task's '- [ ]' to '- [x]' in TASKS.md, and append a dated entry to PROGRESS.md using the template at the top of that file.
8. If you are blocked or cannot finish, do NOT guess: append the blocker to PROGRESS.md and stop.
Do not modify any other unchecked task. Never run git push."

mkdir -p logs
LOG="logs/aider-loop-$(date +%Y-%m-%d).log"

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
  curl -fsS -m 10 -H "Title: NewNews aider loop" -d "$1" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
    || log "WARN ntfy ping failed"
}

# Run one Aider session with a watchdog (macOS has no `timeout` command).
# --no-auto-commits: the loop owns commits (commit on pass / reset on fail),
#   so a half-finished edit is never committed.
# --auto-test + --test-cmd: Aider runs the suite after editing and gets a chance
#   to self-correct before returning; the loop then re-tests as the real gate.
# Files added to the chat: the rule/checklist files it must read & edit, plus
#   the source and test trees. Qwen3-Coder-Next's large context absorbs this;
#   tighten to the task's module later if you want leaner runs.
run_agent() {
  aider \
    --model "$AIDER_MODEL" \
    --openai-api-base "$LLAMA_BASE_URL" \
    --model-metadata-file "$AIDER_MODEL_METADATA" \
    --edit-format whole \
    --no-auto-commits \
    --yes-always \
    --no-analytics \
    --no-check-update \
    --test-cmd "uv run pytest" \
    --auto-test \
    --message "$PROMPT" \
    AGENTS.md TASKS.md PROGRESS.md src/commute_news tests \
    >> "$LOG" 2>&1 &
  local pid=$!
  ( sleep $((ITER_TIMEOUT_MIN * 60)); kill "$pid" 2>/dev/null ) &
  local watchdog=$!
  local status=0
  wait "$pid" || status=$?
  kill "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  return "$status"
}

for tool in aider uv git; do
  command -v "$tool" >/dev/null || { log "ERROR $tool not found on PATH"; exit 1; }
done
git rev-parse --git-dir >/dev/null 2>&1 || { log "ERROR not a git repo"; exit 1; }
if [ -n "$(git status --porcelain)" ]; then
  log "ERROR working tree not clean; commit or stash first (the loop uses git reset --hard)"
  exit 1
fi

# Fail fast if the model server is not reachable.
if ! curl -fsS -m 5 "${LLAMA_BASE_URL%/v1}/health" >/dev/null 2>&1 \
   && ! curl -fsS -m 5 "${LLAMA_BASE_URL}/models" >/dev/null 2>&1; then
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
  [ "$agent_status" -eq 0 ] || log "WARN aider exited with status $agent_status"

  if uv run pytest >> "$LOG" 2>&1; then
    git add -A
    if ! git diff --cached --quiet; then
      git commit -q -m "aider-loop: iteration $i (tests pass)" >> "$LOG" 2>&1
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

summary="NewNews aider loop stopped: $stop_reason. passed=$passed failed=$failed unchecked=$(unchecked). Log: $LOG"
log "$summary"
notify "$summary"
