"""
Slack lead bot (2026-10-20, per Shruti).

  The team posts NEW LEADS OF ANY KIND in one Slack channel (#leads) and this
  bot puts them straight into Leads (Sales module + admin Leads tab), with the
  right lead generated date. "Make this a channel to make any leads - insta /
  referral etc. We can mention the lead source or you can ask if not
  mentioned."

  1. TEXT, e.g. Sid's usual list:
         19 Oct Leads:
         1. JINAL TEJANI (+919820541935) - replied to the Harry Potter message
         2. PRIYAL VIKMANI (+919870770001) - insta ad
         3. Neha K 98200 11111 - referred by Anjali, 5:40pm
     -> one lead per line with a number (or an Instagram @handle). Lead date =
        the date in the heading (a list posted next morning still lands on the
        right day); time = a time on the line, else when it was posted (today's
        leads) or 11:59 PM of that day. A heading or line like "Referrals:" /
        "Insta ads" sets the source for the lines under it.
  2. SCREENSHOTS of the AiSensy chat / Instagram DM. Claude reads name, number,
     the ad card (-> Ad shown + Instagram AiSensy Ad), the first-message time
     (-> exact lead time) and the answers to our 7 questions (age, gender,
     venue, # kids, theme, services, date). A screenshot of someone already in
     Leads only fills blanks (and corrects the lead time).

  SOURCE comes from words on the line / heading / message (see
  _SOURCE_RULES): insta ad / aisensy, insta DM, broadcast / revert / "replied
  to", facebook / fb, google, referral / referred by NAME (-> Referred by),
  repeat, WSR, stall, website; bare "insta" = Instagram. If none is given the
  lead is still created and the bot ASKS in the thread; a reply there sets it
  ("referral by Neha" = all missing ones; "2 stall" / "Saloni insta ad" /
  "#145 google" = that one, also to correct a source).

  Labels (Lead Source stays on the approved list, catalogue_data.LEAD_SOURCES):
     Instagram AiSensy Ad -> Source "Instagram",  Platform "Instagram AiSensy Ad"
     Instagram DM         -> Source "Instagram",  Platform "Instagram DM"
     WhatsApp Broadcast   -> Source "WhatsApp Broadcast"
     others               -> Source "Facebook" / "Google" / "Referral" / ...

  Same mobile number with a lead generated within the last 90 days = the same
  lead (per Shruti, counted from the lead generation date): blanks get
  filled in, and anything DIFFERENT (name, source, venue, ...) is added to the
  lead's "Changes / Updates" note instead of overwriting. Over 90 days after
  the lead generation date a new lead is made, linked to (noting) the earlier one. Lead Source only ever takes a
  value from the approved list (catalogue_data.LEAD_SOURCES); anything else
  is asked about. Partner (vendor) numbers are skipped. The bot replies in the thread with
  what it did and links to each lead.

Set-up: TASKS.md + docs/slack_leads_app_manifest.yml. Needs SLACK_SIGNING_SECRET
+ SLACK_BOT_TOKEN; screenshots also need ANTHROPIC_API_KEY.
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import re
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from config import settings
from database import database
import sheet_sync
from routers.aisensy_webhook import (
    normalise_phone, _is_partner, _existing_lead, _playbook_id, _playbook_log, _log_call,
)

router = APIRouter()
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
SLACK_API = "https://slack.com/api"

# Every lead source the bot understands -> (Lead Source, Lead Source Platform).
# Lead Source values are the approved list (catalogue_data.LEAD_SOURCES).
SOURCES = {
    "ad":        ("Instagram",          "Instagram AiSensy Ad"),
    "dm":        ("Instagram",          "Instagram DM"),
    "instagram": ("Instagram",          None),
    "broadcast": ("WhatsApp Broadcast", "WhatsApp Broadcast"),
    "facebook":  ("Facebook",           None),
    "google":    ("Google",             None),
    "referral":  ("Referral",           None),
    "repeat":    ("Repeat",             None),
    "wsr":       ("WSR Repeat",         None),
    "stall":     ("Stall",              None),
    "website":   ("Website",            None),
    "chatgpt":   ("ChatGpt",            None),   # 2026-10-23
}
_HELP_LABELS = [("ad", "Instagram ad"), ("dm", "Instagram DM"), ("broadcast", "WhatsApp broadcast"),
                ("facebook", "Facebook"), ("google", "Google"), ("referral", "Referral (referred by …)"),
                ("repeat", "Repeat"), ("wsr", "WSR Repeat"), ("stall", "Stall"), ("website", "Website"), ("chatgpt", "ChatGpt")]


def source_help() -> str:
    """The sources the team may use — only those on the approved list."""
    from catalogue_data import LEAD_SOURCES
    return " · ".join(lbl for k, lbl in _HELP_LABELS if SOURCES[k][0] in LEAD_SOURCES)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# ─── text lists ────────────────────────────────────────────────────────────

_SOURCE_RULES = [   # first match wins
    ("broadcast", r"broadcast|\brevert|repl(?:ied|y)\s+to\b"),
    ("wsr",       r"\bwsr\b"),
    ("repeat",    r"\brepeat\b|returning|existing (?:customer|client)|booked (?:with us )?before|past (?:customer|client)"),
    ("dm",        r"\bdms?\b|direct message|insta(?:gram)?\s*(?:msg|message|inbox)"),
    ("facebook",  r"\bfacebook\b|\bfb\b"),
    ("ad",        r"\bads?\b|aisensy|ai-?sensi"),
    ("instagram", r"\binsta(?:gram)?\b|\big\b"),
    ("google",    r"\bgoogle\b"),
    ("referral",  r"referr?al|\breferred\b|\bref\b|\breference\b|recommended by"),
    ("stall",     r"\bstall\b|exhibition|\bflea\b|pop-?up"),
    ("website",   r"\bwebsite\b|\bweb\b|build-?a-?birthday|\bbuilder\b"),
]
REFERRER_RE = re.compile(r"(?:referred|referral|ref|reference|recommended)\s*(?:by|from|of)?\s*[:\-–]?\s*"
                         r"([A-Za-z][A-Za-z .']{1,40}?)\s*(?=$|[,;()\-–—|]|\s+(?:for|wants|looking|needs|and)\b)", re.I)


def source_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """(source key or None, referrer name or None) from free text."""
    t = (text or "").lower()
    for key, rx in _SOURCE_RULES:
        if re.search(rx, t):
            ref = None
            if key == "referral":
                m = REFERRER_RE.search(text or "")
                if m and m.group(1).strip().lower() not in ("by", "from", "a", "the", "friend"):
                    ref = m.group(1).strip()
            return key, ref
    return None, None


def _year_for(month: int, day: int, today: date) -> date:
    """'19 Oct' -> the most recent 19 Oct that isn't in the future."""
    try:
        d = date(today.year, month, day)
    except ValueError:
        return today
    if d > today + timedelta(days=1):
        try:
            d = date(today.year - 1, month, day)
        except ValueError:
            pass
    return d


