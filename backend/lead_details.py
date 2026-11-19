"""
Reading lead details from a Slack post or reply (2026-11-19, per Shruti).

  "when slack creates leads, it doesn't update information in the fields, so i
   add the parent name, child's age, event date, birthday date - these should
   get updated ... any field i input on slack for a lead - like locality, venue
   type, no. of kids"

The team types leads one detail per line, in any order, e.g.

    9769939153
    3 year old
    12 Dec
    Home
    Jogeshwari
    Theme bunny rabbit25 kids
    Decor, activities
    Instagram DM

parse_block() reads such a post into lead fields without needing the Claude
API: phone, parent name, child's name / age / gender, birthday, event date
(+ time), # kids, venue / locality, venue type, theme, email, sales lead,
source, services and anything else (kept as notes). parse_updates() reads a
thread reply such as "Tanvi Naik parent name", "Parent name Supriya" or
"event date is 26 or 27th December" into the fields to change on that lead.
Used by routers/slack_leads.py.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from event_naming import _AREA_RE


def known_area(text: str) -> bool:
    """True when the text names a Mumbai / Thane / Navi Mumbai area we know."""
    t = " " + re.sub(r"\s+", " ", str(text or "").lower()) + " "
    return any(rx.search(t) for rx, _ in _AREA_RE)

INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁩﻿]")


def clean(text: str) -> str:
    """Copy-pasted WhatsApp numbers carry invisible direction marks and
    non-breaking spaces; take them out."""
    return INVISIBLE.sub("", (text or "").replace(" ", " "))


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_D = r"(\d{1,2})(?:st|nd|rd|th)?"
_SEP = r"\s*(?:-|–|to|or|/|&|and)\s*"
DATE_PATTERNS = [
    # "26-27th Nov", "26 or 27th December", "5-6th Dec"
    (re.compile(rf"\b{_D}{_SEP}{_D}\s*(?:of\s+)?{_MON}(?:\s*,?\s*(\d{{4}}))?", re.I), lambda m: (m.group(1), m.group(3), m.group(4))),
    # "12 Dec", "2nd Jan", "12th of December 2026"
    (re.compile(rf"\b{_D}\s*(?:of\s+)?{_MON}(?:\s*,?\s*(\d{{4}}))?", re.I), lambda m: (m.group(1), m.group(2), m.group(3))),
    # "Dec 13", "December 13th"
    (re.compile(rf"\b{_MON}\s*{_D}\b(?:\s*,?\s*(\d{{4}}))?", re.I), lambda m: (m.group(2), m.group(1), m.group(3))),
    # "13/12", "13-12-2026", "13.12.26"
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b"), lambda m: (m.group(1), m.group(2), m.group(3))),
]


def find_date(text: str, today: date, future: bool = True) -> Tuple[Optional[date], str, str]:
    """(date, the date as written, text without it). A date with no year is
    the next one on or after today (future=True)."""
    for rx, get in DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        dd, mm, yy = get(m)
        mo = MONTHS.get(mm[:3].lower()) if not str(mm).isdigit() else int(mm)
        try:
            day = int(dd)
            if yy:
                y = int(yy); y = y + 2000 if y < 100 else y
                d = date(y, mo, day)
            else:
                d = date(today.year, mo, day)
                if future and d < today:
                    d = date(today.year + 1, mo, day)
        except (TypeError, ValueError):
            continue
        rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,;-–")
        return d, m.group(0).strip(), rest
    return None, "", text


_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b"
                   r"|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)


def _hm(h: str, m: Optional[str], ap: Optional[str]) -> Optional[str]:
    h = int(h); mi = int(m or 0)
    if ap:
        ap = ap.lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def find_time(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """'4-7pm' -> ('16:00', '19:00'); '11am' -> ('11:00', None)."""
    m = _TIME.search(text)
    if not m:
        return None, None, text
    rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,;-–")
    if m.group(4):
        ap2 = m.group(6)
        ap1 = m.group(3) or ap2
        start, end = _hm(m.group(1), m.group(2), ap1), _hm(m.group(4), m.group(5), ap2)
        # "11-2pm": 11 is am
        if start and end and start > end and not m.group(3):
            start = _hm(m.group(1), m.group(2), "am")
        return start, end, rest
    return _hm(m.group(7), m.group(8), m.group(9)), None, rest


PHONE = re.compile(r"(\+?\d[\d\s\-()]{8,16}\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
KIDS = re.compile(r"#?\s*(?:(\d{1,3})\s*(?:-|–|to)\s*)?(\d{1,3})\s*\+?\s*(?:kids?|children|child(?:ren)?|guests?|pax|people)\b"
                  r"|\b(?:kids?|children|guests?|no\.?\s*of\s*kids?|kids?\s*count)\s*[:\-=]?\s*(?:(\d{1,3})\s*(?:-|–|to)\s*)?(\d{1,3})\b", re.I)
AGE = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*(?:yrs?|years?|yo|year)\s*(?:old)?\b|\bturning\s*(\d{1,2})\b|\bage\s*[:\-=]?\s*(\d{1,2})\b"
                 r"|\b(\d{1,2})(?:st|nd|rd|th)\s*(?:birthday|bday|b'day)\b", re.I)
GENDER_AGE = re.compile(r"^\s*(girl|boy|f|m|female|male)\s*[-/,]?\s*(\d{1,2})\s*$|^\s*(\d{1,2})\s*[-/,]?\s*(girl|boy|f|m|female|male)\s*$", re.I)
GENDER = re.compile(r"\b(girl|boy|daughter|son|female|male)\b", re.I)


def _gender(w: str) -> Optional[str]:
    w = (w or "").lower()
    if w in ("girl", "f", "female", "daughter"):
        return "Female"
    if w in ("boy", "m", "male", "son"):
        return "Male"
    return None


VENUE_TYPES = [   # (pattern, value) — values as in sales_leads.VENUE_TYPES
    (r"\bsociety\s*(?:banquet|hall)|\bbanquet\s*hall\b|\bsociety\s*club\s*house\b", "Society Banquet Hall"),
    (r"\bbanquet\b", "Society Banquet"),
    (r"\bturf\b", "Turf"),
    (r"\bclub\s*-?\s*house\b|\bclubhouse\b|\bclub\b|\bresort\b|\bgymkhana\b", "Club"),
    (r"\brestaurant\b|\bcaf[eé]\b|\bhotel\b", "Restaurant"),
    (r"\bplay\s*area\b|\bplay\s*zone\b|\bsoft\s*play\b", "Play Area"),
    (r"\bat\s+home\b|\bhouse\s*party\b|\bhome\b|\bhouse\b|\bresidence\b|\bterrace\b", "Home"),
    (r"\bnot\s*decided\b|\bvenue\s*tbd\b|\btbd\b", "Not Decided"),
]
VENUE_TYPE_WORDS = re.compile(r"\b(?:party|venue|type|at|in|the|a|our|my)\b", re.I)

SERVICE_WORDS = re.compile(
    r"\bdecor|\bactivit|face\s*paint|\btattoo|\bserver|\bhost\b|\bemcee|\banchor|\bdj\b|\bmusic|\bmagic|\bphoto|\bvideo|"
    r"\bcake|return\s*gift|\bgifts?\b|\bcater|\bfood|\bsnack|\bgames?\b|\bbubble|\bpuppet|\bpinata|\bballoon|\binflatable|"
    r"\bbouncy|\btrampoline|\bmascot|\bslime|\bworkshop|\bstation|\bmatch\b|\bshow\b|\bpopcorn|\bcandy|\btreasure\s*hunt|"
    r"\binvite|\bmehendi|\bnail\s*art|\bhair\s*(?:style|glitter)|\bglitter|\bsports?\b|\bfootball|\bcricket\s*match", re.I)

LABELS = [   # (field, label pattern) for "Label: value" / "Label value"
    ("name", r"parent(?:'?s)?\s*name|parent|mother|mom|mum|father|dad|client\s*name|customer\s*name|contact\s*name|name"),
    ("child_names", r"child(?:'?s)?\s*name|kid(?:'?s)?\s*name|baby(?:'?s)?\s*name|child|kid|baby|birthday\s*(?:boy|girl)"),
    ("child_dobs", r"birth\s*date|birthday\s*date|date\s*of\s*birth|dob|b'?day\s*date|birthday|bday|b'day"),
    ("event_date", r"event\s*date|party\s*date|date\s*of\s*(?:the\s*)?(?:event|party)|event\s*on|party\s*on|date"),
    ("event_time", r"event\s*time|party\s*time|time|timing|timings"),
    ("child_ages", r"child(?:'?s)?\s*age|age"),
    ("child_genders", r"gender|sex"),
    ("kids_count", r"no\.?\s*of\s*kids|number\s*of\s*kids|kids?\s*count|#\s*kids|kids|children|guests|pax|head\s*count"),
    ("venue_type", r"venue\s*type|type\s*of\s*venue|venue\s*kind"),
    ("venue", r"venue\s*location|venue\s*address|venue\s*name|venue|locality|location|area|address|place"),
    ("theme", r"theme"),
    ("email", r"e-?mail(?:\s*id)?"),
    ("event_sales_lead", r"sales\s*lead|sales\s*person|assigned\s*to|owner|handled\s*by"),
    ("services", r"services?|requirements?|needs|wants|looking\s*for"),
    ("source", r"lead\s*source|source|reference|referred\s*by|referral"),
    ("budget", r"budget"),
]
_LABEL_RE = [(f, re.compile(rf"^\s*(?:{p})\s*(?:is|=|:|-|–)?\s*(.+?)\s*$", re.I)) for f, p in LABELS]
_LABEL_AFTER_RE = [(f, re.compile(rf"^\s*(.+?)\s*(?:is\s+)?(?:the\s+)?(?:{p})\s*$", re.I)) for f, p in LABELS
                   if f in ("name", "child_names", "theme", "venue", "event_date", "child_dobs", "venue_type")]
BARE_NAME = re.compile(r"^[A-Za-z][A-Za-z.'’]*(?:\s+[A-Za-z][A-Za-z.'’]*){0,3}$")
STOP_NAME = re.compile(r"\b(?:new|lead|leads|party|birthday|bday|kids?|theme|decor|ad|ads|insta|instagram|google|website|"
                       r"whatsapp|referral|referred|reference|enquiry|inquiry|budget|done|ok|call|later|sales|mumbai)\b", re.I)


def _tidy(v: str, n: int = 255) -> Optional[str]:
    v = re.sub(r"\s+", " ", (v or "")).strip(" ,;:-–.")
    return v[:n] or None


def _name(v: str) -> Optional[str]:
    v = _tidy(v, 255)
    if not v:
        return None
    return v.title() if (v.isupper() or v.islower()) else v


def _venue_type(text: str) -> Optional[str]:
    for p, val in VENUE_TYPES:
        if re.search(p, text, re.I):
            return val
    return None


def _kids(m) -> int:
    hi = m.group(2) or m.group(4)
    return int(hi)


class Lead:
    def __init__(self):
        self.f: Dict[str, Any] = {}
        self.notes: List[str] = []
        self.services: List[str] = []
        self.date_text: Optional[str] = None
        self.bday: Optional[date] = None

    def set(self, k, v, overwrite=False):
        if v in (None, ""):
            return
        if overwrite or self.f.get(k) in (None, ""):
            self.f[k] = v


def _apply_value(L: Lead, field: str, value: str, today: date, source_fn, overwrite: bool) -> bool:
    """A labelled value -> the lead. False if it couldn't be used."""
    v = value.strip()
    if not v:
        return False
    if field == "name":
        L.set("name", _name(v), overwrite); return True
    if field == "child_names":
        rest = v
        a = AGE.search(rest)
        if a:
            L.set("child_ages", str(int(next(x for x in a.groups() if x))), overwrite)
            rest = rest[:a.start()] + " " + rest[a.end():]
        g = GENDER.search(rest)
        if g:
            L.set("child_genders", _gender(g.group(1)), overwrite)
            rest = rest[:g.start()] + " " + rest[g.end():]
        nm = re.split(r"[,;(]", rest)[0]
        nm = re.sub(r"\b(?:old|year|years|yrs)\b", "", nm, flags=re.I)
        L.set("child_names", _name(nm), overwrite); return True
    if field in ("event_date", "child_dobs"):
        d, written, _ = find_date(v, today, future=True)
        if not d:
            return False
        if field == "event_date":
            L.set("event_date", d, overwrite)
            if re.search(_SEP.strip() + r"|\bor\b", written, re.I) and re.search(r"\d.*\d", written):
                L.date_text = written
        else:
            L.bday = d
        return True
    if field == "event_time":
        s, e, _ = find_time(v)
        if not s:
            return False
        L.set("event_time", s, overwrite); L.set("event_end_time", e, overwrite); return True
    if field == "child_ages":
        m = re.search(r"\d{1,2}", v)
        if not m:
            return False
        L.set("child_ages", str(int(m.group(0))), overwrite); return True
    if field == "child_genders":
        g = GENDER.search(v) or re.fullmatch(r"\s*([fm])\s*", v, re.I)
        if not g:
            return False
        L.set("child_genders", _gender(g.group(1)), overwrite); return True
    if field == "kids_count":
        m = re.findall(r"\d{1,3}", v)
        if not m:
            return False
        L.set("kids_count", int(m[-1]), overwrite); return True
    if field == "venue_type":
        vt = _venue_type(v) or next((x for x in ("Home", "Society Banquet Hall", "Society Banquet", "Club", "Restaurant",
                                               "Turf", "Play Area", "Other", "Not Decided") if x.lower() == v.lower()), None)
        if not vt:
            return False
        L.set("venue_type", vt, overwrite); return True
    if field == "venue":
        L.set("venue", _tidy(v), overwrite)
        vt = _venue_type(v)
        if vt:
            L.set("venue_type", vt)
        return True
    if field == "theme":
        L.set("theme", _tidy(re.sub(r"\btheme(?:d)?\b", "", v, flags=re.I)), overwrite); return True
    if field == "email":
        m = EMAIL.search(v)
        if not m:
            return False
        L.set("email", m.group(0), overwrite); return True
    if field == "event_sales_lead":
        L.set("event_sales_lead", _name(v), overwrite); return True
    if field == "services":
        L.services.append(_tidy(v, 300)); return True
    if field == "source":
        src, ref = source_fn(value if re.search(r"refer|ref\b|reference", v, re.I) else v)
        if not src and re.search(r"^\s*(?:referred\s*by|referral)", value, re.I):
            src = "referral"
        if src:
            L.set("source", src, overwrite); L.set("referred_by", ref, overwrite); return True
        L.notes.append(f"Source given: {v}"); return True
    if field == "budget":
        L.notes.append(f"Budget: {v}"); return True
    return False


