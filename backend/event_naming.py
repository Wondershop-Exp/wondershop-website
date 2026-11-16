"""
Standard event name (2026-11-16, per Shruti).

  "we are standardising our event naming nomenclature - Name age-gender
   location, example: Ishani F8 Ghatkopar, Mitansh M10 Thane"

event_name(booking) -> "Ishani F8 Ghatkopar"
  Name      the child's first name (first word of child_names)
  F8 / M10  gender initial + age (F = girl, M = boy), straight after the name
  Location  the area of the venue (no East / West: "Ghatkopar") — a known Mumbai / Thane / Navi Mumbai area
            found in the venue text; else the city when it isn't just
            "Mumbai"; else the last part of the venue address.
Several children: "Ishani & Vir F8 M6 Ghatkopar". A part that isn't known
is left out ("Ishani F8" when there's no venue yet).

Used for packing-list titles (routers/packaging.py, routers/slack_packing.py)
and the Event Photos sheet's event name (routers/admin.py).
"""
import re
from typing import Any, List, Optional

# Longer names first so "Andheri East" wins over "Andheri", "Navi Mumbai"
# over "Mumbai" etc. Spelling variants map to the name we use.
_AREAS = [
    "Andheri East", "Andheri West", "Bandra East", "Bandra West", "Borivali East", "Borivali West",
    "Goregaon East", "Goregaon West", "Kandivali East", "Kandivali West", "Malad East", "Malad West",
    "Santacruz East", "Santacruz West", "Vile Parle East", "Vile Parle West", "Mulund East", "Mulund West",
    "Ghatkopar East", "Ghatkopar West", "Kurla West", "Kurla East", "Dahisar East", "Dahisar West",
    "Lower Parel", "Mumbai Central", "Marine Drive", "Marine Lines", "Grant Road", "Charni Road",
    "Navi Mumbai", "Vashi", "Nerul", "Kharghar", "Panvel", "Belapur", "CBD Belapur", "Airoli", "Ghansoli",
    "Kopar Khairane", "Sanpada", "Seawoods", "Ulwe", "Kamothe", "Turbhe", "Juinagar",
    "Andheri", "Bandra", "Borivali", "Goregaon", "Kandivali", "Malad", "Santacruz", "Vile Parle",
    "Mulund", "Ghatkopar", "Kurla", "Dahisar", "Juhu", "Versova", "Lokhandwala", "Oshiwara", "Jogeshwari",
    "Khar", "Powai", "Chandivali", "Vikhroli", "Bhandup", "Kanjurmarg", "Chembur", "Sion", "Wadala",
    "Matunga", "Dadar", "Prabhadevi", "Worli", "Mahim", "Parel", "Byculla", "Tardeo", "Malabar Hill",
    "Breach Candy", "Peddar Road", "Kemps Corner", "Colaba", "Cuffe Parade", "Nariman Point", "Fort",
    "Churchgate", "Girgaon", "Mazgaon", "BKC", "Kalina", "Saki Naka", "Marol", "Chakala", "Mira Road",
    "Bhayandar", "Vasai", "Virar", "Nalasopara", "Thane West", "Thane East", "Ghodbunder Road",
    "Majiwada", "Kolshet", "Hiranandani Estate", "Thane", "Kalyan", "Dombivli", "Ambernath", "Badlapur",
    "Bhiwandi", "Govandi", "Mankhurd", "Deonar", "Trombay", "Antop Hill", "Sewri", "Lalbaug",
    "Kalbadevi", "Mahalaxmi", "Agripada", "Madh Island", "Marve", "Gorai", "Manori", "Aarey",
    "Lonavala", "Alibaug", "Karjat", "Pune",
]
_ALIASES = {
    "bandra kurla complex": "BKC", "vileparle": "Vile Parle", "parle": "Vile Parle",
    "santa cruz": "Santacruz", "kandivli": "Kandivali", "borivli": "Borivali",
    "hiranandani powai": "Powai", "dombivali": "Dombivli",
    "bhayander": "Bhayandar", "nala sopara": "Nalasopara", "koparkhairane": "Kopar Khairane",
    "seawood": "Seawoods", "andheri e": "Andheri East", "andheri w": "Andheri West",
    # Parts of Thane go by "Thane" (as in "Mitansh M10 Thane").
    "majiwada": "Thane", "ghodbunder road": "Thane", "ghodbunder": "Thane", "gb road": "Thane",
    "kolshet": "Thane", "hiranandani estate": "Thane", "thane west": "Thane", "thane east": "Thane",
    "vasant vihar thane": "Thane", "manpada": "Thane", "kasarvadavali": "Thane", "pokhran road": "Thane",
}
_AREA_RE = [(re.compile(r"(?<![a-z])" + re.escape(a.lower()) + r"(?![a-z])"), a)
            for a in sorted(list(_AREAS) + list(_ALIASES), key=len, reverse=True)]
