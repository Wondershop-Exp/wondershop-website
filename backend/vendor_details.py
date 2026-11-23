"""
Reading a partner / vendor contact from a Slack post (2026-11-23, per Shruti).

  "For creating vendors/partners, you are not updating information from slack.
   whatever information I am providing - like name, number, deals in, remarks,
   locality, pincode, address, city, etc. you update everything in remarks and
   copy phone no. in name, can we try updating other fields as well"

Without the Claude API key the bot took the first line as the name (often the
phone number) and kept the whole post as a note. parse_contact() reads the
post line by line instead — no API key needed:

    97692 97760                         -> mobile (a 2nd number -> alternate)
    PARTY POP RENTAL INDIA              -> business name (first plain line)
    contact person: Tamanna             -> contact person
    deals in - carnival                 -> "What do you deal in" category
    42, M M Chhotani Rd, Mahim, Mumbai, Maharashtra 400016
                                        -> address, locality (Mahim), city, pincode
    email: x@y.com / instagram link / website
    met at Prachi's party ...           -> notes (anything not placed in a field)

parse_updates() reads a thread reply such as "pincode 400016", "locality
Andheri" or "deals in decorator" into the fields to fill on that partner.
Used by routers/slack_vendors.py.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from lead_details import clean, known_area
from event_naming import _AREA_RE, _ALIASES

PHONE_RE = re.compile(r"(?<![\w/])(\+?\d[\d\s\-().]{8,16}\d)(?![\w/])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)|(?:^|\s)@([A-Za-z0-9_.]{3,30})\b", re.I)
PIN_RE = re.compile(r"(?<!\d)([1-9]\d{2}\s?\d{3})(?!\d)")
EMOJI_RE = re.compile(r":[a-z0-9_+\-]+:")

CITIES = ["Navi Mumbai", "Mumbai", "Thane", "Pune", "Delhi", "New Delhi", "Gurgaon", "Gurugram", "Noida", "Bangalore",
          "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Surat", "Nashik", "Nagpur", "Akola", "Lonavala",
          "Alibaug", "Goa", "Jaipur", "Indore", "Vasai", "Virar", "Kalyan", "Dombivli", "Panvel", "Bhiwandi"]
_CITY_RE = [(re.compile(rf"(?<![a-z]){re.escape(c.lower())}(?![a-z])"), c) for c in CITIES]
STATES = r"maharashtra|gujarat|karnataka|haryana|delhi|goa|india|uttar pradesh|telangana|tamil nadu|west bengal|rajasthan|madhya pradesh"
ADDR_WORDS = re.compile(r"\b(?:road|rd|marg|lane|street|st|sector|sec|shop|floor|flr|building|bldg|tower|mall|complex|plot|"
                        r"opp|opposite|near|nr|behind|station|nagar|society|soc|chs|wing|gala|basement|industrial|estate|"
                        r"apartment|apt|house|chowk|cross|main|west|east|w|e)\b\.?", re.I)

# Words in a post -> "What do you deal in" category (partner_categories.BASE names).
DEALS_RULES = [
    (r"\bdecor(?:ator|ation)?s?\b|\bballoon\s*decor", "Decorator"),
    (r"photograph|\bphoto\s*&?\s*video|videograph|\bcamera\b", "Photographer"),
    (r"\bdj\b|\bsound\b|\bmusic\b", "DJ"),
    (r"magician|\bmagic\b", "Magician"),
    (r"bubble\s*show", "Bubble Show Artist"),
    (r"science\s*(?:show|station)", "Science Show Artist"),
    (r"puppet", "Puppet Show Artist"),
    (r"\bhost\b|\banchor\b|\bemcee\b", "Host"),
    (r"\bbaker|\bcakes?\b|\bbakery\b", "Baker"),
    (r"tempo|transport|porter|\btruck\b|\bcab\b|\bdriver\b", "Transport Services"),
    (r"return\s*gift|gift\s*shop|\bgifts?\b", "Gift Shop"),
    (r"carnival|\bstalls?\b|\bgames?\b|gaming|inflatable|bouncy|bouncer|jumping|trampoline|live\s*(?:counter|station)|"
     r"t-?shirt\s*printing|fridge\s*magnet|mascot|\bps5\b|arcade|soft\s*play|rides?\b|sky\s*balloon", "Live Stations & Mascots"),
    (r"volunteer", "Event Volunteer"),
    (r"stationery|stationary", "Stationery Store"),
    (r"art\s*(?:&|and)?\s*craft|craft\s*store", "Art & Craft Store"),
    (r"hardware|electric|plumbing|sanitary", "Hardware Store"),
    (r"packaging", "Packaging Store"),
    (r"personali[sz]", "Personalization Store"),
    (r"\bprops?\b|decorative\s*items|decoration\s*store", "Decoration Store"),
    (r"entertain|workshop|\bshow\b", "Other Entertainer"),
]
OTHER_DEALS = [(r"cater|food|live\s*food|snacks?", "Catering"), (r"\bbrand\s*carts?|\bcarts?\b", "Custom carts")]

LABELS = [   # (field, pattern) for "Label: value" / "Label - value"
    ("business_name", r"company(?:\s*name)?|business(?:\s*name)?|firm(?:\s*name)?|brand(?:\s*name)?|shop(?:\s*name)?|vendor(?:\s*name)?|name"),
    ("contact_person", r"contact\s*person|contact\s*name|person|owner|proprietor|poc|spoc"),
    ("deals_in", r"deals?\s*in|deal\s*in|category|service\s*type|type|work|business\s*type|they\s*do"),
    ("services", r"services?|offers?|products?|provides?"),
    ("address", r"address|addr|shop\s*address|office"),
    ("locality", r"locality|area|location|based\s*(?:out\s*of|in|at)|stays\s*in|lives\s*in|warehouse(?:\s*in)?"),
    ("city", r"city"),
    ("pincode", r"pin\s*code|pincode|pin"),
    ("email", r"e-?mail(?:\s*id)?"),
    ("website", r"website|site|web"),
    ("instagram", r"instagram|insta|ig"),
    ("notes", r"note|notes|remarks?|comments?|feedback|quote|quoted|rates?|price|referred\s*by|reference|ref"),
]
_LABEL_RE = [(f, re.compile(rf"^\s*(?:{p})\s*(?:[:=\-–]|\s(?=\S))\s*(.+?)\s*$", re.I)) for f, p in LABELS]
STOP_NAME = re.compile(r"\b(?:met|please|create|contact|call|vendor\s+contact|quote|good|experience|years?|followers?|"
                       r"we|our|they|their|offers?|available|price|rates?)\b", re.I)
STRONG_ADDR = re.compile(r"\b(?:road|rd|marg|lane|sector|floor|flr|building|bldg|tower|mall|complex|plot|opp|opposite|behind|"
                         r"society|chs|wing|gala|basement|estate|apartments?|chowk|nagar)\b|\bshop\s*(?:no|#|\d)", re.I)
HANDLE_RE = re.compile(r"^@?(?=[a-z0-9_.]*[0-9_.])[a-z][a-z0-9_.]{4,29}$")


def _tidy(v, n=255) -> Optional[str]:
    v = re.sub(r"\s+", " ", EMOJI_RE.sub("", str(v or ""))).strip(" ,;:-–.|")
    return v[:n] or None


def _name(v) -> Optional[str]:
    v = _tidy(v, 150)
    if not v:
        return None
    return v.title() if (v.islower() and len(v) > 3) else v


def digits10(v) -> Optional[str]:
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d if re.fullmatch(r"[6-9]\d{9}", d) else None


def area_name(text: str) -> Optional[str]:
    t = " " + re.sub(r"\s+", " ", str(text or "").lower()) + " "
    hits = [re.sub(r"\s+(?:East|West)$", "", _ALIASES.get(name.lower(), name)) for rx, name in _AREA_RE if rx.search(t)]
    specific = [h for h in hits if h not in ("Navi Mumbai",)]
    return (specific or hits or [None])[0]


def city_of(text: str) -> Optional[str]:
    t = " " + str(text or "").lower() + " "
    for rx, c in _CITY_RE:
        if rx.search(t):
            return {"Gurugram": "Gurgaon", "Bengaluru": "Bangalore", "New Delhi": "Delhi"}.get(c, c)
    return None


def deals_of(text: str, categories: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """(category from the list, or None; a short "other" description)."""
    low = (text or "").lower()
    for c in sorted(categories, key=len, reverse=True):   # an exact category name wins ("Electricity Vendor")
        if c.lower() != "others" and re.search(rf"(?<![a-z]){re.escape(c.lower())}(?![a-z])", low):
            return c, None
    for p, c in DEALS_RULES:
        if re.search(p, low) and c in categories:
            return c, None
    for p, o in OTHER_DEALS:
        if re.search(p, low):
            return "Others", o
    return None, None


def _looks_address(t: str) -> bool:
    if STRONG_ADDR.search(t) and (re.search(r"\d|,", t) or len(t.split()) <= 6 or city_of(t) or known_area(t)):
        return True
    if PIN_RE.search(t) and (t.count(",") >= 1 or ADDR_WORDS.search(t)):
        return True
    return t.count(",") >= 2 and bool(ADDR_WORDS.search(t)) or bool(re.search(rf"\b(?:{STATES})\b", t, re.I)) and "," in t


class C:
    def __init__(self):
        self.f: Dict[str, Any] = {}
        self.phones: List[str] = []
        self.notes: List[str] = []
        self.addr: List[str] = []
        self.deals_hint: List[str] = []

    def set(self, k, v, overwrite=False):
        if v not in (None, "") and (overwrite or not self.f.get(k)):
            self.f[k] = v

    def add_service(self, v, overwrite=False):
        v = _tidy(v, 500)
        if not v:
            return
        cur = self.f.get("services")
        self.f["services"] = v if (overwrite or not cur) else (cur + ", " + v)[:500]


def _place(c: C, t: str, overwrite=False):
    """Locality / city / pincode out of a piece of address text."""
    pm = PIN_RE.search(t)
    if pm:
        c.set("pincode", pm.group(1).replace(" ", ""), overwrite)
    a = area_name(t)
    if a:
        c.set("locality", a, overwrite)
    ct = city_of(t)
    if ct:
        c.set("city", ct, overwrite)
    elif a:
        c.set("city", "Mumbai")


def _apply(c: C, field: str, v: str, categories: List[str], overwrite=False) -> bool:
    v = v.strip()
    if not v:
        return False
    if field in ("business_name", "contact_person"):
        c.set(field, _name(v), overwrite); return True
    if field == "deals_in":
        cat, other = deals_of(v, categories)
        if cat:
            c.set("deals_in", cat, overwrite)
            if other:
                c.set("deals_in_other", other, overwrite)
        else:
            c.set("deals_in", "Others", overwrite); c.set("deals_in_other", _tidy(v, 60), overwrite)
            c.set("new_category", _tidy(v, 40).title() if len(v.split()) <= 3 else None, overwrite)
        if len(v.split()) > 1 or "," in v:
            c.add_service(v, overwrite)
        return True
    if field == "services":
        c.add_service(v, overwrite)
        cat, other = deals_of(v, categories)
        if cat:
            c.set("deals_in", cat)
            if other:
                c.set("deals_in_other", other)
        return True
    if field == "address":
        c.set("address", _tidy(v, 500), overwrite); _place(c, v, overwrite); return True
    if field == "locality":
        a = area_name(v) or _tidy(re.split(r"[,/]| and ", v)[0], 100)
        c.set("locality", a, overwrite)
        ct = city_of(v)
        c.set("city", ct or ("Mumbai" if area_name(v) else None), overwrite)
        if len(v) > len(a or "") + 3:
            c.notes.append(f"Location: {_tidy(v)}")
        return True
    if field == "city":
        c.set("city", city_of(v) or _tidy(v, 50), overwrite); return True
    if field == "pincode":
        m = PIN_RE.search(v)
        if not m:
            return False
        c.set("pincode", m.group(1).replace(" ", ""), overwrite); return True
    if field == "email":
        m = EMAIL_RE.search(v)
        if not m:
            return False
        c.set("email", m.group(0).lower(), overwrite); return True
    if field == "website":
        m = URL_RE.search(v)
        c.set("website", _tidy(m.group(0) if m else v, 255), overwrite); return True
    if field == "instagram":
        m = IG_RE.search(v)
        h = (m.group(1) or m.group(2)) if m else re.sub(r"^@", "", v.split()[0])
        c.set("instagram", h.strip("/@"), overwrite); return True
    if field == "notes":
        c.notes.append(_tidy(v, 1000) or v); return True
    if field == "notes_line":
        c.notes.append(_tidy(v, 1000) or v); return True
    return False


def read_line(c: C, raw: str, categories: List[str], reply=False) -> None:
    bullet = bool(re.match(r"^\s*(?::[a-z0-9_+\-]+:|[\u2600-\u27bf\U0001F300-\U0001FAFF])", clean(raw)))
    t = EMOJI_RE.sub("", clean(raw)).strip().strip("*_").strip()
    t = re.sub(r"^\s*(?:[-•●▪◦]|\d{1,2}[.)])\s+", "", t)
    if not t:
        return
    ow = reply
    # links: instagram -> instagram, maps -> notes, other -> website
    for u in URL_RE.findall(t):
        if "instagram.com" in u:
            m = IG_RE.search(u)
            if m:
                c.set("instagram", (m.group(1) or "").strip("/"), ow)
        elif re.search(r"goo\.gl/maps|maps\.app|google\.[a-z.]+/maps", u):
            c.notes.append(f"Map: {u}")
        else:
            c.set("website", u.rstrip(".,)"), ow)
        t = t.replace(u, " ")
    igm = re.search(r"(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)\S*", t, re.I)
    if igm:
        c.set("instagram", igm.group(1).strip("/."), ow)
        t = t.replace(igm.group(0), " ")
    em = EMAIL_RE.search(t)
    if em:
        c.set("email", em.group(0).lower(), ow)
        t = t.replace(em.group(0), " ")
    # phone numbers anywhere ("97734 04342 DJ Sandesh", "Jane : 99206 15055")
    for pm in list(PHONE_RE.finditer(t)):
        d = digits10(pm.group(1))
        if d:
            if d not in c.phones:
                c.phones.append(d)
            t = t.replace(pm.group(1), " ")
    t = re.sub(r"\s+", " ", t).strip(" ,;:-–/|")
    t = re.sub(r"^(?:contact\s*(?:number|no\.?|details)?|mobile|phone|ph|mob|whatsapp|tel|call)\s*[:\-–]?\s*$", "", t, flags=re.I)
    t = re.sub(r"^(?:email|e-mail|website|instagram|insta)\s*[:\-–]?\s*$", "", t, flags=re.I)
    if not t:
        return
    # "Label: value"
    for field, rx in _LABEL_RE:
        m = rx.match(t)
        if not m:
            continue
        if field == "business_name" and not re.match(r"^\s*(?:company|business|firm|brand|shop|vendor)?\s*name\b|^\s*(?:company|business|firm|brand)\b", t, re.I):
            continue
        if field in ("instagram", "website") and not re.match(rf"^\s*(?:{dict(LABELS)[field]})\s*[:=\-–]", t, re.I):
            continue
        if field == "notes" and not re.match(r"^\s*(?:note|notes|remarks?|comments?|feedback|quote|quoted|rates?|price|referred\s*by|reference|ref)\b", t, re.I):
            continue
        if field == "notes" and not re.match(r"^\s*(?:note|notes|remarks?|comments?)\b", t, re.I):
            c.notes.append(_tidy(t, 1000)); return          # "quoted 5k ...", "Referred by Hadi" kept whole
        if _apply(c, field, m.group(1), categories, ow):
            return
    if HANDLE_RE.match(t) and not EMAIL_RE.search(t):   # "pankajphotography01" = their Instagram handle
        c.set("instagram", t.lstrip("@"), ow); return
    if bullet and not _looks_address(t):              # ":ferris_wheel: Amusement Rides" = what they offer
        c.deals_hint.append(t); c.notes.append(_tidy(t, 500)); return
    if re.search(r"(?:₹|rs\.?|inr)?\s*-?\s*\d{3,6}\s*(?:/-|k\b)?\s*$", t, re.I) and not _looks_address(t) and len(t.split()) <= 8:
        c.notes.append(_tidy(t, 500)); return         # "Photography -4500", "Video with editing 6000"
    if len(t.split()) > 14:          # long description -> note (and a hint for "deals in")
        c.deals_hint.append(t)
        c.notes.append(_tidy(t, 1500))
        return
    if _looks_address(t):
        c.addr.append(t); _place(c, t, ow); return
    # a lone place name ("Gurgaon", "Andheri", "Mumbai")
    if len(t.split()) <= 3 and (known_area(t) or city_of(t)) and not deals_of(t, categories)[0]:
        a, ct = area_name(t), city_of(t)
        if a:
            c.set("locality", a, ow)
        c.set("city", ct or ("Mumbai" if a else None), ow)
        return
    cat, other = deals_of(t, categories)
    short = len(t.split()) <= 6 and not re.search(r"\d{3,}", t)
    if not reply and short and not c.f.get("business_name") and not STOP_NAME.search(t):
        # first plain line = the name she uses for them; a category word in it also sets "deals in"
        c.set("business_name", _name(t))
        if cat:
            c.set("deals_in", cat)
            if other:
                c.set("deals_in_other", other)
        return
    if cat and len(t.split()) <= 10:
        c.set("deals_in", cat, ow)
        if other:
            c.set("deals_in_other", other, ow)
        c.add_service(t, ow)
        return
    if (not reply and short and c.f.get("business_name") and not c.f.get("contact_person")
            and re.fullmatch(r"[A-Za-z][A-Za-z.']*(?:\s+[A-Za-z][A-Za-z.']*){0,2}", t) and not STOP_NAME.search(t)
            and not known_area(t) and not STRONG_ADDR.search(t)):
        c.set("contact_person", _name(t)); return
    c.deals_hint.append(t)
    c.notes.append(_tidy(t, 1500))


def _finish(c: C, categories: List[str]) -> Dict[str, Any]:
    f = dict(c.f)
    if c.addr and not f.get("address"):
        f["address"] = _tidy(", ".join(a.strip(" ,-") for a in c.addr), 500)
    if not f.get("deals_in"):
        cat, other = deals_of(" ".join(c.deals_hint + [f.get("business_name") or ""]), categories)
        if cat:
            f["deals_in"] = cat
            if other:
                f["deals_in_other"] = other
    if not f.get("business_name") and f.get("instagram"):
        f["business_name"] = "@" + f["instagram"]
    if c.phones:
        f["phone"] = c.phones[0]
        if len(c.phones) > 1:
            f["alternate_phone"] = c.phones[1]
        if len(c.phones) > 2:
            c.notes.append("Other numbers: " + ", ".join(c.phones[2:]))
    f["notes"] = "\n".join(n for n in c.notes if n) or None
    return f


def parse_contact(text: str, categories: List[str]) -> List[Dict[str, Any]]:
    """One contact per post (the usual case). Same keys as the Claude reader:
    business_name, contact_person, phone, alternate_phone, email, website,
    instagram, address, locality, city, pincode, deals_in, deals_in_other,
    new_category, services, notes."""
    c = C()
    for line in clean(text).splitlines():
        read_line(c, line, categories)
    f = _finish(c, categories)
    if not (f.get("business_name") or f.get("phone") or f.get("contact_person")):
        return []
    return [f]


FIELD_LABELS = {"business_name": "name", "contact_person": "contact person", "phone": "mobile", "alternate_phone": "alternate number",
                "email": "email", "website": "website", "instagram": "Instagram", "address": "address", "locality": "locality",
                "city": "city", "pincode": "pincode", "deals_in": "deals in", "services": "services"}


def parse_updates(text: str, categories: List[str]) -> Tuple[Dict[str, Any], str]:
    """A thread reply -> (fields to change, the rest as a note). Only clear
    details change fields: a labelled line ("pincode 400016", "deals in:
    decorator", "contact person Riya"), a phone number, email, link, address
    or a lone area name. Everything else stays a note."""
    changes: Dict[str, Any] = {}
    rest: List[str] = []
    for line in clean(text).splitlines():
        if not line.strip():
            continue
        c = C()
        read_line(c, line, categories, reply=True)
        f = _finish(c, categories)
        note = f.pop("notes", None)
        f = {k: v for k, v in f.items() if v not in (None, "") and k != "new_category"}
        if f:
            changes.update(f)
            if note and note.strip() != line.strip():
                rest.append(note)
        else:
            rest.append(line.strip())
    return changes, "\n".join(rest)
