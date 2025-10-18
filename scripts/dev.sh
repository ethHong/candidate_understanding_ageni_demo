#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# --- load env (local first) ---
load_env() {
  if [[ -f ".env.local" ]]; then set -a; source .env.local; set +a; fi
  if [[ -f ".env" ]]; then set -a; source .env; set +a; fi
}
load_env

# --- read OPENAI_API_KEY from file if not set ---
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -n "${OPENAI_API_KEY_FILE:-}" && -f "${OPENAI_API_KEY_FILE}" ]]; then
    export OPENAI_API_KEY="$(tr -d '[:space:]' < "${OPENAI_API_KEY_FILE}")"
    echo "[dev] Loaded OPENAI_API_KEY from ${OPENAI_API_KEY_FILE}"
  else
    echo "[dev] WARN: OPENAI_API_KEY not set (and no OPENAI_API_KEY_FILE). LLM 기능이 제한될 수 있어요." >&2
  fi
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
# macOS old bash: lower-case conversion without ${var,,}
LOG_LEVEL="$(printf '%s' "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

# --- venv ---
if [[ ! -d ".venv" ]]; then $PYTHON_BIN -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
if [[ -f "requirements.txt" ]]; then
  pip install -r requirements.txt
fi

# --- run server ---
exec uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --log-level "${LOG_LEVEL}"
