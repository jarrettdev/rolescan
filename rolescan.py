#!/usr/bin/env python3
"""rolescan: one entry point for every platform-facing action."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if VENV.exists() and Path(sys.executable) != VENV:
    # setup creates the venv; after that every command should use it, even when
    # the caller ran the system interpreter.
    os.execv(str(VENV), [str(VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

from cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