def read_line(L: Lead, line: str, today: date, source_fn, reply: bool = False) -> bool:
    """One line of a post (or reply) -> fields on L. Returns True if something
    was taken from it. In a reply (reply=True) a bare word isn't taken as the
    parent's name; replies change values (overwrite) instead of filling blanks."""
    t = clean(line).strip().strip("*_").strip()
    t = re.sub(r"^\s*(?:[-•●▪◦]|\d{1,2}[.)])\s+", "", t)
    if not t:
        return False
    ow = reply
    # email anywhere
    em = EMAIL.search(t)
    if em:
        L.set("email", em.group(0), ow)
        t = (t[:em.start()] + t[em.end():]).strip(" ,;")
        if not t:
            return True
    # "Zidan's 5th Birthday"
    m = re.match(r"^([A-Za-z]+)['’]?s\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:birthday|bday|b'day)\b(.*)$", t, re.I)
    if m:
        L.set("child_names", _name(m.group(1)), ow); L.set("child_ages", str(int(m.group(2))), ow)
        rest = m.group(3).strip(" ,-")
        if rest:
            read_line(L, rest, today, source_fn, reply)
        return True
    # "Girl 10" / "M4" / "10 F"
    m = GENDER_AGE.match(t)
    if m:
        L.set("child_genders", _gender(m.group(1) or m.group(4)), ow)
        L.set("child_ages", str(int(m.group(2) or m.group(3))), ow)
        return True
    # "Parent location Malad" is where they live, not the venue or a name.
    m = re.match(r"^\s*parent(?:'?s)?\s*(?:location|locality|area|address|lives\s*in|stays\s*in)\s*[:\-=]?\s*(.+)$", t, re.I)
    if m:
        L.notes.append(f"Parent location: {_tidy(m.group(1))}"); return True
    # "Referred by Kiran" / "Reference Google" / "Lead source: insta ad"
    if re.match(r"^\s*(?:referred|referral|reference|ref|recommended|lead\s*source|source)\b", t, re.I) and len(t.split()) <= 8:
        src, ref = source_fn(t)
        if src:
            L.set("source", src, ow); L.set("referred_by", ref, ow); return True
    # "# kids" anywhere on a short line ("Theme bunny rabbit25 kids")
    if len(t.split()) <= 8:
        km = KIDS.search(t)
        if km and not re.match(r"^\s*(?:no\.?\s*of|number\s*of)?\s*kids?\s*(?:count)?\s*[:\-=]", t, re.I):
            L.set("kids_count", _kids(km), ow)
            t = (t[:km.start()] + " " + t[km.end():]).strip(" ,;-")
            if not t:
                return True
    # "Label: value" / "Label value"
    for field, rx in _LABEL_RE:
        lm = rx.match(t)
        if not lm:
            continue
        if field == "name" and re.match(r"^\s*name\b", t, re.I) is None and not re.match(r"^\s*(?:parent|mother|mom|mum|father|dad|client|customer|contact)", t, re.I):
            continue
        # "child - mark, 7 year old boy"; "kids 25" handled; skip "kids" if no number
        if _apply_value(L, field, lm.group(1), today, source_fn, ow):
            return True
    # "Tanvi Naik parent name", "Football theme", "26 Dec event date"
    for field, rx in _LABEL_AFTER_RE:
        lm = rx.match(t)
        if lm and len(lm.group(1).split()) <= 6 and _apply_value(L, field, lm.group(1), today, source_fn, ow):
            return True
    took = False
    short = len(t.split()) <= 8
    if not short:
        L.notes.append(_tidy(t, 500)); return True
    # Source words ("Instagram DM", "Reference Google", "Referred by Kiran")
    src, ref = source_fn(t)
    if src and len(t.split()) <= 5:
        L.set("source", src, ow); L.set("referred_by", ref, ow)
        return True
    # "Child - mark, 7 year old boy" / "3 year old" / "10 years old girl"
    am = AGE.search(t)
    if am:
        L.set("child_ages", str(int(next(x for x in am.groups() if x))), ow)
        rest = (t[:am.start()] + " " + t[am.end():])
        g = GENDER.search(rest)
        if g:
            L.set("child_genders", _gender(g.group(1)), ow)
            rest = rest[:g.start()] + " " + rest[g.end():]
        rest = re.sub(r"\b(?:old|kid|child)\b", "", rest, flags=re.I).strip(" ,;-–")
        if rest and re.search(r"\b(?:birthday|bday)\b", rest, re.I):
            rest = re.sub(r"\b(?:birthday|bday)\b", "", rest, flags=re.I).strip(" ,;-–")
        rest = re.sub(r"^\s*(?:child|kid|baby)\s*[:\-–]?\s*|\b(?:is|turning|will\s*be)\b", " ", rest, flags=re.I).strip(" ,;-–")
        if rest and BARE_NAME.match(rest) and not STOP_NAME.search(rest) and not known_area(rest) and len(rest.split()) <= 2:
            L.set("child_names", _name(rest), ow)   # "son Aarav turning 6"
        elif rest:
            read_line(L, rest, today, source_fn, reply)
        return True
    g = re.fullmatch(r"\s*(girl|boy|female|male|daughter|son)\s*", t, re.I)
    if g:
        L.set("child_genders", _gender(g.group(1)), ow); return True
    # time ("4-7pm")
    s, e, rest_t = find_time(t)
    if s:
        L.set("event_time", s, ow); L.set("event_end_time", e, ow)
        t = rest_t; took = True
        if not t:
            return True
    # birthday date ("birthday 12 Dec", "bday on 5th")
    if re.search(r"\b(?:birthday|bday|b'day|dob|born)\b", t, re.I):
        d, written, rest = find_date(t, today)
        if d:
            L.bday = d
            return True
    # event date ("12 Dec", "2nd Jan, Godrej platinum clubhouse", "26-27th Nov")
    d, written, rest = find_date(t, today)
    if d:
        L.set("event_date", d, ow)
        if re.search(r"\d\s*(?:-|–|to|or|/|&|and)\s*\d", written):
            L.date_text = written
        t = re.sub(r"^\s*(?:on|date|event|party)\b", "", rest, flags=re.I).strip(" ,;-–")
        took = True
        if not t:
            return True
    # venue type ("Home", "House party", "Turf party", "Godrej platinum clubhouse")
    vt = _venue_type(t)
    if vt:
        L.set("venue_type", vt, ow)
        leftover = re.sub("|".join(p for p, _ in VENUE_TYPES), " ", t, flags=re.I)
        leftover = VENUE_TYPE_WORDS.sub(" ", leftover).strip(" ,;-–")
        if leftover and len(leftover) > 2:
            if SERVICE_WORDS.search(leftover):
                L.services.append(_tidy(leftover, 300))
            else:
                L.set("venue", _tidy(t), ow)   # a named place, e.g. "Godrej platinum clubhouse"
        return True
    # services ("Decor, activities", "Face painting tattoo", "Server")
    if SERVICE_WORDS.search(t) and len(t.split()) <= 6:
        L.services.append(_tidy(t, 300)); return True
    # "xyz theme" / "theme xyz" (unlabelled form already handled above)
    # a Mumbai area -> venue / locality ("Jogeshwari", "Worli/parel/bandra")
    if known_area(t) and len(t) <= 60:
        L.set("venue", _tidy(t), ow); return True
    # A bare name line -> the parent's name (first one only, posts only)
    if not reply and BARE_NAME.match(t) and not STOP_NAME.search(t) and not L.f.get("name"):
        L.set("name", _name(t)); return True
    L.notes.append(_tidy(t, 500))
    return took or True


