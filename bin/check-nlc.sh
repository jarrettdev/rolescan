#!/usr/bin/env bash
# NLC gate: needs the hub (0.8.0). Rules, rule IR and the call tree, all deterministic.
set -uo pipefail
cd "$(dirname "$0")/.."
rc=0
version=$(cat .nlc/lock.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["hub"])')
[ "$version" = "0.8.0" ] || { echo "NLC:NOT_MET lock hub=$version (expected 0.8.0)"; rc=1; }
./nlc maintainer rule-coverage --check || rc=1
./nlc maintainer rule-runner --check || rc=1
./nlc maintainer call-tree --check || rc=1
[ "$rc" -eq 0 ] && echo "NLC:MET" || echo "NLC:NOT_MET"
exit "$rc"
