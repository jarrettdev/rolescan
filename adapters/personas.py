"""Four test users: run every filters/personas document against the fixtures, one CSV each."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from adapters import paths


def run() -> int:
    output_dir = paths.data_root() / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    personas = sorted((paths.ROOT / "filters" / "personas").glob("*.json"))
    if not personas:
        print("PERSONAS:NOT_MET no filters/personas/*.json")
        return 1
    print(f"{'persona':<10} {'rows':<5} matches")
    rc = 0
    for filters in personas:
        name = filters.stem
        env = {**os.environ, "NOTIFY": "print", "JOBKIT_FILTERS": ""}
        env.pop("JOBKIT_FILTERS", None)
        result = subprocess.run(
            [sys.executable, str(paths.ROOT / "process_stream.py"), "--fixtures", str(paths.ROOT / "fixtures" / "run1"),
             "--dry-run", "--filters", str(filters), "--csv", str(output_dir / f"{name}.csv")],
            cwd=paths.ROOT, env=env, capture_output=True, text=True)
        rows = 0
        for line in result.stdout.splitlines():
            if line.startswith("csv=") and " rows=" in line:
                rows = int(line.rsplit(" rows=", 1)[1])
        summary = next((line for line in result.stdout.splitlines() if line.startswith("batches=")), "")
        print(f"{name:<10} {rows:<5} {summary.removeprefix('batches=1 ')}")
        if result.returncode != 0 or rows <= 0:
            print(f"  no rows for {name}: check {filters}")
            if result.stderr:
                print(f"  {result.stderr.strip().splitlines()[-1]}")
            rc = 1
    print(f"PERSONAS:{'MET' if rc == 0 else 'NOT_MET'} (csvs in {output_dir})")
    return rc