def parse_heading_date(line: str, today: date) -> Optional[date]:
    l = line.lower()
    if "lead" not in l and not re.fullmatch(r"\s*\d{1,2}\s*[a-z]{3,9}\.?\s*:?\s*", l):
        return None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", l)
    if m:
        return _year_for(MONTHS[m.group(2)], int(m.group(1)), today)
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{1,2})\b", l)
    if m:
        return _year_for(MONTHS[m.group(1)], int(m.group(2)), today)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", l)
    if m:
        dd, mm = int(m.group(1)), int(m.group(2))
        if m.group(3):
            yy = int(m.group(3)); yy = yy + 2000 if yy < 100 else yy
            try:
                return date(yy, mm, dd)
            except ValueError:
                return None
        return _year_for(mm, dd, today)
    if "today" in l:
        return today
    if "yesterday" in l:
        return today - timedelta(days=1)
    return None


TIME_RE = re.compile(r"\b(\d{1,2})([:.])(\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm)\b", re.I)


def parse_time(text: str) -> Optional[Tuple[int, int]]:
    for m in TIME_RE.finditer(text or ""):
        if m.group(1):
            h, mi, ap = int(m.group(1)), int(m.group(3)), (m.group(4) or "").lower()
            if m.group(2) == "." and not ap:
                continue          # "2.50" is a number, not a time
        else:
            h, mi, ap = int(m.group(5)), 0, m.group(6).lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            return h, mi
    return None


PHONE_IN_LINE = re.compile(r"(\+?\d[\d\s-]{8,16}\d)")
HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{2,30})")


def parse_lead_list(text: str, posted_at: datetime) -> List[Dict[str, Any]]:
    """A posted list -> [{name, phone, handle, note, source, referred_by, generated_at}]."""
    posted_ist = posted_at.astimezone(IST)
    today = posted_ist.date()
    day = today
    section_src = None
    out = []
    for raw in (text or "").splitlines():
        line = raw.replace("*", "").replace("_", " ").strip()
        if not line:
            continue
        hd = parse_heading_date(line, today)
        if hd and not PHONE_IN_LINE.search(line) and not HANDLE_RE.search(line):
            day = hd
            k = source_from_text(line)
            if k[0]:
                section_src = k
            continue
        if not PHONE_IN_LINE.search(line) and not HANDLE_RE.search(line):
            # a heading such as "Referrals:" / "Insta ads" / "Stall leads:"
            k = source_from_text(line)
            if k[0] and len(line) <= 40:
                section_src = k
            continue
        body = re.sub(r"^\s*(?:\d{1,3}[.)]|[-•●▪︎*])\s*", "", line)
        pm = PHONE_IN_LINE.search(body)
        phone = normalise_phone(pm.group(1)) if pm else None
        hm = HANDLE_RE.search(body)
        if not phone and not hm:
            continue
        cut = pm.start() if pm else hm.start()
        name = body[:cut]
        name = re.sub(r"[\s(\[\-–—:|,]+$", "", name).strip()
        rest = body[(pm.end() if pm else hm.end()):]
        rest = re.sub(r"^[\s)\]]*", "", rest)
        note = re.sub(r"^[\-–—:|,\s]+", "", rest).strip()
        src, ref = source_from_text(note)
        if not src and section_src:
            src, ref = section_src
        t = parse_time(note)
        if t:
            gen = datetime(day.year, day.month, day.day, t[0], t[1], tzinfo=IST)
            note = TIME_RE.sub("", note).strip(" ,-–—")
        elif day == today:
            gen = posted_ist
        else:
            # A list for an earlier day with no time: end of that day, so it
            # still sorts after that day's earlier leads. A screenshot of the
            # chat later corrects it to the exact time.
            gen = datetime(day.year, day.month, day.day, 23, 59, tzinfo=IST)
        out.append({
            "name": name or None, "phone": phone, "handle": hm.group(1) if hm else None,
            "note": note or None, "source": src, "referred_by": ref, "generated_at": gen,
        })
    return out


# ─── screenshots (Claude) ──────────────────────────────────────────────────

VISION_PROMPT = """You are reading screenshots that a sales teammate at Wondershop Experiences (a kids' birthday party company in Mumbai) posted. They are chats from the AiSensy WhatsApp inbox, or Instagram DMs, with people enquiring about parties. Today is {today} (India time). The teammate's message text was: {text!r}

Extract every DIFFERENT customer you can see. Several screenshots of one chat are ONE customer. For each, return:
- name: as shown in the chat header (keep their spelling, drop emoji)
- phone: the number in the header, digits with country code, e.g. "+919820314142"; null if none shown
- instagram_handle: for Instagram DMs, the @handle without "@"; else null
- kind: "ad" if the chat starts with an ad card (headline, fb.me / instagram link, "Ad ID"); "broadcast" if the chat starts with OUR outgoing promotional/broadcast message and they replied to it; "dm" if it is an Instagram DM screen; "unknown" if you can't tell
- ad_headline: the ad card's bold headline, e.g. "Planning a Birthday?"; else null
- ad_id: digits after "Ad ID"; else null
- first_message_at: date and time of THEIR earliest message visible, as "YYYY-MM-DDTHH:MM" (24h, India time). Chat timestamps look like "10:59 AM, 19/10/26" (day/month/year) or just "04:01 PM" (then use the date shown nearby, else today). null if no time is visible for them
- child_age: the birthday child's age as a number/text (e.g. "10"); null if not given
- child_gender: "Male" (boy/M) or "Female" (girl/F); null if not given
- venue: venue/location text they gave; null if none
- kids_count: number of kids as an integer (use the number in "around 20"); null if none
- theme: theme they mentioned; null if none
- services: services they want, short text; null if none
- event_date: party date as "YYYY-MM-DD" (the next such date on or after today) when a day AND month are given; else null
- event_date_text: the date exactly as they wrote it, if any (e.g. "31", "22nd Nov"); else null
- summary: one short line on what they want (e.g. "10 yr old girl's pool party, Versova, 18 kids")

Their answers usually follow our questionnaire 1) Age 2) Gender 3) Venue/Location 4) # kids 5) Theme 6) Services 7) Date of Event — sometimes as bare lines in that order (e.g. "10 / F / Versova / 18 / Pool party / Decoration / 31"). Only report what is actually visible; never guess a phone number.

Reply with ONLY a JSON object: {{"leads": [ ... ]}}"""

IMAGE_MAX_EDGE = 1568


