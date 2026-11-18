"""Goal select-ats-postings (adrs/0015): which postings from the employer
boards the poller hands on, as scrape rows. Pure: no I/O. bin/ats-poll
fetches the boards, passes the lanes (values/lanes.py), the posting keys the
ledger and the registry already hold, today's emitted count, the clock and
select-listings' blocked companies, and writes the rows it gets back.

Two passes, so detail requests are spent only where they can matter:
prefilter() uses what a board list carries (title, location, dates);
select() then needs the description too, for the lane's keyword query, the
pay floor and the years ceiling, and applies the caps.
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "values"))
import lanes as L  # noqa: E402
from posting_key import UnkeyedListing, posting_key  # noqa: E402
from ats import employer_host  # noqa: E402
from tech_terms import tech_stack  # noqa: E402

MAX_PER_RUN = 8
MAX_PER_DAY = 40
MAX_PER_COMPANY = 2  # per run, so one employer's hiring burst does not take every row
FRESH_HOURS = 72


def poller_lanes(lanes):
    """Lanes whose title query names a role. A lane of NOT clauses only
    (Python Data, Python AWS, Security+, Software Engineer) leans on
    hiring.cafe's relevance search, which a local word match cannot
    replace, so those lanes stay with the hiring.cafe scrape."""
    return [ln for ln in lanes if L.positive(ln.title_query)]

_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
           "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
_STATE_NAMES = ("alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho "
                "illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota "
                "mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah "
                "vermont virginia washington wisconsin wyoming").split() + [
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "rhode island",
    "south carolina", "south dakota", "west virginia", "district of columbia"]
_US = re.compile(r"\b(united states|usa|u\.s\.a?\.?|us|" + "|".join(_STATE_NAMES) + r")\b", re.I)
_STATE_ABBR = re.compile(r"(?:,|\b-)\s*(" + "|".join(_STATES) + r")\b")
_NON_US = re.compile(r"\b(canada|toronto|vancouver|montreal|united kingdom|uk|london|england|ireland|dublin|india|"
                     r"bangalore|bengaluru|hyderabad|germany|berlin|munich|france|paris|netherlands|amsterdam|spain|"
                     r"madrid|poland|warsaw|brazil|mexico city|singapore|japan|tokyo|australia|sydney|israel|"
                     r"tel aviv|emea|apac|latam|europe|philippines|argentina|colombia|portugal|lisbon|switzerland|"
                     r"zurich|sweden|stockholm|romania|ukraine|china|hong kong|korea|seoul|taiwan|vietnam)\b", re.I)


def is_us(location):
    """True when the location names the US (a state, 'United States', 'US')
    or says Remote without naming another country."""
    # nlc:rule=R-goal-no-noun-write
    # nlc:rule=R-poll-caps  # nlc:obligation=the ATS poller hands on at most 8 postings per run and 40 per UTC day, only lane-matched, US, fresh postings whose key is not in the ledger or already emitted
    loc = (location or "").strip()
    if not loc:
        return False
    us = bool(_US.search(loc) or _STATE_ABBR.search(loc))
    if us:
        return True
    return "remote" in loc.lower() and not _NON_US.search(loc)


def _when(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _key(posting):
    try:
        return posting_key(posting.get("url"))
    except UnkeyedListing:
        return None


def prefilter(postings, lanes, known_keys, now, blocked=()):
    """Postings worth a detail request: a lane's title query matches, US,
    first published within FRESH_HOURS, not known, not a blocked company.
    Newest first. Malformed postings are skipped."""
    cutoff = now - timedelta(hours=FRESH_HOURS)
    lanes = poller_lanes(lanes)
    out = []
    for p in postings:
        try:
            when = _when(p.get("first_published"))
            key = _key(p)
            if not key or key in known_keys or when is None or when < cutoff or when > now + timedelta(hours=1):
                continue
            if (p.get("company") or "").strip().lower() in blocked or not is_us(p.get("location")):
                continue
            if not any(L.matches(lane.title_query, p.get("title") or "") for lane in lanes):
                continue
            out.append(p)
        except (AttributeError, TypeError):
            continue
    out.sort(key=lambda p: _when(p["first_published"]), reverse=True)
    return out


def fits(posting, lane):
    """The lane's title, keyword and search queries (values/lanes.lane_for
    rules), its pay floor (and stated pay when the lane needs it), and its
    years ceiling."""
    title, text = posting.get("title") or "", posting.get("text") or ""
    if L.lane_for(title, text, [lane]) is None:
        return False
    pay = L.stated_pay(text)
    if pay is None and lane.need_pay:
        return False
    if pay is not None and pay[1] < lane.pay_min:
        return False
    years = L.required_years(text)
    return years is None or years <= lane.yoe_max


def to_row(posting, lane, now):
    """A scrape row (values/scrape_csv.row_to_csv keys) for one posting, plus
    company_homepage, which bin/ats-poll turns into company_linkedin."""
    when = _when(posting.get("first_published")) or now
    hours = max(0, int((now - when).total_seconds() // 3600))
    pay = L.stated_pay(posting.get("text") or "")
    return {
        "title": posting.get("title", ""), "company": posting.get("company", ""),
        "location": posting.get("location", ""), "salary": pay[0] if pay else "Not listed",
        "time_posted": f"{hours}h", "yoe": L.required_years(posting.get("text") or "") or "",
        "description": (posting.get("text") or "")[:500],
        "tech_stack": tech_stack(posting.get("text") or "") or "Not listed",
        "requirements": f"ATS poller: {posting.get('ats')} board {posting.get('tenant')}, lane {lane.name}",
        "company_linkedin": "", "company_homepage": employer_host(posting.get("url")),
        "apply_url": posting.get("url", ""), "job_type": "", "industry": "",
    }


def select_ats_postings(postings, lanes, known_keys, emitted_today, now, blocked=()):
    """Detail-filled postings in, (row, posting, lane name) out: prefilter
    again, the lane fit, then newest first within MAX_PER_RUN and what is
    left of MAX_PER_DAY. Each key appears once."""
    room = max(0, min(MAX_PER_RUN, MAX_PER_DAY - emitted_today))
    usable = poller_lanes(lanes)
    out, seen, per_company = [], set(), {}
    for p in prefilter(postings, lanes, known_keys, now, blocked):
        if len(out) >= room:
            break
        key = _key(p)
        company = (p.get("company") or p.get("tenant") or "").strip().lower()
        same = (company, re.sub(r"\W+", " ", (p.get("title") or "").lower()).strip())
        if key in seen or same in seen or per_company.get(company, 0) >= MAX_PER_COMPANY:
            continue
        lane = next((ln for ln in usable if fits(p, ln)), None)
        if lane is None:
            continue
        seen.update((key, same))
        per_company[company] = per_company.get(company, 0) + 1
        out.append((to_row(p, lane, now), p, lane.name))
    return out
