"""Selftest: the same seven sections as bin/check.sh, without bash."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from adapters import doctor, paths


def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(argv, cwd=str(cwd or paths.ROOT), capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def run() -> int:
    rc = 0

    print("== COMPILE")
    code, out = _run([sys.executable, "-m", "compileall", "-q", "adapters", "values", "domain", "goals",
                      "primitives", "tests", "cli", "rolescan.py", "process_stream.py", "hc_scraper.py",
                      "linkedin_lookup.py"])
    if code != 0:
        print(out[-800:])
        rc = 1

    print("== SECRETS")
    code, out = _run([sys.executable, "bin/secret-scan"])
    print(out.strip().splitlines()[-1] if out.strip() else "SECRET_SCAN:NO_OUTPUT")
    if code != 0:
        print(out)
        rc = 1

    print("== DOCS")
    code, out = _run([sys.executable, "bin/docs-check"])
    print(out.strip().splitlines()[-1] if out.strip() else "DOCS_CHECK:NO_OUTPUT")
    if code != 0:
        print(out)
        rc = 1

    print("== DOCTOR")
    if doctor.run(as_json=True) == 0:
        print("DOCTOR:MET")
    else:
        print("DOCTOR:NOT_MET")
        rc = 1

    print("== TESTS")
    files = (sorted(Path("tests").glob("test_*.py"))
             + sorted(Path("goals").glob("*/tests/test_*.py"))
             + sorted(Path("domain").glob("*/tests/test_*.py")))
    for file in files:
        code, out = _run([sys.executable, str(file)])
        if code != 0:
            print(f"TEST:NOT_MET {file}")
            print("\n".join(out.splitlines()[-5:]))
            rc = 1
        else:
            lines = [line for line in out.splitlines() if line.strip()]
            print(lines[-1] if lines else f"TEST:MET {file}")

    print("== FIXTURE RUN")
    code, out = _run([sys.executable, "process_stream.py", "--fixtures", "fixtures/run1", "--dry-run",
                      "--filters", "filters/example.json"])
    tail = [line for line in out.splitlines() if line.strip()][-2:]
    print("\n".join(tail))
    if code != 0 or "matched=3" not in out:
        print("FIXTURE:NOT_MET expected matched=3")
        rc = 1

    if _run(["git", "rev-parse", "--is-inside-work-tree"])[0] == 0:
        print("== TREE")
        code, out = _run(["git", "status", "--porcelain"])
        if out.strip():
            print("TREE:NOT_MET")
            print("\n".join(out.splitlines()[:10]))
            rc = 1
        else:
            print("TREE:MET")

    print("CHECK:MET" if rc == 0 else "CHECK:NOT_MET")
    return rc