def _shrink(data: bytes, mime: str) -> Tuple[bytes, str]:
    """Large screenshots cost more and can exceed the API's size limit."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if max(im.size) <= IMAGE_MAX_EDGE and len(data) < 3_500_000:
            return data, mime
        im.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, mime


async def read_screenshots(images: List[Tuple[bytes, str]], text: str, today: date) -> List[Dict[str, Any]]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set on Railway, so I can't read screenshots yet.")
    content: List[Dict[str, Any]] = []
    for data, mime in images[:8]:
        data, mime = _shrink(data, mime)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": VISION_PROMPT.format(today=today.isoformat(), text=text or "")})
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.ANTHROPIC_MODEL, "max_tokens": 2000,
                  "messages": [{"role": "user", "content": content}]},
        )
    if r.status_code != 200:
        raise RuntimeError(f"Claude API error {r.status_code}: {r.text[:300]}")
    out_text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", out_text, re.S)
    if not m:
        raise RuntimeError("Couldn't read the screenshot (no data came back).")
    leads = json.loads(m.group(0)).get("leads") or []
    return [l for l in leads if isinstance(l, dict)]


def _clean_screenshot_lead(l: Dict[str, Any], posted_at: datetime) -> Dict[str, Any]:
    def s(k, n=255):
        v = l.get(k)
        v = str(v).strip() if v not in (None, "") else None
        return v[:n] if v else None
    gen = None
    if s("first_message_at"):
        try:
            gen = datetime.fromisoformat(s("first_message_at")[:16]).replace(tzinfo=IST)
            if gen > posted_at.astimezone(IST) + timedelta(minutes=5) or gen < posted_at - timedelta(days=60):
                gen = None
        except ValueError:
            gen = None
    ev = None
    if s("event_date"):
        try:
            ev = date.fromisoformat(s("event_date")[:10])
        except ValueError:
            ev = None
    kids = l.get("kids_count")
    try:
        kids = int(re.search(r"\d+", str(kids)).group(0)) if kids not in (None, "") else None
    except (AttributeError, ValueError):
        kids = None
    gender = s("child_gender")
    gender = {"m": "Male", "male": "Male", "boy": "Male", "f": "Female", "female": "Female", "girl": "Female"}.get(
        (gender or "").lower(), gender)
    kind = (s("kind") or "").lower()
    ad = s("ad_headline", 400)
    if kind not in ("ad", "dm", "broadcast"):
        kind = "ad" if (ad or s("ad_id")) else None
    notes = [x for x in (s("summary", 300), (f"Services: {s('services', 300)}" if s("services") else None),
                         (f"Date as written: {s('event_date_text', 60)}" if s("event_date_text") and not ev else None)) if x]
    return {
        "name": s("name"), "phone": normalise_phone(s("phone") or ""), "handle": (s("instagram_handle", 60) or "").lstrip("@") or None,
        "source": kind, "referred_by": None, "generated_at": gen,
        "ad_shown": (ad + (f" · Ad ID {s('ad_id', 60)}" if s("ad_id") else "")) if ad else (f"Ad ID {s('ad_id', 60)}" if s("ad_id") else None),
        "ad_id": s("ad_id", 100),
        "fields": {"child_ages": s("child_age", 60), "child_genders": gender, "venue": s("venue"),
                   "kids_count": kids, "theme": s("theme"), "event_date": ev},
        "note": " · ".join(notes) or None,
    }


# ─── creating / updating leads ─────────────────────────────────────────────

DETAIL_LABELS = {"child_ages": "age", "child_genders": "gender", "venue": "venue", "kids_count": "# kids",
                 "theme": "theme", "event_date": "event date", "child_names": "child's name",
                 "earlier_conversations": "earlier conversations", "event_sales_lead": "sales lead",
                 "email": "email"}


# ─── "Key = value" records (2026-10-21, per Shruti) ────────────────────────
# Moving the AiSensy leads from the old Google Sheet: one lead per line, e.g.
#   Lead Source = 'Ai-Sensi Instagram', Lead Date =15/10/2026, Contact = 9930083544,
#   Name = QUEEN B , Birthday Month =12_Dec, Locality =Kural west, First Call = 46311,
#   Event Date =46372, Earlier Conversations=mitika - 16/10 call back in evening
# Dates may be dd/mm/yyyy, "16 Oct", or Google Sheets serial numbers (46311 =
# 16 Oct 2026). Fields go where the old-leads import put them (Earlier
# conversations, month-only birthday, first call in the call log).

KV_SPLIT = re.compile(r",\s*(?=[A-Za-z#][A-Za-z0-9 #/_.()-]{0,40}?\s*=)")
KV_KEYS = {   # normalised key -> field
    "leadsource": "source", "source": "source",
    "leaddate": "lead_date", "leadgenerationdate": "lead_date", "enquirydate": "lead_date", "date": "lead_date",
    "contact": "phone", "contactno": "phone", "mobile": "phone", "mobileno": "phone", "phone": "phone",
    "phoneno": "phone", "number": "phone", "whatsapp": "phone", "contactnumber": "phone", "mobilenumber": "phone",
    "name": "name", "parentname": "name", "clientname": "name", "customername": "name", "parent": "name",
    "birthdaymonth": "bday_month", "month": "bday_month", "eventmonth": "bday_month",
    "locality": "locality", "location": "locality", "area": "locality",
    "venue": "venue", "address": "venue",
    "firstcall": "first_call", "firstcalldate": "first_call", "calldate": "first_call",
    "eventdate": "event_date", "partydate": "event_date", "birthdaydate": "event_date", "birthday": "event_date",
    "earlierconversations": "conv", "earlierconversation": "conv", "conversations": "conv", "remarks": "conv",
    "remark": "conv", "notes": "conv", "note": "conv", "comments": "conv",
    "childname": "child_names", "child": "child_names", "kidname": "child_names", "childsname": "child_names",
    "age": "child_ages", "childage": "child_ages",
    "gender": "child_genders",
    "theme": "theme",
    "kids": "kids_count", "nokids": "kids_count", "kidscount": "kids_count", "numberofkids": "kids_count",
    "noofkids": "kids_count", "guests": "kids_count",
    "saleslead": "event_sales_lead", "assignedto": "event_sales_lead", "owner": "event_sales_lead",
    "email": "email", "emailid": "email",
    "followup": "followup", "followupdate": "followup", "nextfollowup": "followup",
}
SHEET_EPOCH = date(1899, 12, 30)


def _kv_date(v: str, today: date, future: bool = False) -> Optional[date]:
    """dd/mm/yyyy, dd/mm, '16 Oct', ISO, or a Sheets serial number. An empty
    date cell in Google Sheets shows as 30/12/1899 (serial 0) -> no date."""
    d = _kv_date_raw(v, today, future)
    return d if d and d.year >= 2000 else None


def _kv_date_raw(v: str, today: date, future: bool = False) -> Optional[date]:
    v = (v or "").strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", v) and 30000 < float(v) < 80000:
        return SHEET_EPOCH + timedelta(days=int(float(v)))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    d = parse_heading_date(v + " lead", today)   # reuses the list-heading date reader
    if d and future and d < today and not re.search(r"\d{4}|/\d{2}$", v):
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            pass
    return d


def _month_of(v: str) -> Optional[int]:
    l = (v or "").lower()
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", l)
    if m:
        return MONTHS[m.group(1)]
    m = re.search(r"\b(\d{1,2})\b", l)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return None


def _key_regex(norm: str) -> str:
    # "leadsource" -> "l[\s_.#-]*e[\s_.#-]*a..." : matches "Lead Source", "Lead_source", "LEAD SOURCE"
    return r"[\s_.#-]*".join(re.escape(ch) for ch in norm)


_KNOWN_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(_key_regex(k) for k in sorted(KV_KEYS, key=len, reverse=True)) + r")\s*=",
    re.I)
_ANY_KEY_RE = re.compile(r"(?:^|[,;\n])\s*([A-Za-z#][A-Za-z0-9 #/_.()-]{0,40}?)\s*=", re.M)
_RECORD_KEYS = ("phone", "name", "source", "lead_date")   # one of these again = the next lead


def _kv_pairs(text: str) -> List[Tuple[str, str]]:
    """All 'Key = value' pairs in the message, in order — whether the leads
    are one per line, separated by blank lines, or run together on one line."""
    marks = {}
    for m in _KNOWN_KEY_RE.finditer(text):
        marks[m.start(1)] = (m.group(1), m.end())
    for m in _ANY_KEY_RE.finditer(text):
        st = m.start(1)
        # skip it when a known key starts inside this label (the known one wins)
        if not any(st <= k < m.end() for k in marks):
            marks[st] = (m.group(1), m.end())
    starts = sorted(marks)
    # drop a mark that sits inside an earlier mark's label
    clean = []
    for st in starts:
        if clean and st < marks[clean[-1]][1]:
            continue
        clean.append(st)
    pairs = []
    for i, st in enumerate(clean):
        label, vstart = marks[st]
        vend = clean[i + 1] if i + 1 < len(clean) else len(text)
        val = text[vstart:vend].strip().rstrip(",;").strip().strip("'\"").strip()
        pairs.append((label.strip(), val))
    return pairs


def parse_kv_records(text: str, posted_at: datetime) -> List[Dict[str, Any]]:
    """'Key = value, Key = value' rows (any number per message) -> lead items
    (empty list if the message isn't in that format)."""
    posted_ist = posted_at.astimezone(IST)
    today = posted_ist.date()
    if (text or "").count("=") < 2:
        return []
    records: List[Tuple[Dict[str, str], List[str]]] = []
    rec: Dict[str, str] = {}
    extra: List[str] = []
    seen: set = set()
    for label, v in _kv_pairs(text):
        key = KV_KEYS.get(re.sub(r"[^a-z]", "", label.lower()))
        if key in _RECORD_KEYS and key in seen:
            records.append((rec, extra))
            rec, extra, seen = {}, [], set()
        if key:
            seen.add(key)
        if not v:
            continue
        if key and key not in rec:
            rec[key] = v
        else:
            extra.append(f"{label}: {v}")
    records.append((rec, extra))
    out = []
    for rec, extra in records:
        if "phone" not in rec and "name" not in rec:
            continue
        phone = normalise_phone(rec.get("phone", ""))
        src, ref = source_from_text(rec.get("source", ""))
        if rec.get("source") and not src:
            extra.append(f"Lead source given: {rec['source']}")
        ld = _kv_date(rec.get("lead_date", ""), today)
        if ld and ld != today:
            gen = datetime(ld.year, ld.month, ld.day, 23, 59, tzinfo=IST)
        else:
            gen = posted_ist
        fields: Dict[str, Any] = {}
        ev = _kv_date(rec.get("event_date", ""), today, future=True)
        if ev:
            fields["event_date"], fields["date_precision"] = ev, "exact"
        elif rec.get("bday_month") and _month_of(rec["bday_month"]):
            mo = _month_of(rec["bday_month"])
            yr = today.year if mo >= today.month else today.year + 1
            fields["event_date"], fields["date_precision"] = date(yr, mo, 1), "month"
        venue = ", ".join(x for x in (rec.get("venue"), rec.get("locality")) if x)
        if venue:
            fields["venue"] = venue[:255]
        for k in ("child_names", "child_ages", "theme", "event_sales_lead", "email"):
            if rec.get(k):
                fields[k] = rec[k][:255]
        if rec.get("child_genders"):
            g = rec["child_genders"].strip().lower()
            fields["child_genders"] = {"m": "Male", "male": "Male", "boy": "Male", "f": "Female",
                                       "female": "Female", "girl": "Female"}.get(g, rec["child_genders"])
        if rec.get("kids_count"):
            m = re.search(r"\d+", rec["kids_count"])
            if m:
                fields["kids_count"] = int(m.group(0))
        conv = "\n".join(x for x in [rec.get("conv")] + extra if x)
        if conv:
            fields["earlier_conversations"] = conv
        calls = []
        fc = _kv_date(rec.get("first_call", ""), today)
        if fc:
            fu = _kv_date(rec.get("followup", ""), today, future=True)
            calls.append({"id": f"c{int(time.time() * 1000) % 10**9}", "date": fc.isoformat(), "time": None,
                          "first_call": True, "disposition": None, "followup_at": fu.isoformat() if fu else None,
                          "remarks": "From the old Google Sheet", "by": None, "at": None})
        out.append({"name": rec.get("name"), "phone": phone, "handle": None, "note": None,
                    "source": src, "referred_by": ref, "generated_at": gen, "fields": fields, "call_log": calls})
    return out


SAME_LEAD_DAYS = 90   # 2026-10-20, per Shruti: same mobile, lead generated within 90 days = same lead

# Counted from the LEAD GENERATION DATE (when the person first enquired),
# falling back to when the lead was created for older leads without one.
LAST_TOUCH_SQL = "COALESCE(l.lead_generated_at, l.created_on)"


def _last10(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


async def _find_existing(phone: Optional[str], name: Optional[str], handle: Optional[str]):
    """The lead this post belongs to: same mobile number (last 10 digits)
    whose lead generation date is within the last 90 days. Instagram DMs without a number match
    on the @handle, else the exact name, by the same rule."""
    if phone:
        where, vals = "RIGHT(regexp_replace(COALESCE(l.phone,''), '\\D', '', 'g'), 10) = :p", {"p": _last10(phone)}
    elif handle:
        where, vals = "l.lead_source_detail ILIKE :h", {"h": f"%@{handle}%"}
    elif name:
        where, vals = "lower(l.parent_name) = lower(:n)", {"n": name}
    else:
        return None
    return await database.fetch_one(
        f"SELECT * FROM (SELECT l.lead_id, {LAST_TOUCH_SQL} AS last_touch FROM leads l "
        f"LEFT JOIN lead_sales_playbook p ON p.lead_id = l.lead_id WHERE {where}) x "
        f"WHERE last_touch >= NOW() - INTERVAL '{SAME_LEAD_DAYS} days' ORDER BY last_touch DESC LIMIT 1",
        values=vals)


async def _earlier_lead(phone: Optional[str]):
    if not phone:
        return None
    return await database.fetch_one(
        f"SELECT l.lead_id, l.status, l.is_booking, {LAST_TOUCH_SQL} AS last_touch FROM leads l "
        "LEFT JOIN lead_sales_playbook p ON p.lead_id = l.lead_id "
        "WHERE RIGHT(regexp_replace(COALESCE(l.phone,''), '\\D', '', 'g'), 10) = :p ORDER BY last_touch DESC LIMIT 1",
        values={"p": _last10(phone)})


def approved_source(source: Optional[str]) -> bool:
    """Only the pre-decided Lead Source list (catalogue_data.LEAD_SOURCES) —
    per Shruti 2026-10-20: never a new value without her confirmation."""
    from catalogue_data import LEAD_SOURCES
    return bool(source) and source in LEAD_SOURCES


def _show(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, date):
        return v.strftime("%d %b %Y")
    return str(v)


def _same(a, b) -> bool:
    norm = lambda v: re.sub(r"\s+", " ", str(v)).strip().lower() if v not in (None, "") else ""
    return norm(a) == norm(b)


async def _append_change_note(lead_id: int, text: str) -> None:
    """Changed values go into the lead's "Changes / Updates" notes (Sales
    module, Notes section) — the lead itself keeps what the team has."""
    await database.execute(
        "UPDATE lead_sales_playbook SET notes_changes_updates = "
        "CASE WHEN COALESCE(notes_changes_updates, '') = '' THEN :t ELSE notes_changes_updates || E'\\n' || :t END "
        "WHERE lead_id = :id", values={"t": text, "id": lead_id})


async def intake(item: Dict[str, Any], who: str, how: str) -> Dict[str, Any]:
    """Create the lead, or update the one with the same mobile generated in
    the last 90 days: blanks are filled in, anything DIFFERENT is added as a note (the
    lead keeps its value). Returns a result dict for the Slack reply."""
    phone, name, handle = item.get("phone"), item.get("name"), item.get("handle")
    if not phone and not handle and not name:
        return {"outcome": "skipped", "why": "no name or number"}
    if phone and await _is_partner(phone):
        return {"outcome": "skipped", "why": "partner (vendor) number", "phone": phone, "name": name}
    skey = item.get("source")
    source, platform = SOURCES[skey] if skey else (None, None)
    if source and not approved_source(source):
        source, platform = None, None     # not on the approved list -> ask instead
    referred_by = item.get("referred_by")
    gen: datetime = item.get("generated_at") or datetime.now(IST)
    fields = {k: v for k, v in (item.get("fields") or {}).items() if v not in (None, "")}
    note = item.get("note")
    actor = f"{who} (Slack)"
    stamp = datetime.now(IST).strftime("%d %b, %I:%M %p")

    async with database.transaction():
        await database.execute("SELECT pg_advisory_xact_lock(hashtext(:k))",
                               values={"k": "lead-intake:" + (_last10(phone) if phone else (handle or (name or "").lower()))})
        existing = await _find_existing(phone, name, handle)
        if existing:
            lead_id = existing["lead_id"]
            row = dict(await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id}))
            sets, vals, filled, changes = [], {"id": lead_id}, [], []

            def take(col, new, label, setter=None):
                cur = row.get(col)
                if new in (None, ""):
                    return
                if cur in (None, "") or (isinstance(cur, str) and not cur.strip()):
                    if setter:
                        setter()
                    else:
                        sets.append(f"{col} = :{col}"); vals[col] = new
                    filled.append(label)
                elif not _same(cur, new):
                    changes.append(f"{label}: {_show(cur)} → {_show(new)}")

            precision = fields.pop("date_precision", None)
            for col, v in fields.items():
                take(col, v, DETAIL_LABELS.get(col, col))
            if precision and "event_date" in vals:
                sets.append("date_precision = :dprec"); vals["dprec"] = precision
            if item.get("call_log"):
                pb = await database.fetch_one("SELECT call_log FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
                cur_calls = (pb["call_log"] if pb else None) or []
                cur_calls = json.loads(cur_calls) if isinstance(cur_calls, str) else cur_calls
                have = {c.get("date") for c in cur_calls if isinstance(c, dict)}
                add = [c for c in item["call_log"] if c["date"] not in have]
                if add:
                    for c in add:
                        c["first_call"] = c["first_call"] and not any(x.get("first_call") for x in cur_calls if isinstance(x, dict))
                        c["by"] = c["by"] or who
                    await database.execute("UPDATE lead_sales_playbook SET call_log = CAST(:c AS JSONB) WHERE lead_id = :id",
                                           values={"c": json.dumps(cur_calls + add), "id": lead_id})
                    filled.append("call log")
            # "=" in a name = a sheet row an older bot version saved whole as the
            # name (2026-10-21): posting the row again repairs it.
            garbled = "=" in (row.get("parent_name") or "")
            placeholder = garbled or (row.get("parent_name") or "").startswith(("Instagram lead", "New lead", "New Sales Lead", "@"))
            if garbled:
                await database.execute(
                    "UPDATE lead_sales_playbook SET notes_special_instructions = NULL "
                    "WHERE lead_id = :id AND notes_special_instructions LIKE '%=%'", values={"id": lead_id})
            if name and placeholder:
                sets.append("parent_name = :pn"); vals["pn"] = name[:255]; filled.append("name")
            elif name and not _same(name, row.get("parent_name")):
                changes.append(f"name: {_show(row.get('parent_name'))} → {name}")
            take("ad_shown", (item.get("ad_shown") or "")[:500] or None, "ad shown",
                 lambda: (sets.extend(["ad_shown = :ad", "ad_id = COALESCE(ad_id, :adid)"]),
                          vals.update(ad=item["ad_shown"][:500], adid=item.get("ad_id"))))
            if source:
                cur_label = row.get("lead_source_platform") or row.get("lead_source")
                if not (row.get("lead_source") or "").strip():
                    sets += ["lead_source = :src", "lead_source_platform = :plat"]
                    vals.update(src=source, plat=platform); filled.append(f"source → {platform or source}")
                elif not _same(row.get("lead_source"), source) or (platform and row.get("lead_source_platform")
                                                                   and not _same(row.get("lead_source_platform"), platform)):
                    changes.append(f"source: {cur_label} → {platform or source}")
            take("referred_by", referred_by, "referred by")
            moved = None
            if (row.get("lead_source_detail") or "").startswith("Slack"):
                # A screenshot shows the exact first-message time: correct
                # the lead time if it's earlier than what the list gave us.
                cur = row.get("lead_generated_at")
                if item.get("generated_at") and (cur is None or item["generated_at"] < cur):
                    sets += ["lead_generated_at = :gen", "created_on = :gen"]; vals["gen"] = item["generated_at"]
                    moved = item["generated_at"]
            if sets:
                await database.execute(f"UPDATE leads SET {', '.join(sets)} WHERE lead_id = :id", values=vals)
            # A note that only names the source ("google", "insta ad") isn't news.
            just_source = bool(note) and len(re.findall(r"\w+", note)) <= 3 and bool(source_from_text(note)[0])
            new_note = bool(note) and not just_source and note.lower() not in (await _playbook_text(lead_id)).lower()
            if changes or new_note:
                parts = changes + ([f"note: {note}"] if new_note else [])
                await _append_change_note(lead_id, f"[{stamp} · {who} via Slack] " + "; ".join(parts))
            bits = [f"Posted again on Slack by {who}"]
            if filled:
                bits.append("filled in: " + ", ".join(filled))
            if changes:
                bits.append("different values added as a note: " + "; ".join(changes))
            if moved:
                bits.append("lead time set to " + moved.astimezone(IST).strftime("%d %b %Y, %I:%M %p"))
            if new_note:
                bits.append(f"Note: {note}")
            await _playbook_log(await _playbook_id(lead_id), "updated", " · ".join(bits))
            result = {"outcome": "updated" if (filled or moved or changes or new_note) else "duplicate",
                      "lead_id": lead_id, "name": vals.get("pn") or row.get("parent_name"), "phone": row.get("phone"),
                      "filled": filled, "changes": changes, "moved": moved,
                      "needs_source": not (source or (row.get("lead_source") or "").strip())}
        else:
            earlier = await _earlier_lead(phone)
            # "Slack · ..." marks bot-made leads (later screenshots may
            # correct their lead time; nothing else is overwritten).
            detail = "Slack" + (f" · {platform}" if platform else "") + (f" · @{handle}" if handle else "") \
                + (f" · Ad: {item['ad_shown']}" if item.get("ad_shown") else "")
            cols = {
                "parent_name": (name or (f"@{handle}" if handle else "New lead"))[:255],
                "phone": phone or "", "lead_origin": "sales_module", "lead_source": source,
                "lead_source_detail": detail[:255], "lead_source_platform": platform, "referred_by": referred_by,
                "ad_shown": (item.get("ad_shown") or None) and item["ad_shown"][:500], "ad_id": item.get("ad_id"),
                "lead_generated_at": gen, "created_on": gen, "status": "New", "is_booking": False, **fields,
            }
            names = ", ".join(cols)
            lead_id = await database.execute(
                f"INSERT INTO leads ({names}) VALUES ({', '.join(':' + k for k in cols)}) RETURNING lead_id", values=cols)
            pid = await database.execute(
                "INSERT INTO lead_sales_playbook (lead_id, created_by, notes_special_instructions, call_log) "
                "VALUES (:id, :by, :n, CAST(:cl AS JSONB)) RETURNING id",
                values={"id": lead_id, "by": actor, "n": note,
                        "cl": json.dumps([{**c, "by": c["by"] or who} for c in item["call_log"]]) if item.get("call_log") else None})
            label = platform or source
            earlier_txt = None
            if earlier:
                earlier_txt = (f"Earlier lead #{earlier['lead_id']} with this number "
                               f"(lead generated {earlier['last_touch'].astimezone(IST).strftime('%d %b %Y')}, "
                               f"{'booking' if earlier['is_booking'] else earlier['status']})")
                await _append_change_note(lead_id, f"[{stamp}] {earlier_txt}")
            await _playbook_log(pid, "created",
                                f"New {label + ' ' if label else ''}lead, posted on Slack by {who} ({how})"
                                + (f" · referred by {referred_by}" if referred_by else "") + (f" · {note}" if note else "")
                                + (f" · {earlier_txt}" if earlier_txt else ""))
            result = {"outcome": "created", "lead_id": lead_id, "name": cols["parent_name"], "phone": phone,
                      "platform": label, "generated_at": gen, "needs_source": not source,
                      "earlier": earlier["lead_id"] if earlier else None,
                      "filled": [DETAIL_LABELS[k] for k in fields if k in DETAIL_LABELS]
                                + (["first call"] if item.get("call_log") else [])}
    if result["outcome"] in ("created", "updated"):
        sheet_sync.schedule_sync(result["lead_id"])
    return result


async def _playbook_text(lead_id: int) -> str:
    r = await database.fetch_one(
        "SELECT COALESCE(notes_special_instructions, '') || ' ' || COALESCE(notes_changes_updates, '') AS t "
        "FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
    return (r["t"] if r else "") or ""


# ─── Slack plumbing ────────────────────────────────────────────────────────

def verify_slack(body: bytes, ts: Optional[str], sig: Optional[str]) -> bool:
    secret = settings.SLACK_SIGNING_SECRET
    if not (secret and ts and sig) or not ts.isdigit() or abs(time.time() - int(ts)) > 300:
        return False
    base = b"v0:" + ts.encode() + b":" + body
    mine = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mine, sig)


async def slack_api(method: str, **payload) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{SLACK_API}/{method}", json=payload,
                              headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"})
    d = r.json()
    if not d.get("ok"):
        logger.warning(f"Slack {method}: {d.get('error')}")
    return d


_names: Dict[str, str] = {}


async def slack_user_name(uid: str) -> str:
    if uid in _names:
        return _names[uid]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SLACK_API}/users.info", params={"user": uid},
                                 headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"})
        u = (r.json() or {}).get("user") or {}
        p = u.get("profile") or {}
        name = p.get("display_name") or p.get("real_name") or u.get("real_name") or u.get("name") or "Someone"
    except Exception:
        name = "Someone"
    _names[uid] = name
    return name


