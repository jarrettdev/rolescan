"""doctor.sh (adrs/0018): CORE_READY on a good tree, a JSON pointer on a bad
filters document, and exit 1 only for core failures."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def doctor(**env_overrides):
    env = {**os.environ, **env_overrides}
    return subprocess.run(["bash", str(ROOT / "doctor.sh"), "--json"], cwd=ROOT, env=env,
                          capture_output=True, text=True)


def test_good_tree_is_core_ready():
    result = doctor()
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["CORE_READY"] is True
    states = {check["name"]: check["state"] for check in payload["checks"]}
    assert states["filters"] == "PASS" and states["notify"] == "PASS"


def test_bad_filters_report_a_pointer():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text(json.dumps({"note": "x", "base": {}, "locations": {}, "filters": [{"name": "x"}]}))
        result = doctor(JOBKIT_FILTERS=str(bad))
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["CORE_READY"] is False
    filters = next(check for check in payload["checks"] if check["name"] == "filters")
    assert filters["state"] == "MISS" and "/filters/0" in filters["detail"], filters


def test_discord_without_token_is_a_core_miss():
    result = doctor(NOTIFY="discord", DISCORD_BOT_TOKEN="", DISCORD_CHANNEL_ID="123",
                    JOBKIT_FILTERS=str(ROOT / "filters" / "example.json"))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    notify = next(check for check in payload["checks"] if check["name"] == "notify")
    assert notify["state"] == "MISS" and "DISCORD_BOT_TOKEN" in notify["detail"]




def test_unknown_location_reports_a_pointer():
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        doc = _json.loads((ROOT / "filters" / "example.json").read_text())
        doc["filters"][0]["location"] = "US_WEST"
        bad = Path(tmp) / "bad.json"
        bad.write_text(_json.dumps(doc))
        result = doctor(JOBKIT_FILTERS=str(bad))
    payload = json.loads(result.stdout)
    filters = next(check for check in payload["checks"] if check["name"] == "filters")
    assert result.returncode == 1 and filters["state"] == "MISS"
    assert "/filters/0/location" in filters["detail"], filters


def test_optional_rows_do_not_decide_core_readiness():
    result = doctor()
    payload = json.loads(result.stdout)
    assert payload["CORE_READY"] is True
    browser = next((c for c in payload["checks"] if c["name"] == "browser"), None)
    if browser and browser["state"] == "WARN":
        assert payload["BROWSER_READY"] is False, "a browser WARN must not read as ready"

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"DOCTOR:MET {len(tests)} tests")
