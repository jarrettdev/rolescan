"""run-once (adrs/0018/0019): the fixture batch notifies the lane matches, a
filter edit changes them, and dry runs never write state."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"
FIXTURES = ROOT / "fixtures" / "run1"
EXAMPLE = ROOT / "filters" / "example.json"


def run(*args, data_root, filters=None):
    env = {**os.environ, "JOBKIT_DATA": str(data_root), "NOTIFY": "print"}
    env.pop("JOBKIT_FILTERS", None)
    if filters:
        env["JOBKIT_FILTERS"] = str(filters)
    command = [str(PY), str(ROOT / "process_stream.py"), "--fixtures", str(FIXTURES), "--dry-run", *args]
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)


def newgrad_filters(directory: Path) -> Path:
    doc = json.loads(EXAMPLE.read_text())
    doc["filters"].append({"name": "New grad and internships", "location": "US", "overrides": {
        "jobTitleQuery": 'Intern OR Internship OR "New Grad" OR Graduate',
        "technologyKeywordsQuery": "Python OR SQL",
        "searchQuery": ""}})
    path = directory / "filters.json"
    path.write_text(json.dumps(doc))
    return path


def test_baseline_matches_the_three_lane_rows():
    with tempfile.TemporaryDirectory() as tmp:
        result = run(data_root=Path(tmp) / "data", filters=EXAMPLE)
    assert result.returncode == 0, result.stderr
    assert "matched=4" in result.stdout and "notified=3" in result.stdout, result.stdout
    assert "Acme Systems" in result.stdout and "Zeta Corp" not in result.stdout
    assert "Delta Works" not in result.stdout and "Epsilon Analytics" not in result.stdout


def test_newgrad_filter_changes_the_matches():
    with tempfile.TemporaryDirectory() as tmp:
        path = newgrad_filters(Path(tmp))
        result = run(data_root=Path(tmp) / "data", filters=path)
    assert result.returncode == 0, result.stderr
    assert "matched=6" in result.stdout and "notified=5" in result.stdout, result.stdout
    assert "Delta Works" in result.stdout and "Epsilon Analytics" in result.stdout


def test_missing_filters_file_exits_two():
    with tempfile.TemporaryDirectory() as tmp:
        result = run(data_root=Path(tmp) / "data", filters=Path(tmp) / "nope.json")
    assert result.returncode == 2 and "FILTERS_MISSING" in result.stderr


def test_non_dry_run_records_into_the_data_root():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        first = subprocess.run([str(PY), str(ROOT / "process_stream.py"), "--fixtures", str(FIXTURES),
                                "--filters", str(EXAMPLE)],
                               cwd=ROOT, env={**os.environ, "JOBKIT_DATA": str(data), "NOTIFY": "print"},
                               capture_output=True, text=True)
        assert first.returncode == 0, first.stderr
        assert (data / "processed_jobs.csv").exists(), "ledger missing"
        second = subprocess.run([str(PY), str(ROOT / "process_stream.py"), "--once",
                                 str(sorted((data / "drop").rglob("job_listings_*.csv"))[0]),
                                 "--filters", str(EXAMPLE)],
                                cwd=ROOT, env={**os.environ, "JOBKIT_DATA": str(data), "NOTIFY": "print"},
                                capture_output=True, text=True)
        assert second.returncode == 0
        assert "notified=0" in second.stdout and "repeats=3" in second.stdout, second.stdout


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"RUN_ONCE:MET {len(tests)} tests")
