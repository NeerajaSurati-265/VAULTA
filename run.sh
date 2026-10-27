#!/usr/bin/env bash
# Starts the VAULTA backend (FastAPI) and UI (Streamlit) together.
# Usage: ./run.sh        (from anywhere; settings come from env vars, see README)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
# So `import app...` works for both uvicorn and streamlit
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Use the project venv automatically if one exists and none is active
if [[ -z "${VIRTUAL_ENV:-}" && -f "$REPO_ROOT/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.venv/bin/activate"
fi

# Read the effective settings from app/config.py (env vars + defaults) so
# run.sh and the app can never disagree about a default.
read -r OLLAMA_URL VAULTA_MODEL VAULTA_BACKEND_URL VAULTA_RETRIEVAL_MODE VAULTA_EMBED_MODEL < <(python -c "
from app import config as c
print(c.OLLAMA_URL, c.MODEL, c.BACKEND_URL, c.RETRIEVAL_MODE, c.EMBED_MODEL)")
export OLLAMA_URL VAULTA_MODEL VAULTA_BACKEND_URL VAULTA_RETRIEVAL_MODE VAULTA_EMBED_MODEL

# --- 1. Check Ollama is reachable and the models are pulled ---
if ! tags="$(curl -fsS -m 5 "$OLLAMA_URL/api/tags" 2>/dev/null)"; then
    echo "ERROR: Cannot reach Ollama at $OLLAMA_URL." >&2
    echo "       Install it from https://ollama.com and start it with: ollama serve" >&2
    exit 1
fi
# Ollama lists models as "name":"qwen2.5:3b"; untagged pulls appear as "<name>:latest"
has_model() {
    grep -qF "\"name\":\"$1\"" <<<"$tags" || grep -qF "\"name\":\"$1:latest\"" <<<"$tags"
}
require_model() {
    if ! has_model "$1"; then
        echo "ERROR: Model '$1' is not pulled in Ollama." >&2
        echo "       Run: ollama pull $1" >&2
        exit 1
    fi
}
require_model "$VAULTA_MODEL"
# Only the semantic retrieval modes need the embedding model
case "$VAULTA_RETRIEVAL_MODE" in
    semantic|hybrid) require_model "$VAULTA_EMBED_MODEL" ;;
esac
echo "Ollama OK at $OLLAMA_URL (chat model: $VAULTA_MODEL, retrieval: $VAULTA_RETRIEVAL_MODE, embed model: $VAULTA_EMBED_MODEL)"

# --- 2. Start the backend in the background ---
# Host/port are taken from VAULTA_BACKEND_URL so the UI and backend always agree
read -r BACKEND_HOST BACKEND_PORT < <(python -c "
from urllib.parse import urlparse
u = urlparse('$VAULTA_BACKEND_URL')
print(u.hostname or '127.0.0.1', u.port or 8000)")

echo "Starting backend on $BACKEND_HOST:$BACKEND_PORT ..."
python -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

# Stop the backend whenever this script exits (Ctrl+C, UI closed, or error)
cleanup() {
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (pid $BACKEND_PID) ..."
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# --- 3. Wait for /health (startup indexes data/documents, which can take a few seconds) ---
for _ in $(seq 1 60); do
    if curl -fsS -m 2 "$VAULTA_BACKEND_URL/health" >/dev/null 2>&1; then
        echo "Backend is up at $VAULTA_BACKEND_URL"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "ERROR: Backend exited during startup; see the log above." >&2
        exit 1
    fi
    sleep 1
done
if ! curl -fsS -m 2 "$VAULTA_BACKEND_URL/health" >/dev/null 2>&1; then
    echo "ERROR: Backend did not become healthy within 60 seconds." >&2
    exit 1
fi

# --- 4. Start the UI in the foreground; backend stops when it exits ---
# No usage stats: VAULTA makes no external calls
python -m streamlit run app/ui.py --browser.gatherUsageStats false
