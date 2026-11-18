#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY=venv/bin/python; [ -x "$PY" ] || PY=python3
exec "$PY" rolescan.py doctor "$@"
