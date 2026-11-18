"""Filters are user data (adrs/0019): the shipped example matches the schema,
every set in filters/ parses, and active.json is never committed."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import jsonschema  # noqa: E402
import hc_scraper  # noqa: E402

SCHEMA = json.loads((ROOT / "filters" / "schema.json").read_text())
EXAMPLE = ROOT / "filters" / "example.json"


def test_example_validates_against_schema():
    doc = json.loads(EXAMPLE.read_text())
    jsonschema.Draft202012Validator(SCHEMA).validate(doc)


def test_example_has_no_personal_locations_or_companies():
    doc = json.loads(EXAMPLE.read_text())
    assert doc["blocked_companies"] == []
    assert all(f["location"] in doc["locations"] for f in doc["filters"])
    assert all("spacex" not in json.dumps(f).lower() for f in doc["filters"])


def test_unknown_field_is_reported_with_a_pointer():
    doc = json.loads(EXAMPLE.read_text())
    doc["typo_field"] = True
    errors = sorted(jsonschema.Draft202012Validator(SCHEMA).iter_errors(doc), key=lambda e: list(e.path))
    assert errors, "schema accepted an unknown top-level field"
    pointer = "/" + "/".join(str(p) for p in errors[0].path) if errors[0].path else "/"
    assert pointer == "/", pointer


def test_every_filter_set_parses_and_has_queries():
    sets = [p for p in sorted((ROOT / "filters").glob("*.json")) if p.name != "schema.json"]
    assert sets, "no filter sets found"
    for path in sets:
        doc = json.loads(path.read_text())
        names = [f["name"] for f in doc["filters"]]
        assert len(names) == len(set(names)), f"{path.name}: duplicate filter names"
        for cfg in hc_scraper.load_filters(path):
            c = cfg["config"]
            assert c.get("jobTitleQuery") or c.get("searchQuery") or c.get("technologyKeywordsQuery"), \
                f"{path.name} {cfg['name']}: no query at all"


def test_active_filters_are_gitignored():
    ignore = (ROOT / ".gitignore").read_text()
    assert "filters/active.json" in ignore


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"FILTERS:MET {len(tests)} tests")