_PLAIN_CITIES = {"mumbai", "bombay", "maharashtra", "india", "mumbai suburban", "greater mumbai", ""}


def _parts(v: Any) -> List[str]:
    return [p.strip() for p in re.split(r"\s*(?:,|/|&|\band\b)\s*", str(v or "")) if p.strip()]


def _first_name(v: str) -> str:
    w = re.split(r"\s+", v.strip())[0] if v.strip() else ""
    return w[:1].upper() + w[1:].lower() if w else ""


def gender_letter(v: Any) -> str:
    t = str(v or "").strip().lower()
    if t.startswith(("girl", "female", "f")):
        return "F"
    if t.startswith(("boy", "male", "m")):
        return "M"
    return ""


def _age(v: Any) -> str:
    m = re.search(r"\d{1,2}", str(v or ""))
    return str(int(m.group(0))) if m else ""


def area_of(venue: Any, city: Any = None) -> str:
    """The area to show in the event name, or ''."""
    for text in (venue, city):
        t = " " + re.sub(r"\s+", " ", str(text or "").lower()) + " "
        for rx, name in _AREA_RE:
            if rx.search(t):
                # "Ghatkopar East" -> "Ghatkopar": the short area, as in the examples.
                return re.sub(r"\s+(?:East|West)$", "", _ALIASES.get(name.lower(), name))
    c = re.sub(r"\s+", " ", str(city or "")).strip()
    if c.lower() not in _PLAIN_CITIES:
        return c.title()
    # Last part of the address that isn't a pincode / plain city / state.
    for part in reversed([p.strip() for p in str(venue or "").split(",")]):
        p = re.sub(r"\b\d{6}\b|-\s*$", "", part).strip(" -.")
        if p and p.lower() not in _PLAIN_CITIES and not p.isdigit() and len(p) <= 30:
            return p.title() if p.islower() or p.isupper() else p
    return ""


def event_name(b: Any, fallback: Optional[str] = None) -> str:
    """b: a booking row / dict with child_names, child_ages, child_genders,
    venue, city (and lead_id / parent_name for the fallback)."""
    g = (lambda k: (b.get(k) if isinstance(b, dict) else b[k]) if _has(b, k) else None)
    names = [_first_name(n) for n in _parts(g("child_names"))]
    names = [n for n in names if n]
    genders = _parts(g("child_genders"))
    ages = _parts(g("child_ages"))
    n = max(len(names), 1)
    codes = []
    for i in range(n):
        code = gender_letter(genders[i] if i < len(genders) else "") + _age(ages[i] if i < len(ages) else "")
        if code:
            codes.append(code)
    who = " & ".join(names[:3])
    if not who:
        parent = str(g("parent_name") or "").strip()
        who = _first_name(parent) if parent else (fallback or (f"Booking #{g('lead_id')}" if g("lead_id") else "Party"))
    bits = [who] + codes[:3] + [area_of(g("venue"), g("city"))]
    return " ".join(b for b in bits if b)


def _has(b: Any, k: str) -> bool:
    try:
        if isinstance(b, dict):
            return k in b
        b[k]
        return True
    except Exception:
        return False
