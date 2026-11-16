"""
Slack packing bot (2026-11-16, per Shruti).

  "help me create a slack bot for packing ... our packing list should be named
   accordingly [Ishani F8 Ghatkopar]. 1 event will have only 1 packing list ...
   we should be able to update/create the packing list from slack as well. so
   i'll write ishani f6 ghatkopar or booking id or ishani 22nd nov to help you
   identify, and then list of items we need to add - you then update it in the
   list"

Channel: settings.SLACK_PACKING_CHANNEL (the channel ID). Same Slack app as
the lead bot (routers/slack_leads.py routes the events here).

POST in the channel — first line says which party, the lines under it are
the items:

    ishani f8 ghatkopar          <- or  #1267  /  1267  /  ishani 22nd nov
    Decor:                       <- optional section header (as in packaging.html)
    - foil balloon 8
    - cutouts x2                 <- "x2" at the end = quantity
    Branding:
    - tent card
    remove caution tape          <- takes an item off

  or on one line:   ishani 22 nov: balloons, cones, tape

The bot finds the booking, opens its packing list (or makes it, named the
standard way — event_naming.py), adds the items (an item already on the list
is not added twice; items with no header go under "Items") and replies in the
thread with what changed, how much is packed and the staff link.
  * Not sure which party it is -> it lists the matches; reply with the number.
  * REPLY in the thread later with more items (or "remove ..."), no need to
    name the party again.
  * "show ishani f8" / "show 1267" -> the list as it stands.
  * "help" -> how to use it.
Adding items to a list already marked packed opens it again (submitted
cleared), so the team packs the new things and submits again.
"""
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from database import database
from event_naming import event_name, area_of, gender_letter
from routers.packaging import (
    BOOKING_COLS, ItemIn, SectionIn, add_items, get_or_create_for_booking, list_for_booking,
    remove_items, _summary,
)
from routers.slack_leads import slack_api, slack_user_name, clean_slack_text, IST

logger = logging.getLogger(__name__)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

HELP = (
    "*📦 Packing bot* — first line says which party, then the items:\n"
    "```ishani f8 ghatkopar\nDecor:\n- foil balloon 8\n- cutouts x2\nremove caution tape```\n"
    "Which party: `ishani f8 ghatkopar`, `ishani 22 nov` or the booking ID `#1267`.\n"
    "One line works too: `ishani 22 nov: balloons, cones, tape`\n"
    "• `x2` at the end of an item = quantity · a line ending in `:` = section header\n"
    "• `remove <item>` takes an item off · `show ishani f8` shows the list\n"
    "• Reply in my thread to add more to the same list.\n"
    "New lists are named the standard way, e.g. *Ishani F8 Ghatkopar*. One list per party."
)


# ─── reading the message ───────────────────────────────────────────────────

def _year_near(month: int, day: int, today: date) -> Optional[date]:
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best


