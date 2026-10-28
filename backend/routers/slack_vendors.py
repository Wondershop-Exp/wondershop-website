"""
Slack vendor contacts bot (2026-10-28, per Shruti).

  "for some cases, I would like to save some contacts in the vendor master and
  the person might not be willing yet to fill all the details. these can be
  future vendors or contacts I want to save. For these people, create a slack
  channel where i can input them and you create them in the vendor master.
  also, let me add a photo of their card and pre-fill information. give a
  comments box where I can input my thoughts so that later on I can fetch them."

  Channel: #vendor-contacts (settings.SLACK_VENDOR_CHANNEL). The same Slack app
  as the lead bot (routers/slack_leads.py) receives the events.

  1. POST a contact: a photo of their visiting card and/or a few lines of text
     ("Riya Balloons, decorator, 98200 11111, Andheri. Good work at the Juhu
     party, pricey"). Claude reads the card + text and pulls out the business
     name, contact person, numbers, email, website, Instagram, address and what
     they deal in. Anything that is the poster's own opinion goes into the
     partner's NOTES, not into the details.
  2. The bot saves it in the vendor master as an inactive partner marked
     "Saved contact" (onboarding_source = 'slack_contact'), keeps the card
     photo with the partner's files, and replies in the thread with what it
     saved, what is still missing and a link to the partner.
     A number that is already in the vendor master is not added twice: the
     note and card go onto that partner instead.
  3. REPLY in the thread any time later -> the reply is added to that partner's
     notes (dated, with who wrote it).
  4. FETCH later: type "find riya" / "find decorator andheri" in the channel ->
     the bot lists matching partners with their notes. Notes also show (and can
     be added) in the Partners tab of the admin panel, and the Partners search
     looks through them.

Needs SLACK_SIGNING_SECRET + SLACK_BOT_TOKEN (same app as the lead bot, with
files:read), and ANTHROPIC_API_KEY to read card photos (text works without it).
"""
import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings
from database import database
from routers.slack_leads import (
    slack_api, slack_user_name, download_slack_file, clean_slack_text, _shrink, IST,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_MOBILE = "1111111111"   # same placeholder as migrations/052
# Same list as the admin Partners tab (DEALS_OPTIONS in admin.html).
DEALS = ['Event Volunteer', 'Wondershop Team Member', 'Carnival Stalls & Mascots', 'Photographer', 'Decorator',
         'Baker', 'Stationery Store', 'Personalization Store', 'Gift Shop', 'Packaging Store', 'Art & Craft Store',
         'Host', 'DJ', 'Magician', 'Bubble Show Artist', 'Science Show Artist', 'Puppet Show Artist',
         'Other Entertainer', 'Others']

PROMPT = """You are helping Wondershop Experiences (a kids' birthday party company in Mumbai) save supplier contacts. The founder posted a message in Slack, possibly with photos of visiting cards. Today is {today}.

Her message text was: {text!r}

Pull out each separate business / person she is saving (usually one; a photo with several cards = several). For each, give:
- business_name: the company or brand name (or the person's name if there is no company)
- contact_person: the person's name, if different from the business name
- phone: main mobile number, 10 digits (Indian numbers; drop +91 / 0)
- alternate_phone: a second number, if any
- email, website, instagram (handle without @)
- address, locality (area, e.g. "Andheri West"), city, pincode
- deals_in: exactly one of {deals}, whichever fits best ("Others" if none fits)
- deals_in_other: if deals_in is "Others", a few words on what they do
- services: short list of what they offer, from the card or the text
- notes: ONLY her own comments, opinions and context from the message text (e.g. "met at the Juhu party, good quality, a bit pricey, call in Dec"). Do NOT repeat contact details here, and never put card text here.

Only report what is actually written. Never guess a phone number or email. Use null for anything not given.

Reply with ONLY a JSON object: {{"contacts": [ ... ]}}"""


def _digits10(v) -> Optional[str]:
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d if re.fullmatch(r"[6-9]\d{9}", d) else None


def _s(v, n: int = 255) -> Optional[str]:
    v = re.sub(r"\s+", " ", str(v)).strip() if v not in (None, "") else ""
    return v[:n] or None


async def _ask_claude(images: List[Tuple[bytes, str]], text: str) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = []
    for data, mime in images[:6]:
        data, mime = _shrink(data, mime)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": PROMPT.format(
        today=datetime.now(IST).date().isoformat(), text=text or "", deals=", ".join(DEALS))})
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
    out = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("Couldn't read the contact details (no data came back).")
    return [c for c in (json.loads(m.group(0)).get("contacts") or []) if isinstance(c, dict)]


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s-]{8,15}\d)")