def _finish(L: Lead, reply: bool = False) -> Dict[str, Any]:
    f = dict(L.f)
    if reply and L.bday:
        # The lead's age is known only when applying (slack_leads.apply_updates).
        f["birthday"] = L.bday
        L.bday = None
    # Birthday given: it's the child's date of birth when the age is known
    # (the age they are turning on it), and the event date if there's none.
    if L.bday:
        if f.get("child_ages") and str(f["child_ages"]).isdigit():
            try:
                f["child_dobs"] = date(L.bday.year - int(f["child_ages"]), L.bday.month, L.bday.day).isoformat()
            except ValueError:
                pass
        if not f.get("event_date"):
            f["event_date"] = L.bday
            L.notes.append(f"Birthday: {L.bday.strftime('%d %b')} (event date set to the birthday)")
        elif not f.get("child_dobs"):
            L.notes.append(f"Birthday: {L.bday.strftime('%d %b')}")
    notes = []
    if L.services:
        notes.append("Services: " + ", ".join(dict.fromkeys(s for s in L.services if s)))
    if L.date_text:
        notes.append(f"Date as written: {L.date_text}")
    notes += [n for n in L.notes if n]
    return {"fields": f, "note": " · ".join(notes) or None}


def parse_block(text: str, today: date, source_fn) -> List[Dict[str, Any]]:
    """A post with one detail per line -> [{phone, name, fields, playbook,
    source, referred_by, note}], one per phone number."""
    lines = [l for l in clean(text).splitlines()]
    leads: List[Tuple[Optional[str], Lead]] = []
    before: List[str] = []
    cur: Optional[Lead] = None
    from routers.aisensy_webhook import normalise_phone
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        pm = PHONE.search(line)
        digits = re.sub(r"\D", "", pm.group(1)) if pm else ""
        if pm and 10 <= len(digits) <= 13 and not EMAIL.search(line):
            phone = normalise_phone(pm.group(1))
            cur = Lead()
            leads.append((phone, cur))
            rest = (line[:pm.start()] + " " + line[pm.end():]).strip(" ,;:-–()[]")
            if rest:
                read_line(cur, rest, today, source_fn)
            continue
        if cur is None:
            before.append(line)
        else:
            read_line(cur, line, today, source_fn)
    if not leads:
        return []
    for line in before:   # details above the (first) number belong to it
        read_line(leads[0][1], line, today, source_fn)
    out = []
    for phone, L in leads:
        r = _finish(L)
        f = r["fields"]
        out.append({
            "phone": phone, "name": f.pop("name", None), "handle": None,
            "source": f.pop("source", None), "referred_by": f.pop("referred_by", None),
            "playbook": {"venue_type": f.pop("venue_type", None), "event_end_time": f.pop("event_end_time", None)},
            "fields": {k: v for k, v in f.items() if v not in (None, "")},
            "note": r["note"], "generated_at": None,
        })
    return out


def parse_updates(text: str, today: date, source_fn) -> Tuple[Dict[str, Any], List[str]]:
    """A thread reply -> (changes, lines not understood as details). Changes
    use the lead column names plus venue_type / event_end_time (sales sheet),
    name (parent), source / referred_by, note."""
    changes: Dict[str, Any] = {}
    other: List[str] = []
    for line in clean(text).splitlines():
        if not line.strip():
            continue
        L = Lead()
        t = line.strip()
        # A line that only names a lead source is for the source logic.
        src, _ = source_fn(t)
        if src and len(t.split()) <= 5 and not re.search(r"\b(?:name|date|kids?|age|venue|theme|time|locality|location)\b", t, re.I):
            other.append(line); continue
        read_line(L, t, today, source_fn, reply=True)
        r = _finish(L, reply=True)
        f = r["fields"]
        f.pop("source", None); f.pop("referred_by", None)
        if not f:
            other.append(line); continue
        changes.update(f)
        if L.services or L.date_text:
            changes["note"] = " · ".join(x for x in [changes.get("note"), r["note"]] if x)
    return changes, other