def parse_date(text: str, today: date) -> Tuple[Optional[date], str]:
    """A date in the reference ('22nd nov', 'nov 22', '22/11', 'tomorrow')
    and the text with it taken out."""
    t = text
    pats = [
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?{_MON}(?:\s*(\d{{4}}))?", lambda m: (MONTHS[m.group(2)[:3]], int(m.group(1)), m.group(3))),
        (rf"\b{_MON}\s*(\d{{1,2}})(?:st|nd|rd|th)?\b(?:\s*(\d{{4}}))?", lambda m: (MONTHS[m.group(1)[:3]], int(m.group(2)), m.group(3))),
        (r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", lambda m: (int(m.group(2)), int(m.group(1)), m.group(3))),
    ]
    for rx, get in pats:
        m = re.search(rx, t, re.I)
        if not m:
            continue
        mo, dy, yr = get(m)
        try:
            if yr:
                y = int(yr); y = y + 2000 if y < 100 else y
                d = date(y, mo, dy)
            else:
                d = _year_near(mo, dy, today)
        except ValueError:
            d = None
        if d:
            return d, (t[:m.start()] + " " + t[m.end():]).strip()
    for word, delta in (("today", 0), ("tomorrow", 1), ("tmrw", 1), ("tmr", 1)):
        m = re.search(rf"\b{word}\b", t, re.I)
        if m:
            return today + timedelta(days=delta), (t[:m.start()] + " " + t[m.end():]).strip()
    return None, t


def parse_ref(line: str, today: date) -> Dict[str, Any]:
    """'ishani f6 ghatkopar' / '#1267' / 'ishani 22nd nov' -> what to look for."""
    raw = re.sub(r"^\s*(?:pack(?:ing)?(?:\s+list)?|list|for|show|booking)\s*[:\-]?\s+", "", line.strip(), flags=re.I)
    m = re.fullmatch(r"\s*(?:booking\s*|id\s*|#)?\s*#?(\d{1,7})\s*", raw, re.I)
    if m:
        return {"lead_id": int(m.group(1))}
    m = re.search(r"(?:booking\s*(?:id)?\s*|#)(\d{1,7})\b", raw, re.I)
    if m:
        return {"lead_id": int(m.group(1))}
    d, rest = parse_date(raw, today)
    gender = age = None
    m = re.search(r"\b([mfbg])\s?(\d{1,2})\b|\b(\d{1,2})\s?([mfbg])\b", rest, re.I)
    if m:
        letter = (m.group(1) or m.group(4)).lower()
        gender = "F" if letter in "fg" else "M"
        age = int(m.group(2) or m.group(3))
        rest = (rest[:m.start()] + " " + rest[m.end():])
    else:
        m = re.search(r"\b(\d{1,2})\s*(?:yrs?|years?|th)?\b", rest, re.I)
        if m and int(m.group(1)) <= 18:
            age = int(m.group(1)); rest = rest[:m.start()] + " " + rest[m.end():]
    words = [w for w in re.split(r"[\s,'’]+", rest) if w and re.search(r"[a-zA-Z]", w)
             and w.lower() not in ("s", "party", "birthday", "bday", "the", "at", "in", "on")]
    return {"name": words[0].lower() if words else None, "place": " ".join(words[1:]).lower() or None,
            "date": d, "gender": gender, "age": age}


_QTY = re.compile(r"\s*(?:[x×*]\s*(\d{1,4})|[-–(]\s*(\d{1,4})\s*(?:pcs?|nos?|pieces?)?\)?|(\d{1,4})\s*(?:pcs|nos|pieces))\s*$", re.I)


def _item(text: str) -> ItemIn:
    t = text.strip().rstrip(".").strip()
    m = _QTY.search(t)
    qty = None
    if m and m.start() > 0:
        qty = int(m.group(1) or m.group(2) or m.group(3))
        t = t[:m.start()].strip(" -–,")
    return ItemIn(text=t, qty=qty or None)


_REMOVE = re.compile(r"^\s*(?:[-•▪*]\s*)?(?:remove|delete|drop|del|cancel|no need(?: for)?)\s*[:\-]?\s+(.+)$", re.I)


def parse_items(lines: List[str], split_commas: bool = False) -> Tuple[List[SectionIn], List[str]]:
    """Same shapes as packaging.html's paste box: '*Decor*' or 'Decor:' starts
    a section, '- x' / '1. x' / plain lines are items, 'Host: Sunny' is a
    header with one item. 'remove x' lines are collected separately."""
    sections: List[SectionIn] = []
    removes: List[str] = []
    cur: Optional[SectionIn] = None

    def push(text: str):
        nonlocal cur
        parts = [p for p in re.split(r"\s*,\s*", text)] if split_commas else [text]
        for p in parts:
            if not p.strip():
                continue
            if cur is None:
                cur = SectionIn(header="", items=[]); sections.append(cur)
            cur.items.append(_item(p))

    for line in lines:
        t = line.strip().replace("✅", "").strip()
        if not t:
            continue
        m = _REMOVE.match(t)
        if m:
            removes += [x.strip() for x in re.split(r"\s*,\s*", m.group(1)) if x.strip()]
            continue
        if (m := re.fullmatch(r"\*(.+)\*", t)) or (m := re.fullmatch(r"([A-Za-z][\w /&'-]{1,40}):", t)):
            cur = SectionIn(header=m.group(1).strip(), items=[]); sections.append(cur)
            continue
        if re.match(r"^\d+_\S", t):
            push(t); continue
        if (m := re.match(r"^[-•▪◦]\s*(.+)$", t)) or (m := re.match(r"^\d+[.)]\s*(.+)$", t)):
            push(m.group(1)); continue
        if (m := re.fullmatch(r"([A-Za-z][\w /&']{1,20}):\s+(\S.{0,40})", t)) and not split_commas:
            cur = SectionIn(header=m.group(1).strip(), items=[]); sections.append(cur)
            push(m.group(2)); continue
        push(t)
    return [s for s in sections if s.items], removes


def split_message(text: str) -> Tuple[str, List[str], bool]:
    """(reference line, item lines, one-line form?)"""
    lines = [l for l in (text or "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", [], False
    first = lines[0].strip()
    rest = lines[1:]
    # "ishani 22 nov: balloons, cones" / "#1267 - balloons, cones"
    m = re.match(r"^(.{2,60}?)\s*(?::|\s[-–—]\s|=>|->)\s*(.+)$", first)
    if m and not rest and not re.fullmatch(r"\d{1,2}", m.group(2).strip()):
        return m.group(1).strip(), [m.group(2)], True
    if m and rest and m.group(2).strip() and not re.search(r"\d{1,2}(:\d{2})", first):
        return m.group(1).strip(), [m.group(2)] + rest, False
    return first.rstrip(":").strip(), rest, False


# ─── finding the booking ───────────────────────────────────────────────────

def _first_names(v) -> List[str]:
    return [p.strip().split()[0].lower() for p in re.split(r"\s*(?:,|/|&|\band\b)\s*", str(v or "")) if p.strip()]


def score(b, ref: Dict[str, Any], today: date) -> Optional[float]:
    """How well booking b fits the reference, or None if it doesn't."""
    name = ref.get("name")
    names = _first_names(b["child_names"])
    if name:
        if name in names:
            s = 10.0
        elif any(n.startswith(name) or (len(name) >= 4 and name.startswith(n) and len(n) >= 4) for n in names):
            s = 7.0
        elif name == (str(b["parent_name"] or "").split() or [""])[0].lower():
            s = 5.0
        else:
            return None
    else:
        s = 0.0
    ed = b["event_date"]
    if ref.get("date"):
        if ed != ref["date"]:
            return None
        s += 6
    if ref.get("gender"):
        genders = [gender_letter(g) for g in re.split(r"\s*,\s*", str(b["child_genders"] or ""))]
        s += 2 if ref["gender"] in genders else (-2 if any(genders) else 0)
    if ref.get("age") is not None:
        ages = [int(a) for a in re.findall(r"\d{1,2}", str(b["child_ages"] or ""))]
        if ref["age"] in ages:
            s += 3
        elif any(abs(a - ref["age"]) <= 2 for a in ages):
            s += 0.5   # "f6" for an 8-year-old: a typo or the age turning, still likely
    if ref.get("place"):
        place = ref["place"]
        where = " ".join([str(b["venue"] or ""), str(b["city"] or ""), area_of(b["venue"], b["city"])]).lower()
        if area_of(place) and area_of(place).lower() == area_of(b["venue"], b["city"]).lower():
            s += 4
        elif all(w in where for w in place.split()):
            s += 3.5
        elif any(len(w) >= 4 and w in where for w in place.split()):
            s += 1.5
        else:
            s -= 2
    # Upcoming parties first; a party long gone is unlikely to be packed.
    if ed:
        days = (ed - today).days
        if days >= -1:
            s += max(0.0, 1.5 - days / 30)
        elif not ref.get("date"):
            s -= 2 if days >= -7 else 5
    return s


async def find_bookings(ref: Dict[str, Any], today: date) -> List[Any]:
    """Best matches first."""
    if ref.get("lead_id"):
        b = await database.fetch_one(f"SELECT {BOOKING_COLS} FROM leads WHERE lead_id = :l", values={"l": ref["lead_id"]})
        return [b] if b else []
    if not ref.get("name") and not ref.get("date"):
        return []
    where, vals = ["is_booking = TRUE", "COALESCE(status, '') <> 'Cancelled'"], {}
    if ref.get("name"):
        where.append("(child_names ILIKE :q OR parent_name ILIKE :q)"); vals["q"] = f"%{ref['name'][:4]}%"
    if ref.get("date"):
        where.append("event_date = :d"); vals["d"] = ref["date"]
    rows = await database.fetch_all(
        f"SELECT {BOOKING_COLS} FROM leads WHERE {' AND '.join(where)} ORDER BY event_date DESC NULLS LAST LIMIT 200",
        values=vals)
    scored = [(score(r, ref, today), r) for r in rows]
    scored = [(s, r) for s, r in scored if s is not None]
    scored.sort(key=lambda x: -x[0])
    # Drop matches far weaker than the best (e.g. last year's party).
    if scored:
        scored = [(s, r) for s, r in scored if scored[0][0] - s <= 6]
    out = [r for s, r in scored]
    # One clear winner -> just that one.
    if len(scored) >= 2 and scored[0][0] - scored[1][0] >= 2.5:
        return out[:1]
    return out[:6]


# ─── replies ──────────────────────────────────────────────────────────────

def _site() -> str:
    return settings.SITE_URL.rstrip("/")


def _when(b) -> str:
    d = b["event_date"]
    return d.strftime("%a %d %b") if d else "date not set"


def _booking_line(b) -> str:
    return f"{event_name(b)} · #{b['lead_id']} · {_when(b)}" + (f" · {b['venue']}" if b["venue"] else "")


async def _post(channel: str, thread: str, text: str) -> Dict[str, Any]:
    return await slack_api("chat.postMessage", channel=channel, thread_ts=thread, text=text[:3900],
                           unfurl_links=False, unfurl_media=False)


async def _remember(channel: str, ts: str, who: str, list_id: Optional[int], pending: Optional[dict]) -> None:
    await database.execute(
        """INSERT INTO slack_packing_posts (channel, ts, posted_by, list_id, pending)
           VALUES (:c, :t, :w, :l, CAST(:p AS JSONB))
           ON CONFLICT (channel, ts) DO UPDATE SET list_id = EXCLUDED.list_id, pending = EXCLUDED.pending""",
        values={"c": channel, "t": ts, "w": who, "l": list_id, "p": json.dumps(pending) if pending else None})


async def _list_text(lst, b=None, show_items: bool = False) -> str:
    sm = await _summary(lst)
    pr = sm["progress"]
    staff = f"{_site()}{sm['share_url']}"
    edit = f"{_site()}/packaging.html?lead_id={lst['lead_id']}" if lst["lead_id"] else f"{_site()}/packaging.html"
    state = (f"✅ packed by {sm['submitted_by']}" if sm["submitted_at"] else f"{pr['checked']}/{pr['total']} packed")
    lines = [f"📦 *{lst['title']}*" + (f" · booking #{lst['lead_id']} · {_when(b)}" if b else ""),
             f"{state} · <{staff}|Staff link (for packing)> · <{edit}|Edit list>"]
    if show_items:
        secs = await database.fetch_all(
            "SELECT * FROM packaging_sections WHERE packaging_list_id = :l ORDER BY sort_order, id", values={"l": lst["id"]})
        for s in secs:
            items = await database.fetch_all(
                "SELECT * FROM packaging_items WHERE section_id = :s ORDER BY sort_order, id", values={"s": s["id"]})
            if not items:
                continue
            lines.append(f"*{s['header']}*")
            lines += [f"{'✅' if i['checked'] else '▫️'} {i['text']}" + (f" x{i['qty']}" if i["qty"] else "") for i in items]
        if not secs:
            lines.append("_No items yet._")
    return "\n".join(lines)


async def apply(channel: str, thread: str, who: str, b, sections: List[SectionIn], removes: List[str],
                show: bool = False) -> None:
    """Open/make the booking's list, apply the changes, reply."""
    lst, created = await get_or_create_for_booking(b, f"{who} (Slack)")
    was_submitted = lst["submitted_at"]
    res = await add_items(lst["id"], sections) if sections else {"added": [], "skipped": [], "qty": []}
    rem = await remove_items(lst["id"], removes) if removes else {"removed": [], "not_found": []}
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE id = :id", values={"id": lst["id"]})
    out = []
    if created:
        out.append("🆕 New packing list made for this party.")
    if res["added"]:
        out.append(f"✅ Added {len(res['added'])}: " + ", ".join(res["added"]))
    if res["qty"]:
        out.append("🔢 Quantity changed: " + ", ".join(res["qty"]))
    if res["skipped"]:
        out.append("↩️ Already on the list: " + ", ".join(res["skipped"]))
    if rem["removed"]:
        out.append("🗑 Removed: " + ", ".join(rem["removed"]))
    if rem["not_found"]:
        out.append("❓ Not on the list: " + ", ".join(rem["not_found"]))
    if was_submitted and (res["added"] or res["qty"]):
        out.append("⚠️ This list was already marked packed — it's open again so the new items get packed.")
    if not (sections or removes) and not created and not show:
        show = True
    text = await _list_text(lst, b, show_items=show) + ("\n" + "\n".join(out) if out else "")
    if created and not sections:
        text += "\nReply in this thread with the items to add."
    await _post(channel, thread, text)
    await _remember(channel, thread, who, lst["id"], None)


async def _ask_which(channel: str, ts: str, who: str, matches: List[Any], body: str, show: bool,
                     one_line: bool = False) -> None:
    lines = ["🤔 Which party is it? Reply with the number (or the booking ID):"]
    lines += [f"*{i}.* {_booking_line(b)}" for i, b in enumerate(matches, start=1)]
    await _post(channel, ts, "\n".join(lines))
    await _remember(channel, ts, who, None, {"candidates": [b["lead_id"] for b in matches], "body": body, "show": show,
                                          "one_line": one_line})


# ─── entry points (called from routers/slack_leads.py) ────────────────────

async def handle_message(ev: Dict[str, Any]) -> None:
    channel, ts = ev.get("channel"), ev.get("ts")
    text = clean_slack_text(ev.get("text") or "").strip()
    if not text:
        return
    who = await slack_user_name(ev.get("user") or "")
    today = datetime.now(IST).date()
    if re.fullmatch(r"\s*(help|\?|how)\s*", text, re.I):
        await _post(channel, ts, HELP); return
    show = bool(re.match(r"^\s*(show|view|see|status)\b", text, re.I))
    if show:
        text = re.sub(r"^\s*(show|view|see|status)\s*(?:me\s+)?(?:the\s+)?(?:packing\s+)?(?:list\s+)?(?:for\s+)?", "", text, flags=re.I)
    ref_line, item_lines, one_line = split_message(text)
    ref = parse_ref(ref_line, today)
    if not ref.get("lead_id") and not ref.get("name") and not ref.get("date"):
        await _post(channel, ts, "I couldn't tell which party this is for.\n\n" + HELP); return
    sections, removes = parse_items(item_lines, split_commas=one_line)
    body = "\n".join(item_lines) if not one_line else item_lines[0]
    matches = await find_bookings(ref, today)
    if not matches:
        what = f"booking #{ref['lead_id']}" if ref.get("lead_id") else f"“{ref_line}”"
        await _post(channel, ts, f"❓ I couldn't find a booking for {what}. Try the booking ID, e.g. `#1267`, "
                                 f"or the name with the party date, e.g. `ishani 22 nov`.")
        await _remember(channel, ts, who, None, {"candidates": [], "body": body, "show": show, "one_line": one_line})
        return
    if len(matches) > 1:
        await _ask_which(channel, ts, who, matches, body, show, one_line); return
    b = matches[0]
    if ref.get("lead_id") and not b["is_booking"]:
        await _post(channel, ts, f"#{b['lead_id']} is still a lead, not a booking — packing lists are for bookings."); return
    await apply(channel, ts, who, b, sections, removes, show=show)


async def handle_thread(ev: Dict[str, Any], post: Dict[str, Any]) -> None:
    """A reply in the thread of one of our answers."""
    channel, thread = ev.get("channel"), ev.get("thread_ts")
    text = clean_slack_text(ev.get("text") or "").strip()
    if not text:
        return
    who = await slack_user_name(ev.get("user") or "")
    pending = post.get("pending")
    if isinstance(pending, str):
        pending = json.loads(pending)
    if pending is not None and not post.get("list_id"):
        cands = pending.get("candidates") or []
        pick = None
        m = re.fullmatch(r"\s*#?\s*(\d{1,7})\s*\.?\s*", text)
        if m:
            n = int(m.group(1))
            if 1 <= n <= len(cands):
                pick = cands[n - 1]
            else:
                pick = n   # a booking ID
        else:
            # They named it again ("ishani 22 nov") — try that.
            matches = await find_bookings(parse_ref(text.splitlines()[0], datetime.now(IST).date()),
                                          datetime.now(IST).date())
            if len(matches) == 1:
                pick = matches[0]["lead_id"]
            elif matches:
                await _ask_which(channel, thread, who, matches, pending.get("body") or "", pending.get("show", False),
                                 bool(pending.get("one_line")))
                return
        if not pick:
            await _post(channel, thread, "Reply with the number from the list, or the booking ID (e.g. `#1267`).")
            return
        b = await database.fetch_one(f"SELECT {BOOKING_COLS} FROM leads WHERE lead_id = :l", values={"l": pick})
        if not b or not b["is_booking"]:
            await _post(channel, thread, f"❓ #{pick} isn't a booking. Reply with the number or a booking ID.")
            return
        sections, removes = parse_items((pending.get("body") or "").splitlines(),
                                        split_commas=bool(pending.get("one_line")))
        await apply(channel, thread, who, b, sections, removes, show=bool(pending.get("show")))
        return
    if not post.get("list_id"):
        return
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE id = :id", values={"id": post["list_id"]})
    if not lst:
        await _post(channel, thread, "That packing list has been deleted."); return
    b = await database.fetch_one(f"SELECT {BOOKING_COLS} FROM leads WHERE lead_id = :l", values={"l": lst["lead_id"]}) if lst["lead_id"] else None
    if re.fullmatch(r"\s*(show|view|list|status)\s*", text, re.I):
        await _post(channel, thread, await _list_text(lst, b, show_items=True)); return
    lines = text.splitlines()
    one = len(lines) == 1 and "," in lines[0] and not _REMOVE.match(lines[0])
    sections, removes = parse_items(lines, split_commas=one)
    if not sections and not removes:
        return
    if b:
        await apply(channel, thread, who, b, sections, removes)
    else:   # an old list with no booking
        res = await add_items(lst["id"], sections) if sections else {"added": []}
        rem = await remove_items(lst["id"], removes) if removes else {"removed": []}
        await _post(channel, thread, await _list_text(lst) + "\n" + "\n".join(filter(None, [
            ("✅ Added: " + ", ".join(res["added"])) if res.get("added") else "",
            ("🗑 Removed: " + ", ".join(rem["removed"])) if rem.get("removed") else ""])))
