"""Doctor: is this clone ready? CORE_READY is offline; the egress row is the one network check."""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import sys
from pathlib import Path

from adapters import config, paths
from adapters.setup import MIN_PYTHON

CHROME_CANDIDATES = {
    "posix": ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/snap/bin/chromium", "/usr/local/bin/chromium"],
    "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
               "/Applications/Chromium.app/Contents/MacOS/Chromium"],
    "win": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
}


def find_browser() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "darwin":
        candidates = CHROME_CANDIDATES["darwin"]
    elif os.name == "nt":
        candidates = CHROME_CANDIDATES["win"]
    else:
        candidates = CHROME_CANDIDATES["posix"]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def run(as_json: bool = False, show_paths: bool = False) -> int:
    core: list[tuple[str, str, str]] = []
    live: list[tuple[str, str, str]] = []
    browser: list[tuple[str, str, str]] = []
    problems: list[str] = []

    def row(state: str, name: str, detail: str) -> None:
        if name == "browser":
            browser.append((state, name, detail))
        elif name == "ats egress":
            live.append((state, name, detail))
        else:
            core.append((state, name, detail))
        if state == "MISS":
            problems.append(name)

    version = ".".join(str(x) for x in sys.version_info[:3])
    row("PASS" if sys.version_info[:2] >= MIN_PYTHON else "MISS", "python",
        version if sys.version_info[:2] >= MIN_PYTHON else f"{version} (need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")

    for module in ("pandas", "dotenv", "jsonschema"):
        try:
            __import__(module)
            row("PASS", f"import {module}", "")
        except ImportError as error:
            row("MISS", f"import {module}", str(error))

    explicit = os.environ.get("JOBKIT_FILTERS")
    active = paths.ROOT / "filters" / "active.json"
    filters = Path(explicit) if explicit else (active if active.exists() else paths.ROOT / "filters" / "example.json")
    if not filters.exists():
        row("MISS", "filters", f"{filters} not found")
    else:
        try:
            doc = json.loads(filters.read_text())
            import jsonschema
            schema = json.loads((paths.ROOT / "filters" / "schema.json").read_text())
            errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
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

    try:
        cfg = config.notify_config()
        row("PASS", "notify", cfg["target"])
    except Exception as error:
        row("MISS", "notify", str(error))

    batches = sorted((paths.ROOT / "fixtures" / "run1").glob("job_listings_*.csv"))
    row("PASS" if batches else "MISS", "fixtures", f"{len(batches)} batch(es) in {paths.ROOT / 'fixtures' / 'run1'}")

    host = "boards-api.greenhouse.io"
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=4) as raw:
            with context.wrap_socket(raw, server_hostname=host):
                row("PASS", "ats egress", host)
    except OSError as error:
        row("WARN", "ats egress", f"{host}: {error}")

    found = find_browser()
    try:
        __import__("seleniumbase")
        row("PASS" if found else "WARN", "browser", found or "seleniumbase present, no Chrome/Chromium found")
    except ImportError:
        row("WARN", "browser", "seleniumbase not installed (pip install -r requirements-browser.txt)")

    core_ready = not problems
    payload = {
        "CORE_READY": core_ready,
        "LIVE_READY": any(state == "PASS" for state, _, _ in live),
        "BROWSER_READY": any(state == "PASS" for state, _, _ in browser),
        "checks": [{"state": s, "name": n, "detail": d} for s, n, d in core + live + browser],
    }
    if as_json:
        print(json.dumps(payload, indent=1))
    else:
        for state, name, detail in core + live + browser:
            print(f"{state:5} {name:16} {detail}".rstrip())
        print("CORE_READY" if core_ready else "CORE_NOT_READY: " + ", ".join(problems))
    if show_paths:
        print(f"python={sys.executable}")
        print(f"clone={paths.ROOT}")
        print(f"data={paths.data_root()}")
    return 0 if core_ready else 1
