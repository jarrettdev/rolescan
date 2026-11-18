"""Setup: venv, dependencies, .env, filters, data. Idempotent, no prompts."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from adapters import paths

MIN_PYTHON = (3, 12)


def python_version(binary: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run([binary, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        major, minor = out.stdout.strip().split(".")[:2]
        return int(major), int(minor)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def find_python(explicit: str | None = None) -> str:
    """The interpreter to build the venv with: explicit, else this process, else PATH."""
    candidates = [explicit] if explicit else []
    candidates += [sys.executable, shutil.which("python3") or "", shutil.which("py") or ""]
    for candidate in candidates:
        if not candidate:
            continue
        version = python_version(candidate)
        if version and version >= MIN_PYTHON:
            return candidate
    found = ", ".join(str(c) for c in candidates if c) or "none"
    raise SystemExit(f"python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required; none found among: {found}")


def venv_python() -> Path:
    return paths.ROOT / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*, browser: bool = False, python: str | None = None) -> int:
    interpreter = find_python(python)
    version = python_version(interpreter)
    print(f"setup: interpreter {interpreter} ({version[0]}.{version[1]})")

    target = venv_python()
    if not target.exists():
        print("setup: creating venv/")
        subprocess.run([interpreter, "-m", "venv", str(paths.ROOT / "venv")], check=True)
    subprocess.run([str(target), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
    subprocess.run([str(target), "-m", "pip", "install", "--quiet", "-r", "requirements-core.txt"], check=True)
    if browser:
        subprocess.run([str(target), "-m", "pip", "install", "--quiet", "-r", "requirements-browser.txt"], check=True)

    env_file = paths.ROOT / ".env"
    if not env_file.exists():
        shutil.copyfile(paths.ROOT / ".env.example", env_file)
        env_file.chmod(0o600)
        print("setup: wrote .env from .env.example (fill your keys when you need to notify)")
    paths.data_root()
    active = paths.ROOT / "filters" / "active.json"
    if not active.exists():
        shutil.copyfile(paths.ROOT / "filters" / "example.json", active)
        active.chmod(0o600)
        print("setup: wrote filters/active.json from filters/example.json (edit your searches)")

    import json
    doc = json.loads(active.read_text())
    print(f"setup: lanes={len(doc['filters'])} locations={len(doc['locations'])}")
    print("setup: ok — next: ./doctor.sh")
    return 0
