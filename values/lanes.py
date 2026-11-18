"""Lanes: the owner's saved searches in filters/active.json, read as data
(adrs/0009, 0015). Pure: no I/O beyond reading the filters file.

This is the one place a lane's effective config (base, location preset,
overrides) is computed, and the one evaluator of its jobTitleQuery and
technologyKeywordsQuery. hc_scraper sends the same config to hiring.cafe;
the ATS poller and the generation screen apply it locally.

Query syntax, as the filters use it: quoted terms or bare words, AND, OR,
NOT, parentheses; adjacent terms mean AND. Terms match whole words, any case:
hiring.cafe must match words, because the Software Engineer lane says
NOT "IT" and still returns security jobs.
"""

import json
import re
from collections import namedtuple
from pathlib import Path

FILTERS_FILE = Path(__file__).resolve().parents[1] / "filters" / "active.json"


def filters_path():
    """JOBKIT_FILTERS, else filters/active.json, else the shipped example."""
    import os
    explicit = os.environ.get("JOBKIT_FILTERS")
    if explicit:
        return Path(explicit)
    return FILTERS_FILE if FILTERS_FILE.exists() else FILTERS_FILE.with_name("example.json")


def blocked_companies(doc):
    """The companies a user never wants to see, from the filters document."""
    return frozenset(str(c).strip().lower() for c in doc.get("blocked_companies") or [] if str(c).strip())

Lane = namedtuple("Lane", "name title_query tech_query search_query yoe_max pay_min need_pay config")

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"([^"]*)"|([^\s()"]+))')


def effective_configs(doc):
    """[{"name", "config"}] with each config built as {**base, locations, **overrides}."""
    out = []
    for flt in doc["filters"]:
        config = {**doc["base"], "locations": doc["locations"][flt.get("location", "US")], **flt["overrides"]}
        out.append({"name": flt["name"], "config": config})
    return out


def _tokens(query):
    pos, out = 0, []
    while pos < len(query):
        m = _TOKEN.match(query, pos)
        if not m or m.end() == pos:
            if query[pos:].strip():
                raise ValueError(f"cannot parse query at {query[pos:]!r}")
            break
        pos = m.end()
        if m.group(1):
            out.append("(")
        elif m.group(2):
            out.append(")")
        elif m.group(3) is not None:
            out.append(("term", m.group(3)))
        else:
            w = m.group(4)
            out.append(w.upper() if w.upper() in ("AND", "OR", "NOT") else ("term", w))
    return out


def parse(query):
    """A query string as a tree: ("or", [..]), ("and", [..]), ("not", x), ("term", s).
    An empty query is None (matches everything). Raises ValueError on bad syntax."""
    toks = _tokens(query or "")
    if not toks:
        return None
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def take():
        nonlocal i
        if i >= len(toks):
            return None
        i += 1
        return toks[i - 1]

    def p_or():
        items = [p_and()]
        while peek() == "OR":
            take()
            items.append(p_and())
        return items[0] if len(items) == 1 else ("or", items)

    def p_and():
        items = [p_not()]
        while peek() not in (None, ")", "OR"):
            if peek() == "AND":
                take()
            items.append(p_not())
        return items[0] if len(items) == 1 else ("and", items)

    def p_not():
        if peek() == "NOT":
            take()
            return ("not", p_not())
        return p_atom()

    def p_atom():
        t = take() if peek() is not None else None
        if t == "(":
            node = p_or()
            if take() != ")":
                raise ValueError(f"unbalanced parentheses in {query!r}")
            return node
        if isinstance(t, tuple):
            return t
        raise ValueError(f"unexpected {t!r} in {query!r}")

    node = p_or()
    if i != len(toks):
        raise ValueError(f"trailing {toks[i]!r} in {query!r}")
    return node


def _has(term, text):
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I) is not None


def _eval(node, text):
    kind = node[0]
    if kind == "term":
        return _has(node[1], text)
    if kind == "not":
        return not _eval(node[1], text)
    if kind == "and":
        return all(_eval(n, text) for n in node[1])
    return any(_eval(n, text) for n in node[1])


def positive(node):
    """True when a query can only match text that contains one of its terms:
    a title query of NOTs alone matches almost any title, so it says nothing
    without hiring.cafe's relevance search behind it."""
    if node is None:
        return False
    kind = node[0]
    if kind == "term":
        return True
    if kind == "not":
        return False
    if kind == "and":
        return any(positive(n) for n in node[1])
    return all(positive(n) for n in node[1])


def matches(query, text):
    """True when text satisfies the query; an empty query matches anything."""
    node = parse(query) if isinstance(query, str) else query
    return True if node is None else _eval(node, text or "")


def load(path=None):
    """The active lanes, each with its parsed queries and fit fields."""
    path = Path(path) if path else filters_path()
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    lanes = []
    for f in effective_configs(doc):
        c = f["config"]
        yoe = c.get("roleYoeRange") or [0, 99]
        lanes.append(Lane(f["name"], parse(c.get("jobTitleQuery", "")), parse(c.get("technologyKeywordsQuery", "")),
                          parse(c.get("searchQuery", "")),
                          int(yoe[1]), int(c.get("minCompensationLowEnd") or 0),
                          bool(c.get("restrictJobsToTransparentSalaries")), c))
    return lanes


def lane_for(title, text, lanes):
    """The first lane whose title query matches the title and whose keyword
    and search queries match the title or the description, or None. Lanes
    whose title query names a role are tried before NOT-only lanes. The
    search query is hiring.cafe's relevance search; locally every word of it
    (honouring OR) must appear."""
    body = f"{title or ''}\n{text or ''}"
    # lanes whose title query names a role first: a lane of NOT clauses only
    # matches nearly anything and would swallow the label (adrs/0016)
    for lane in sorted(lanes, key=lambda ln: not positive(ln.title_query)):
        if matches(lane.title_query, title or "") and matches(lane.tech_query, body) and matches(lane.search_query, body):
            return lane
    return None


# --- what a posting states about itself ---------------------------------------

_PAY = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s?[kK])\b")
_YEARS = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:(?:-|to|–)\s*\d{1,2}\s*\+?\s*)?years?(?:\s+of)?(?:\s+[\w/+#.-]+){0,4}?\s+experience", re.I)


def stated_pay(text):
    """(low, high) yearly pay figures stated in the text, or None. Reads
    "$120,000", "$120k" and "$120.5K"; ignores hourly-looking small amounts."""
    vals = []
    for m in _PAY.finditer(text or ""):
        s = m.group(1).replace(",", "").replace(" ", "").lower()
        v = float(s[:-1]) * 1000 if s.endswith("k") else float(s)
        if v >= 20000:
            vals.append(int(v))
    return (min(vals), max(vals)) if vals else None


def required_years(text):
    """The largest "N years ... experience" the text asks for, or None. A
    posting's bar is its biggest stated requirement, so the largest wins."""
    found = [int(m.group(1)) for m in _YEARS.finditer(text or "") if int(m.group(1)) <= 25]
    return max(found) if found else None