async def download_slack_file(f: Dict[str, Any]) -> Optional[Tuple[bytes, str]]:
    url = f.get("url_private_download") or f.get("url_private")
    mime = f.get("mimetype") or ""
    if not url or not mime.startswith("image/"):
        return None
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"})
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        logger.warning(f"Slack file download failed ({r.status_code}) — is the files:read scope added?")
        return None
    return r.content, mime if mime in ("image/png", "image/jpeg", "image/gif", "image/webp") else "image/png"


def _fmt_phone(p: Optional[str]) -> str:
    if p and len(p) == 10:
        return f"{p[:5]} {p[5:]}"
    return p or "no number"


def format_reply(results: List[Dict[str, Any]], errors: List[str]) -> str:
    site = settings.SITE_URL.rstrip("/")
    link = lambda r: f"<{site}/sales-leads.html?lead_id={r['lead_id']}|#{r['lead_id']}>"
    created = [r for r in results if r["outcome"] == "created"]
    updated = [r for r in results if r["outcome"] == "updated"]
    dup = [r for r in results if r["outcome"] == "duplicate"]
    skipped = [r for r in results if r["outcome"] == "skipped"]
    lines = []
    head = []
    if created: head.append(f"✅ {len(created)} added")
    if updated: head.append(f"✏️ {len(updated)} updated")
    if dup: head.append(f"↩️ {len(dup)} already in Leads")
    if skipped: head.append(f"⏭ {len(skipped)} skipped")
    if head:
        lines.append(" · ".join(head))
    for r in created:
        when = r["generated_at"].astimezone(IST).strftime("%d %b, %I:%M %p")
        extra = f" · filled: {', '.join(r['filled'])}" if r.get("filled") else ""
        lines.append(f"• {link(r)} {r['name']} · {_fmt_phone(r['phone'])} · {r['platform'] or 'source ❓'} · {when}{extra}"
                     + (f" · earlier lead #{r['earlier']}" if r.get('earlier') else ""))
    for r in updated:
        extra = ("filled " + ", ".join(r["filled"])) if r.get("filled") else ""
        if r.get("changes"):
            extra = (extra + "; " if extra else "") + "noted changes: " + "; ".join(r["changes"])
        if r.get("moved"):
            extra = (extra + ", " if extra else "") + "lead time → " + r["moved"].astimezone(IST).strftime("%d %b, %I:%M %p")
        lines.append(f"• {link(r)} {r['name']} — same lead (generated within {SAME_LEAD_DAYS} days): {extra or 'note added'}")
    for r in dup:
        lines.append(f"• {link(r)} {r['name']} — same lead (generated within {SAME_LEAD_DAYS} days), nothing new")
    for r in skipped:
        lines.append(f"• {r.get('name') or _fmt_phone(r.get('phone'))} — skipped ({r['why']})")
    lines += [f"⚠️ {e}" for e in errors]
    ask = [r for r in results if r.get("needs_source") and r.get("lead_id")]
    if ask:
        who = ", ".join(f"*{r.get('pos') or ''}* {r['name']}".replace("** ", "") for r in ask)
        lines.append(f"\n❓ *Lead source?* Not mentioned for: {who}.\n"
                     f"Reply in this thread — one word sets them all (e.g. `referral by Neha`), or one per line "
                     f"with the number or name (e.g. `2 stall`, `Saloni insta ad`).\nSources: {source_help()}")
    if not lines:
        lines.append("I couldn't find any leads in that. I look for lines like "
                     "`1. NAME (+919800000000) - source/note` under a heading like `19 Oct Leads:`, or chat screenshots.")
    return "\n".join(lines)


