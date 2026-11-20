"""The one entry point (adrs/0022): every command answers, and the ones with an
oracle produce their result without a subprocess at the top level."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "rolescan.py")]
COMMANDS = ["setup", "doctor", "personas", "poll", "ingest", "registry", "selftest", "sha256"]


def run(*args, env=None):
    return subprocess.run(CLI + list(args), cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, "NOTIFY": "print", **(env or {})})


def test_top_level_help_lists_every_command():
    result = run("--help")
    assert result.returncode == 0, result.stderr
    for name in COMMANDS:
        assert name in result.stdout, f"{name} missing from --help"


def test_every_command_answers_help():
    for name in COMMANDS:
        result = run(name, "--help")
        assert result.returncode == 0, f"{name} --help: {result.stderr}"


def test_doctor_json_keys_and_paths():
    result = run("doctor", "--json", "--paths")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.split("\npython=")[0])
    assert set(payload) == {"CORE_READY", "LIVE_READY", "BROWSER_READY", "checks"}, payload.keys()
    assert all(set(check) == {"state", "name", "detail"} for check in payload["checks"])
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line and not line.startswith("{"))
    for key in ("python", "clone", "data"):
        assert key in lines, lines
        assert Path(lines[key]).exists(), lines[key]


def test_ingest_writes_csv_and_reports_matches():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "out.csv"
        result = run("ingest", "--fixtures", "fixtures/run1", "--dry-run",
                     "--filters", "filters/example.json", "--csv", str(target),
                     env={"JOBKIT_DATA": str(Path(tmp) / "data")})
        assert result.returncode == 0, result.stderr
        assert "matched=3" in result.stdout
        lines = target.read_text().strip().splitlines()
        assert lines[0].startswith("title,company") and len(lines) >= 2


def test_registry_show_json_with_an_empty_registry():
    with tempfile.TemporaryDirectory() as tmp:
        result = run("registry", "show", "--json", env={"JOBKIT_DATA": str(Path(tmp) / "data")})
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["boards"] == 0 and payload["by_ats"] == {}


def test_poll_dry_run_with_no_boards():
    with tempfile.TemporaryDirectory() as tmp:
        result = run("poll", "--dry-run", env={"JOBKIT_DATA": str(Path(tmp) / "data")})
        assert result.returncode == 0, result.stderr
        assert "ATS_POLL:" in result.stdout and "dry_run=1" in result.stdout


def test_sha256_hashes_and_verifies():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "blob.txt"
        target.write_text("rolescan\n")
        hashed = run("sha256", str(target))
        assert hashed.returncode == 0
        digest = hashed.stdout.split()[0]
        sums = Path(tmp) / "SHA256SUMS"
        sums.write_text(f"{digest}  {target}\n")
        assert run("sha256", "--check", str(sums)).returncode == 0
        target.write_text("changed\n")
        assert run("sha256", "--check", str(sums)).returncode == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"CLI:MET {len(tests)} tests")
