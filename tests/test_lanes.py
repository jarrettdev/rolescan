"""values/lanes.py (adrs/0015): every active lane's queries parse, the
evaluator's word matching and operators, lane_for, what a posting states
about pay and years, and that hc_scraper builds its configs here."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "values"))
import lanes as L  # noqa: E402


def test_every_active_lane_parses():
    doc = json.loads(L.filters_path().read_text())
    lanes = L.load()
    assert len(lanes) == len(doc["filters"]) >= 1
    for lane in lanes:
        assert lane.title_query is not None, lane.name
        assert lane.yoe_max >= 3 and lane.pay_min == int(doc["base"]["minCompensationLowEnd"]), lane


def test_words_not_substrings():
    assert not L.matches('"IT"', "Security Engineer")
    assert L.matches('"IT"', "IT Support Analyst")
    assert L.matches('NOT "IT"', "Security Engineer")
    assert not L.matches('"Sr"', "SRE Platform")
    assert L.matches('"Security+"', "CompTIA Security+ required")
    assert L.matches('"C++"', "Python or C++")


def test_operators_and_precedence():
    q = 'NOT "Senior" AND NOT "Staff" AND ("Data Engineer" OR "Analytics Engineer")'
    assert L.matches(q, "Analytics Engineer II")
    assert not L.matches(q, "Senior Data Engineer")
    assert not L.matches(q, "Data Scientist")
    assert L.matches('"Security+" AND (Python OR AWS)', "Security+ and AWS")
    assert not L.matches('"Security+" AND (Python OR AWS)', "Security+ and Go")
    assert L.matches('Python AWS', "aws with python")  # adjacent terms mean AND
    assert L.matches("", "anything") and L.matches(None, "anything")
    for bad in ('("a" OR "b"', '"a" AND', 'OR "b"'):
        try:
            L.parse(bad)
            raise AssertionError(f"parsed {bad!r}")
        except ValueError:
            pass


def test_lane_for_first_match():
    lanes = L.load()
    assert L.lane_for("Data Engineer", "We use Python and Spark for data", lanes).name == "Data Engineer"
    assert L.lane_for("Registered Nurse", "patient care", lanes) is None
    assert L.lane_for("Store Manager", "", lanes) is None


def test_not_only_lane_labels_as_fallback():
    import json, tempfile
    doc = json.loads(L.filters_path().read_text())
    doc["filters"] = [
        {"name": "Any technical", "location": "US", "overrides": {"jobTitleQuery": 'NOT "Manager"',
                                                                  "technologyKeywordsQuery": "Python",
                                                                  "searchQuery": ""}},
        {"name": "Data Engineer", "location": "US", "overrides": {"jobTitleQuery": '"Data Engineer"',
                                                                  "technologyKeywordsQuery": "Python",
                                                                  "searchQuery": ""}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(doc, handle)
        path = handle.name
    lanes = L.load(path)
    assert L.lane_for("Data Engineer", "Python", lanes).name == "Data Engineer", "role lanes come first"
    assert L.lane_for("Analyst", "Python and data", lanes).name == "Any technical", "NOT-only lanes still label"


def test_stated_pay():
    assert L.stated_pay("The base pay range is $120,000 - $150,000 per year") == (120000, 150000)
    assert L.stated_pay("$95K to $110k") == (95000, 110000)
    assert L.stated_pay("$45/hour") is None and L.stated_pay("") is None


def test_required_years():
    assert L.required_years("3+ years of experience with Python") == 3
    assert L.required_years("5-7 years of professional software experience; 2 years experience with AWS") == 5
    assert L.required_years("founded 20 years ago") is None
    assert L.required_years("2 to 4 years of relevant work experience") == 2
    assert L.required_years("Experience with SQL") is None


def test_hc_scraper_builds_configs_here():
    import importlib.util
    src = (ROOT / "hc_scraper.py").read_text()
    assert "return effective_configs(doc)" in src and "**flt[\"overrides\"]" not in src
    doc = json.loads(L.filters_path().read_text())
    c = L.effective_configs(doc)[0]["config"]
    assert c["locations"] == doc["locations"][doc["filters"][0].get("location", "US")]
    assert c["jobTitleQuery"] == doc["filters"][0]["overrides"]["jobTitleQuery"]
    assert c["minCompensationLowEnd"] == doc["base"]["minCompensationLowEnd"]
    del importlib


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"LANES:MET {len(tests)} tests")
