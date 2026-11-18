#!/usr/bin/env bash
# Is this clone ready? CORE_READY is offline (the ats egress row is the one network check);
# LIVE_READY and BROWSER_READY are optional.
#   ./doctor.sh          human lines, exit 1 only when CORE_READY is false
#   ./doctor.sh --json   machine-readable states
set -uo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
PY=venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" - "$@" <<'PY'
import json, os, shutil, socket, ssl, sys
from pathlib import Path

JSON = "--json" in sys.argv
core, live, browser = [], [], []
problems = []

def row(state, name, detail):
    # Route by what the row measures, not by its state: a browser WARN must not
    # count as LIVE_READY, and an egress PASS must not count as CORE_READY.
    if name == "browser":
        browser.append((state, name, detail))
    elif name == "ats egress":
        live.append((state, name, detail))
    else:
        core.append((state, name, detail))
    if state == "MISS":
        problems.append(name)

# --- core: python and imports (offline) ---
version = sys.version.split()[0]
if sys.version_info >= (3, 12):
    row("PASS", "python", version)
else:
    row("MISS", "python", f"{version} (need >= 3.12)")

for module in ("pandas", "dotenv", "jsonschema"):
    try:
        __import__(module)
        row("PASS", f"import {module}", "")
    except ImportError as error:
        row("MISS", f"import {module}", str(error))

# --- core: filters exist and validate ---
explicit = os.environ.get("JOBKIT_FILTERS")
active = Path("filters/active.json")
filters = Path(explicit) if explicit else (active if active.exists() else Path("filters/example.json"))
if not filters.exists():
    row("MISS", "filters", f"{filters} not found")
else:
    try:
        doc = json.loads(filters.read_text())
        import jsonschema
        schema = json.loads(Path("filters/schema.json").read_text())
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            pointer = "/" + "/".join(str(p) for p in first.path) if first.path else "/"
            row("MISS", "filters", f"{filters}: {pointer}: {first.message}")
        elif not doc.get("filters"):
            row("MISS", "filters", f"{filters}: no filters[] entries")
        else:
            locations = doc.get("locations") or {}
            bad = [(i, f.get("location")) for i, f in enumerate(doc["filters"]) if f.get("location") not in locations]
            if bad:
                index, name = bad[0]
                row("MISS", "filters", f"{filters}: /filters/{index}/location {name!r} is not a key in /locations")
            else:
                row("PASS", "filters", f"{filters} ({len(doc['filters'])} lanes)")
    except (ValueError, OSError) as error:
        row("MISS", "filters", f"{filters}: {error}")

# --- core: notify config for the chosen target ---
sys.path.insert(0, ".")
try:
    from adapters import config
    cfg = config.notify_config()
    row("PASS", "notify", cfg["target"])
except Exception as error:  # MissingSecret and friends are the point
    row("MISS", "notify", str(error))

# --- core: fixtures ---
fixtures = Path("fixtures/run1")
batches = sorted(fixtures.glob("job_listings_*.csv")) if fixtures.exists() else []
row("PASS" if batches else "MISS", "fixtures", f"{len(batches)} batch(es) in {fixtures}")

# --- live: ATS egress (optional) ---
host = "boards-api.greenhouse.io"
try:
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=4) as raw:
        with context.wrap_socket(raw, server_hostname=host):
            row("PASS", "ats egress", host)
except OSError as error:
    row("WARN", "ats egress", f"{host}: {error}")

# --- browser: optional ---
try:
    __import__("seleniumbase")
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    row("PASS" if chrome else "WARN", "browser", chrome or "seleniumbase present, no Chrome/Chromium on PATH")
except ImportError:
    row("WARN", "browser", "seleniumbase not installed (pip install -r requirements-browser.txt)")

core_ready = not problems
if JSON:
    print(json.dumps({
        "CORE_READY": core_ready,
        "LIVE_READY": any(state == "PASS" for state, _, _ in live),
        "BROWSER_READY": any(state == "PASS" for state, _, _ in browser),
        "checks": [{"state": s, "name": n, "detail": d} for s, n, d in core + live + browser],
    }, indent=1))
else:
    for state, name, detail in core + live + browser:
        print(f"{state:5} {name:16} {detail}".rstrip())
    print("CORE_READY" if core_ready else "CORE_NOT_READY: " + ", ".join(problems))
sys.exit(0 if core_ready else 1)
PY
