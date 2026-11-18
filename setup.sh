#!/usr/bin/env bash
# One-time setup: venv, dependencies, .env, filters/active.json, data/.
# Idempotent. Never overwrites an existing .env or filters/active.json.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --browser) BROWSER=1 ;;
    --no-input) ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"python >= 3.12 required, found {sys.version.split()[0]}")
PY

if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/python -m pip install --quiet --upgrade pip
./venv/bin/python -m pip install --quiet -r requirements-core.txt
if [ "$BROWSER" -eq 1 ]; then
  ./venv/bin/python -m pip install --quiet -r requirements-browser.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "wrote .env from .env.example (fill your keys when you need to notify)"
fi
mkdir -p data
if [ ! -f filters/active.json ]; then
  cp filters/example.json filters/active.json
  chmod 600 filters/active.json
  echo "wrote filters/active.json from filters/example.json (edit your searches)"
fi

./venv/bin/python - <<'PY'
import json, sys
from pathlib import Path
doc = json.loads(Path('filters/active.json').read_text())
print(f"setup: lanes={len(doc['filters'])} locations={len(doc['locations'])}")
PY
echo "setup: ok — next: ./doctor.sh"
