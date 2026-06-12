#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${COASYS_HOST:-127.0.0.1}"
PORT="${COASYS_PORT:-5050}"
BASE_URL="http://${HOST}:${PORT}"
SERVER_LOG="workspace/state/release-smoke-server.log"

echo "== Static checks =="
uv run --extra dev ruff check .
uv run --extra dev pytest -q
git diff --check

echo "== Fleet state =="
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md

echo "== API smoke =="
if lsof -ti "tcp:${PORT}" >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use. Stop the existing service or set COASYS_PORT." >&2
  exit 1
fi

uv run coasys serve --host 127.0.0.1 --port "${PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "${SERVER_PID}" >/dev/null 2>&1 || true
  wait "${SERVER_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

READY=0
for _ in $(seq 1 30); do
  if curl -fs "${BASE_URL}/api/summary" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "${READY}" -ne 1 ]]; then
  echo "Dashboard smoke server did not become ready. Last server log:" >&2
  tail -n 80 "${SERVER_LOG}" >&2 || true
  exit 1
fi

COASYS_SMOKE_URL="${BASE_URL}/api/summary" python - <<'PY'
import json
import os
from urllib.request import urlopen

summary = json.load(urlopen(os.environ["COASYS_SMOKE_URL"], timeout=10))
assert summary["repo_count"] == 98, summary
assert summary["cloned_count"] == 98, summary
assert summary["dirty_count"] == 0, summary
assert summary["behind_count"] == 0, summary
PY

curl -fsS "${BASE_URL}/api/report" >/dev/null
curl -fsS "${BASE_URL}/favicon.ico" >/dev/null || true

if command -v chrome-devtools-axi >/dev/null 2>&1; then
  chrome-devtools-axi open "${BASE_URL}" >/dev/null
  chrome-devtools-axi wait 1000 >/dev/null
  chrome-devtools-axi console --type error | grep -q "<no console messages found>"
fi

echo "Release verification passed."