_seen: Dict[str, float] = {}

_SLACK_LINK = re.compile(r"<(?:tel:|mailto:|https?://)[^|>]*\|([^>]*)>|<(?:tel:|mailto:)([^>|]*)>|<(https?://[^>|]*)>")


def clean_slack_text(text: str) -> str:
    """Slack sends phone numbers / links as <tel:+9198...|+9198...> and
    escapes & < >. Turn it back into what the person typed."""
    t = _SLACK_LINK.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or "", text or "")
    t = re.sub(r"<[@#!][^>]*>", "", t)
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

LEAD_REF_RE = re.compile(r"#(\d{1,7})\b")
POS_RE = re.compile(r"^\s*(\d{1,2})\s*(?:[.)\-–:]|\s)")


async def handle_reply(ev: Dict[str, Any], post: Dict[str, Any]) -> None:
    """A reply in the thread of a lead post: set the lead source. One line
    with just a source = every lead in that post still missing one; lines
    naming a lead (#123, its number in the list, or its name) set that lead,
    even if it already has a source (a correction)."""
    channel, thread = ev.get("channel"), ev.get("thread_ts")
    who = await slack_user_name(ev.get("user") or "")
    items = post["items"]
    items = json.loads(items) if isinstance(items, str) else (items or [])
    by_id = {i["lead_id"]: i for i in items}
    lines = [l.strip() for l in clean_slack_text(ev.get("text") or "").splitlines() if l.strip()]
    plan: Dict[int, Tuple[str, Optional[str]]] = {}
    general = None
    for line in lines:
        src = source_from_text(line)
        if not src[0]:
            continue
        targets = [int(x) for x in LEAD_REF_RE.findall(line) if int(x) in by_id]
        m = POS_RE.match(line)
        if not targets and m:
            targets = [i["lead_id"] for i in items if i["pos"] == int(m.group(1))]
        if not targets:
            low = line.lower()
            targets = [i["lead_id"] for i in items
                       if (i.get("name") or "").strip() and re.sub(r"[^\w ]", "", i["name"]).strip().lower().split(" ")[0] in low
                       and len(re.sub(r"[^\w ]", "", i["name"]).strip()) >= 3]
        if targets:
            for t in targets:
                plan[t] = src
        else:
            general = src
    if general:
        missing = await database.fetch_all(
            "SELECT lead_id FROM leads WHERE lead_id = ANY(:ids) AND COALESCE(TRIM(lead_source), '') = ''",
            values={"ids": [i["lead_id"] for i in items]})
        for r in missing:
            plan.setdefault(r["lead_id"], general)
    if not plan:
        # Ordinary chat in the thread: only nudge while a source is still missing.
        missing = await database.fetch_val(
            "SELECT COUNT(*) FROM leads WHERE lead_id = ANY(:ids) AND COALESCE(TRIM(lead_source), '') = ''",
            values={"ids": [i["lead_id"] for i in items]})
        if not lines or not missing:
            return
        await slack_api("chat.postMessage", channel=channel, thread_ts=thread, unfurl_links=False,
                        text=f"I didn't catch a source there. Try e.g. `referral by Neha`, `2 stall` or `Saloni insta ad`.\n"
                             f"Sources: {source_help()}\nOnly these approved sources can be used — a new one needs Shruti's OK first.")
        return
    done = []
    for lead_id, (key, ref) in plan.items():
        source, platform = SOURCES[key]
        if not approved_source(source):
            continue
        sets = ["lead_source = :s", "lead_source_platform = :p"]
        vals = {"s": source, "p": platform, "id": lead_id}
        if ref:
            sets.append("referred_by = :rb"); vals["rb"] = ref[:255]
        await database.execute(f"UPDATE leads SET {', '.join(sets)} WHERE lead_id = :id", values=vals)
        label = platform or source
        await _playbook_log(await _playbook_id(lead_id), "updated",
                            f"Lead source set to {label}" + (f" (referred by {ref})" if ref else "") + f" by {who} on Slack")
        sheet_sync.schedule_sync(lead_id)
        done.append(f"#{lead_id} {by_id.get(lead_id, {}).get('name') or ''} → {label}" + (f" (by {ref})" if ref else ""))
    left = await database.fetch_all(
        "SELECT lead_id, parent_name FROM leads WHERE lead_id = ANY(:ids) AND COALESCE(TRIM(lead_source), '') = ''",
        values={"ids": [i["lead_id"] for i in items]})
    msg = "✅ Source set: " + "; ".join(done)
    if left:
        msg += "\n❓ Still missing: " + ", ".join(f"#{r['lead_id']} {r['parent_name']}" for r in left)
    await slack_api("chat.postMessage", channel=channel, thread_ts=thread, text=msg, unfurl_links=False)


