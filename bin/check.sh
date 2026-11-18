#!/usr/bin/env bash
# Core gate: everything that must pass offline, with no .env, no network, no node.
set -uo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."
PY=venv/bin/python
rc=0
if [ ! -x "$PY" ]; then echo "CHECK:NOT_MET run ./setup.sh first"; exit 1; fi

echo "== COMPILE"
"$PY" -m compileall -q . || rc=1

echo "== SECRETS"
bin/secret-scan || rc=1

echo "== DOCS"
bin/docs-check || rc=1

echo "== DOCTOR"
if "$PY" - <<'PY'
import json, subprocess
out = subprocess.run(["bash", "doctor.sh", "--json"], capture_output=True, text=True)
data = json.loads(out.stdout)
if not data["CORE_READY"]:
    print("doctor: " + ", ".join(c["name"] for c in data["checks"] if c["state"] == "MISS"))
    raise SystemExit(1)
PY
then echo "DOCTOR:MET"; else echo "DOCTOR:NOT_MET"; rc=1; fi

echo "== TESTS"
for file in tests/test_*.py goals/*/tests/test_*.py domain/*/tests/test_*.py; do
  [ -f "$file" ] || continue
  if ! out=$("$PY" "$file" 2>&1); then
    echo "TEST:NOT_MET $file"; echo "$out" | tail -5; rc=1
  else
    echo "$out" | tail -1
  fi
done

echo "== FIXTURE RUN"
if out=$("$PY" process_stream.py --fixtures fixtures/run1 --dry-run --filters filters/example.json 2>&1); then
  echo "$out" | tail -2
  echo "$out" | grep -q "matched=3" || { echo "FIXTURE:NOT_MET expected matched=3"; rc=1; }
else
  echo "FIXTURE:NOT_MET"; echo "$out" | tail -5; rc=1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "== TREE"
  changed=$(git status --porcelain)
  if [ -n "$changed" ]; then echo "TREE:NOT_MET"; echo "$changed" | head -10; rc=1; else echo "TREE:MET"; fi
fi

[ "$rc" -eq 0 ] && echo "CHECK:MET" || echo "CHECK:NOT_MET"
exit "$rc"
