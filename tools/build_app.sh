#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Virtualenv not found at $VENV"
  exit 1
fi

# Ensure build deps and app deps
"$PY" -m pip install -U pip >/dev/null
"$PY" -m pip install "setuptools<81" wheel py2app >/dev/null
if [[ -f "$ROOT/requirements.txt" ]]; then
  "$PY" -m pip install -r "$ROOT/requirements.txt" >/dev/null
fi

# Clean previous build output
rm -rf "$ROOT/build" "$ROOT/dist"

# Optional: generate icon (will create BiliNotify.icns if possible)
if [[ -f "$ROOT/tools/make_icon.py" ]]; then
  "$PY" "$ROOT/tools/make_icon.py" || true
fi

# Build app (default alias mode to avoid dependency bundling issues)
cd "$ROOT"
MODE="${BUILD_MODE:-alias}"
if [[ "$MODE" == "standalone" ]]; then
  "$PY" setup.py py2app
else
  "$PY" setup.py py2app -A
fi

echo "Built app at: $ROOT/dist/B站关注通知.app (mode: $MODE)"