def _parse_plain(text: str) -> List[Dict[str, Any]]:
    """Without the Claude key: first line = name, numbers / email picked out,
    everything else kept as the note."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    phones = [p for p in (_digits10(x) for x in PHONE_RE.findall(text)) if p]
    email = (EMAIL_RE.search(text) or [None])[0]
    name = re.split(r"[,–-]|\d", lines[0])[0].strip() or lines[0][:60]
    deals = next((d for d in DEALS if d.lower() in text.lower()), None)
    return [{"business_name": name, "phone": phones[0] if phones else None,
             "alternate_phone": phones[1] if len(phones) > 1 else None, "email": email,
             "deals_in": deals, "notes": text}]


def _clean(c: Dict[str, Any]) -> Dict[str, Any]:
    deals = _s(c.get("deals_in"), 60)
    if deals and deals not in DEALS:
        deals = next((d for d in DEALS if d.lower() == deals.lower()), "Others")
    other = _s(c.get("deals_in_other"), 60)
    phone, alt = _digits10(c.get("phone")), _digits10(c.get("alternate_phone"))
    if alt == phone:
        alt = None
    ig = _s(c.get("instagram"), 100)
    services = c.get("services")
    if isinstance(services, list):
        services = ", ".join(str(x) for x in services if x)
    return {
        "name": _s(c.get("business_name"), 150) or _s(c.get("contact_person"), 150),
        "primary_contact_name": _s(c.get("contact_person"), 100),
        "primary_mobile": phone, "alternate_mobile": alt,
        "email": (_s(c.get("email"), 254) or "").lower() or None,
        "website": _s(c.get("website"), 255),
        "instagram": ig.lstrip("@") if ig else None,
        "address": _s(c.get("address"), 500), "locality": _s(c.get("locality"), 100),
        "city": _s(c.get("city"), 50), "pincode": (_s(c.get("pincode"), 6) or "") if re.fullmatch(r"[1-9]\d{5}", str(c.get("pincode") or "")) else None,
        "deals_in": (other if deals == "Others" and other else deals),
        "services": _s(services, 500),
        "notes": (str(c.get("notes")).strip()[:3000] if c.get("notes") else None),
    }


_DIG = "right(regexp_replace(COALESCE({c}, ''), '[^0-9]', '', 'g'), 10)"


async def _find_existing(c: Dict[str, Any]):
    for num in (c.get("primary_mobile"), c.get("alternate_mobile")):
        if num:
            row = await database.fetch_one(
                f"SELECT vendor_id, name FROM vendor_master WHERE duplicate_of_id IS NULL AND "
                f"({_DIG.format(c='primary_mobile')} = :m OR {_DIG.format(c='alternate_mobile')} = :m "
                f"OR {_DIG.format(c='whatsapp_number')} = :m) ORDER BY vendor_id LIMIT 1", {"m": num})
            if row:
                return row
    if c.get("name") and not c.get("primary_mobile"):
        return await database.fetch_one(
            "SELECT vendor_id, name FROM vendor_master WHERE duplicate_of_id IS NULL AND LOWER(TRIM(name)) = LOWER(:n) "
            "ORDER BY vendor_id LIMIT 1", {"n": c["name"]})
    return None


async def add_note(vendor_id: int, note: str, by: str, source: str, slack_ts: Optional[str] = None) -> None:
    note = (note or "").strip()
    if note:
        await database.execute(
            "INSERT INTO vendor_notes (vendor_id, note, added_by, source, slack_ts) VALUES (:v, :n, :b, :s, :t)",
            {"v": vendor_id, "n": note[:5000], "b": (by or "")[:100], "s": source, "t": slack_ts})


async def _save_card(vendor_id: int, data: bytes, mime: str, i: int) -> None:
    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
    await database.execute(
        "INSERT INTO vendor_catalogues (vendor_id, filename, content_type, size_bytes, file_data) VALUES (:v, :n, :t, :s, :d)",
        {"v": vendor_id, "n": f"card-{datetime.now(IST):%Y%m%d}-{i}.{ext}", "t": mime, "s": len(data), "d": data})


async def save_contact(c: Dict[str, Any], who: str, cards: List[Tuple[bytes, str]], slack_ts: Optional[str]) -> Dict[str, Any]:
    existing = await _find_existing(c)
    extra = "; ".join(x for x in [
        f"Instagram @{c['instagram']}" if c.get("instagram") else "",
        f"Services: {c['services']}" if c.get("services") else ""] if x)
    if existing:
        vid = existing["vendor_id"]
        # Fill only blank fields on the existing partner; never overwrite.
        for f in ("primary_contact_name", "alternate_mobile", "email", "website", "address", "locality", "city", "pincode", "deals_in"):
            if c.get(f):
                await database.execute(
                    f"UPDATE vendor_master SET {f} = :v WHERE vendor_id = :id AND COALESCE(TRIM({f}), '') = ''",
                    {"v": c[f], "id": vid})
        outcome = "existing"
    else:
        vals = {k: c.get(k) for k in ("name", "primary_contact_name", "alternate_mobile", "email", "website",
                                       "address", "locality", "city", "pincode", "deals_in")}
        vals["name"] = vals["name"] or "Unnamed contact"
        vals["primary_mobile"] = c.get("primary_mobile") or PLACEHOLDER_MOBILE
        vals["whatsapp_number"] = c.get("primary_mobile")
        vals["remarks"] = extra or None
        cols = ", ".join(vals)
        vid = await database.fetch_val(
            f"INSERT INTO vendor_master ({cols}, is_active, onboarding_source, onboarding_reviewed, submitted_on) "
            f"VALUES ({', '.join(':' + k for k in vals)}, FALSE, 'slack_contact', TRUE, NOW()) RETURNING vendor_id", vals)
        outcome = "created"
    for i, (data, mime) in enumerate(cards, start=1):
        await _save_card(vid, data, mime, i)
    note = c.get("notes") or ""
    if outcome == "existing" and extra:
        note = (note + "\n" if note else "") + extra
    await add_note(vid, note, who, "slack", slack_ts)
    return {"vendor_id": vid, "outcome": outcome, "name": existing["name"] if existing else vals["name"], "c": c}


def _link(vid: int, name: str) -> str:
    return f"<{settings.SITE_URL.rstrip('/')}/admin.html#vendor-{vid}|{name}>"


def _missing(c: Dict[str, Any]) -> List[str]:
    return [label for label, ok in [
        ("mobile number", c.get("primary_mobile")), ("what they deal in", c.get("deals_in")),
        ("area", c.get("locality") or c.get("address")), ("email", c.get("email"))] if not ok]


async def handle_message(ev: Dict[str, Any]) -> None:
    channel, ts = ev.get("channel"), ev.get("ts")
    text = clean_slack_text(ev.get("text") or "")
    who = await slack_user_name(ev.get("user") or "")
    reply = []
    try:
        m = re.match(r"^\s*(?:find|search|notes?)\s+(.+)$", text, re.I | re.S)
        if m and not ev.get("files"):
            await slack_api("chat.postMessage", channel=channel, thread_ts=ts,
                            text=await find_text(m.group(1).strip()), unfurl_links=False)
            return
        files = [f for f in (ev.get("files") or []) if (f.get("mimetype") or "").startswith("image/")]
        images = [x for x in [await download_slack_file(f) for f in files] if x]
        if files and not images:
            reply.append("⚠️ I couldn't open the photo — the Slack app needs the files:read permission.")
        if not text.strip() and not images:
            return
        if settings.ANTHROPIC_API_KEY:
            contacts = await _ask_claude(images, text)
        else:
            contacts = _parse_plain(text)
            if images:
                reply.append("⚠️ ANTHROPIC_API_KEY isn't set on Railway, so I saved the card photo but couldn't read it.")
        contacts = [c for c in (_clean(x) for x in contacts) if c.get("name") or c.get("primary_mobile")]
        if not contacts:
            reply.append("I couldn't find a name or number to save. Post the card photo, or a line like "
                         "_Riya Balloons, decorator, 98200 11111, Andheri — good work, a bit pricey_.")
        saved = []
        for i, c in enumerate(contacts):
            # One card per contact when the counts match; otherwise all cards go on the first.
            cards = [images[i]] if len(images) == len(contacts) else (images if i == 0 else [])
            saved.append(await save_contact(c, who, cards, ts))
        if saved:
            await database.execute(
                "INSERT INTO slack_vendor_posts (channel, ts, vendor_ids) VALUES (:c, :t, :v) "
                "ON CONFLICT (channel, ts) DO UPDATE SET vendor_ids = EXCLUDED.vendor_ids",
                {"c": channel, "t": ts, "v": ",".join(str(s["vendor_id"]) for s in saved)})
        for s in saved:
            c = s["c"]
            head = ("✅ Saved to the vendor master as " if s["outcome"] == "created"
                    else "ℹ️ Already in the vendor master — added your note to ") + _link(s["vendor_id"], s["name"]) + f" (#{s['vendor_id']})"
            bits = [x for x in [
                c.get("primary_contact_name"),
                " / ".join(p for p in [c.get("primary_mobile"), c.get("alternate_mobile")] if p),
                c.get("deals_in"), c.get("email"), c.get("website"), ("@" + c["instagram"]) if c.get("instagram") else None,
                c.get("locality") or c.get("city")] if x]
            lines = [head]
            if bits:
                lines.append("• " + " · ".join(bits))
            if c.get("notes"):
                lines.append("📝 Note: " + c["notes"][:300] + ("…" if len(c["notes"]) > 300 else ""))
            if s["outcome"] == "created" and _missing(c):
                lines.append("Missing: " + ", ".join(_missing(c)))
            reply.append("\n".join(lines))
        if saved:
            reply.append("_Reply in this thread to add more notes. Type *find <name>* in the channel to pull them up later._")
    except Exception as exc:
        logger.exception("Slack vendors: failed")
        reply.append(f"Something went wrong: {str(exc)[:200]}")
    if reply:
        await slack_api("chat.postMessage", channel=channel, thread_ts=ts, text="\n\n".join(reply), unfurl_links=False)


async def handle_reply(ev: Dict[str, Any], post: Dict[str, Any]) -> None:
    """A reply in the thread of a saved contact = another note on it."""
    text = clean_slack_text(ev.get("text") or "")
    if not text.strip():
        return
    who = await slack_user_name(ev.get("user") or "")
    ids = [int(x) for x in (post.get("vendor_ids") or "").split(",") if x.strip().isdigit()]
    if not ids:
        return
    target = ids
    if len(ids) > 1:   # several contacts in one post: "#123 call in Dec" picks one
        m = re.search(r"#(\d{1,7})\b", text)
        target = [int(m.group(1))] if m and int(m.group(1)) in ids else ids
    names = []
    for vid in target:
        await add_note(vid, text, who, "slack", ev.get("ts"))
        names.append(await database.fetch_val("SELECT name FROM vendor_master WHERE vendor_id = :v", {"v": vid}) or f"#{vid}")
    await slack_api("chat.postMessage", channel=ev.get("channel"), thread_ts=ev.get("thread_ts"),
                    text="📝 Note added to " + ", ".join(names), unfurl_links=False)


async def find_text(q: str) -> str:
    words = [w for w in re.split(r"\s+", q) if w][:5]
    conds = " AND ".join(
        f"(v.name ILIKE :w{i} OR v.primary_contact_name ILIKE :w{i} OR v.deals_in ILIKE :w{i} OR v.locality ILIKE :w{i} "
        f"OR v.city ILIKE :w{i} OR v.address ILIKE :w{i} OR v.primary_mobile ILIKE :w{i} OR v.remarks ILIKE :w{i} "
        f"OR EXISTS (SELECT 1 FROM vendor_notes n WHERE n.vendor_id = v.vendor_id AND n.note ILIKE :w{i}))"
        for i in range(len(words))) or "TRUE"
    rows = await database.fetch_all(
        f"SELECT v.vendor_id, v.name, v.deals_in, v.primary_mobile, v.locality, v.onboarding_source FROM vendor_master v "
        f"WHERE v.duplicate_of_id IS NULL AND {conds} ORDER BY (v.onboarding_source = 'slack_contact') DESC, v.name LIMIT 8",
        {f"w{i}": f"%{w}%" for i, w in enumerate(words)})
    if not rows:
        return f"No partners match _{q}_."
    out = []
    for r in rows:
        notes = await database.fetch_all(
            "SELECT note, added_by, created_at FROM vendor_notes WHERE vendor_id = :v ORDER BY created_at DESC LIMIT 5",
            {"v": r["vendor_id"]})
        num = r["primary_mobile"] if r["primary_mobile"] and r["primary_mobile"] != PLACEHOLDER_MOBILE else "no number"
        line = f"*{_link(r['vendor_id'], r['name'])}* (#{r['vendor_id']}) · {r['deals_in'] or '—'} · {num}" + (f" · {r['locality']}" if r["locality"] else "")
        for n in notes:
            when = n["created_at"].astimezone(IST).strftime("%d %b %Y") if n["created_at"] else ""
            line += f"\n   📝 {when} {n['added_by'] or ''}: {n['note'][:250]}"
        out.append(line)
    return f"Partners matching _{q}_:\n\n" + "\n\n".join(out)