async def handle_message(ev: Dict[str, Any]) -> None:
    channel, ts = ev.get("channel"), ev.get("ts")
    text = clean_slack_text(ev.get("text") or "")
    posted_at = datetime.fromtimestamp(float(ts), tz=timezone.utc) if ts else datetime.now(timezone.utc)
    who = await slack_user_name(ev.get("user") or "")
    results, errors = [], []
    try:
        kv = parse_kv_records(text, posted_at)
        items = [(i, "sheet row") for i in kv] if kv else [(i, "text list") for i in parse_lead_list(text, posted_at)]
        files = [f for f in (ev.get("files") or []) if (f.get("mimetype") or "").startswith("image/")]
        if files:
            images = [x for x in [await download_slack_file(f) for f in files] if x]
            if not images:
                errors.append("I couldn't open the screenshot(s) — the Slack app needs the files:read permission.")
            else:
                try:
                    shot = await read_screenshots(images, text, posted_at.astimezone(IST).date())
                    msg_src = source_from_text(text)
                    for l in shot:
                        it = _clean_screenshot_lead(l, posted_at)
                        if not it.get("source") and msg_src[0]:
                            it["source"], it["referred_by"] = msg_src
                        items.append((it, "screenshot"))
                    if not shot:
                        errors.append("I couldn't see a customer in the screenshot(s).")
                except Exception as exc:
                    logger.exception("Slack leads: screenshot reading failed")
                    errors.append(str(exc)[:300])
        for pos, (item, how) in enumerate(items, start=1):
            try:
                r = await intake(item, who, how)
                r["pos"] = pos
                results.append(r)
            except Exception as exc:
                logger.exception("Slack leads: couldn't save a lead")
                errors.append(f"Couldn't save {item.get('name') or item.get('phone')}: {str(exc)[:200]}")
        if not items and not files and not re.search(r"\d{10}|lead", text, re.I):
            return   # ordinary chat in the channel — stay quiet
        posted = [{"pos": r["pos"], "lead_id": r["lead_id"], "name": r.get("name")} for r in results if r.get("lead_id")]
        if posted:
            await database.execute(
                "INSERT INTO slack_lead_posts (channel, ts, posted_by, items) VALUES (:c, :t, :w, CAST(:i AS JSONB)) "
                "ON CONFLICT (channel, ts) DO UPDATE SET items = EXCLUDED.items",
                values={"c": channel, "t": ts, "w": who, "i": json.dumps(posted)})
        await _log_call("slack.message", None, results[0].get("lead_id") if results else None,
                        "slack", f"{who}: {len(results)} result(s), {len(errors)} error(s)",
                        {"text": text[:4000], "files": len(ev.get("files") or []), "results": [
                            {k: (str(v) if isinstance(v, datetime) else v) for k, v in r.items()} for r in results]})
    except Exception as exc:
        logger.exception("Slack leads: failed")
        errors.append(f"Something went wrong: {str(exc)[:200]}")
    # Long batches (many sheet rows) -> several replies, so none is cut off.
    chunk, size = [], 0
    for line in format_reply(results, errors).split("\n"):
        if chunk and size + len(line) > 3500:
            await slack_api("chat.postMessage", channel=channel, thread_ts=ts, text="\n".join(chunk),
                            unfurl_links=False, unfurl_media=False)
            chunk, size = [], 0
        chunk.append(line); size += len(line) + 1
    if chunk:
        await slack_api("chat.postMessage", channel=channel, thread_ts=ts, text="\n".join(chunk),
                        unfurl_links=False, unfurl_media=False)


