"""Four test users, no keys (ADRs 0019): every persona produces a CSV from the fixtures."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = sorted((ROOT / "filters" / "personas").glob("*.json"))


def test_personas_are_present():
    names = {p.stem for p in PERSONAS}
    assert {"intern", "new-grad", "swe", "data"} <= names, names


def test_personas_run_without_keys_and_write_csv():
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "JOBKIT_DATA": str(Path(tmp) / "data"), "NOTIFY": "print"}
        env.pop("JOBKIT_FILTERS", None)
        result = subprocess.run(["bash", str(ROOT / "bin" / "personas")], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PERSONAS:MET" in result.stdout
        results = Path(tmp) / "data" / "results"
        for persona in ("intern", "new-grad", "swe", "data"):
            path = results / f"{persona}.csv"
            assert path.exists(), f"{persona}: no csv"
            lines = path.read_text().strip().splitlines()
            assert len(lines) >= 2, f"{persona}: csv has no rows ({len(lines)} lines)"
            assert lines[0].startswith("title,company,location,salary,lane,url"), lines[0]
        intern = (results / "intern.csv").read_text()
        assert "Delta Works" in intern, intern
        newgrad = (results / "new-grad.csv").read_text()
        assert "Epsilon Analytics" in newgrad, newgrad


if __name__ == "__main__":
    import glob
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"PERSONAS:MET {len(tests)} tests")