@router.post("/integrations/slack/events")
async def slack_events(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"detail": "bad request"}, status_code=400)
    ok = verify_slack(body, request.headers.get("x-slack-request-timestamp"),
                      request.headers.get("x-slack-signature"))
    # Slack checks the URL once when the app is set up; answering its
    # challenge is harmless, so it works even before the secret is saved.
    if payload.get("type") == "url_verification" and (ok or not settings.SLACK_SIGNING_SECRET):
        return PlainTextResponse(payload.get("challenge", ""))
    if not settings.SLACK_SIGNING_SECRET or not settings.SLACK_BOT_TOKEN:
        return JSONResponse({"detail": "Slack lead bot is not configured."}, status_code=503)
    if not ok:
        return JSONResponse({"detail": "Bad signature."}, status_code=401)
    if request.headers.get("x-slack-retry-num"):
        return {"ok": True}   # we already got it; Slack retries if we were slow
    ev = payload.get("event") or {}
    eid = payload.get("event_id") or ev.get("ts") or ""
    now = time.time()
    for k in [k for k, t in _seen.items() if now - t > 3600]:
        _seen.pop(k, None)
    if eid in _seen:
        return {"ok": True}
    _seen[eid] = now
    if ev.get("type") != "message" or ev.get("bot_id") or ev.get("subtype") not in (None, "file_share"):
        return {"ok": True}
    # On-demand business summary (2026-10-20, per Shruti): "summary",
    # "summary yesterday", "summary 19 Oct" in any channel the bot is in
    # (meant for #business-performance) -> the daily update, as a thread reply.
    from routers import daily_report
    sday = daily_report.parse_summary_request(ev.get("text") or "")
    if sday is not None:
        asyncio.get_running_loop().create_task(_safe(daily_report.reply_in_thread(ev.get("channel"), ev.get("ts"), sday)))
        return {"ok": True}
    # #vendor-contacts (2026-10-28): visiting cards / contacts -> vendor master.
    if settings.SLACK_VENDOR_CHANNEL and ev.get("channel") == settings.SLACK_VENDOR_CHANNEL:
        from routers import slack_vendors
        if ev.get("thread_ts") and ev.get("thread_ts") != ev.get("ts"):
            post = await database.fetch_one("SELECT * FROM slack_vendor_posts WHERE channel = :c AND ts = :t",
                                            values={"c": ev.get("channel"), "t": ev.get("thread_ts")})
            if post:
                asyncio.get_running_loop().create_task(_safe(slack_vendors.handle_reply(ev, dict(post))))
            return {"ok": True}
        asyncio.get_running_loop().create_task(_safe(slack_vendors.handle_message(ev)))
        return {"ok": True}
    if settings.SLACK_LEADS_CHANNEL and ev.get("channel") != settings.SLACK_LEADS_CHANNEL:
        return {"ok": True}
    if ev.get("thread_ts") and ev.get("thread_ts") != ev.get("ts"):
        # A reply in a thread: only the answer to "Lead source?" on one of
        # our lead posts means anything; other thread chat is left alone.
        post = await database.fetch_one("SELECT * FROM slack_lead_posts WHERE channel = :c AND ts = :t",
                                        values={"c": ev.get("channel"), "t": ev.get("thread_ts")})
        if post:
            asyncio.get_running_loop().create_task(_safe(handle_reply(ev, dict(post))))
        return {"ok": True}
    # Slack wants an answer within 3 seconds; reading screenshots takes longer.
    asyncio.get_running_loop().create_task(_safe(handle_message(ev)))
    return {"ok": True}


async def _safe(coro):
    try:
        await coro
    except Exception:
        logger.exception("Slack leads: background task failed")
