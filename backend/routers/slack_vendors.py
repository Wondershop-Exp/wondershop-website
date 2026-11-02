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
  5. NEW CATEGORY (2026-11-02, per Shruti): "add category Hardware Store" in
     the channel, or a card for a kind of business that fits no "What do you
     deal in" category -> the bot ASKS first ("Add X as a new category? Reply
     yes / no") and only adds it after a "yes" in that thread. Added
     categories show on the partner form and in the Partners tab
     (partner_categories.py, migrations/082).
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

from partner_categories import BASE as DEALS, all_categories, add_category, find_category, tidy_name

logger = logging.getLogger(__name__)

PLACEHOLDER_MOBILE = "1111111111"   # same placeholder as migrations/052
# Built-in categories: partner_categories.BASE (imported as DEALS); the full
# list incl. ones added from Slack comes from all_categories().

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
- new_category: ONLY if deals_in is "Others": a short Title Case name for this kind of supplier that could become a new category (2-3 words, e.g. "Party Supplies Store", "Balloon Artist"); otherwise null
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


async def _ask_claude(images: List[Tuple[bytes, str]], text: str, deals: List[str]) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = []
    for data, mime in images[:6]:
        data, mime = _shrink(data, mime)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": PROMPT.format(
        today=datetime.now(IST).date().isoformat(), text=text or "", deals=", ".join(deals))})
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


def _parse_plain(text: str, deals_list: List[str]) -> List[Dict[str, Any]]:
    """Without the Claude key: first line = name, numbers / email picked out,
    everything else kept as the note."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    phones = [p for p in (_digits10(x) for x in PHONE_RE.findall(text)) if p]
    email = (EMAIL_RE.search(text) or [None])[0]
    name = re.split(r"[,–-]|\d", lines[0])[0].strip() or lines[0][:60]
    deals = next((d for d in deals_list if d.lower() in text.lower()), None)
    return [{"business_name": name, "phone": phones[0] if phones else None,
             "alternate_phone": phones[1] if len(phones) > 1 else None, "email": email,
             "deals_in": deals, "notes": text}]


def _clean(c: Dict[str, Any], deals_list: List[str]) -> Dict[str, Any]:
    deals = _s(c.get("deals_in"), 60)
    if deals and deals not in deals_list:
        deals = next((d for d in deals_list if d.lower() == deals.lower()), "Others")
    other = _s(c.get("deals_in_other"), 60)
    new_cat = tidy_name(c.get("new_category") or "") if deals == "Others" else ""
    if new_cat and new_cat.lower() in {d.lower() for d in deals_list}:
        deals, other, new_cat = next(d for d in deals_list if d.lower() == new_cat.lower()), None, ""
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
        # A suggested new category is saved as their "deals in" straight away;
        # it becomes a listed category once Shruti says yes in the thread.
        "deals_in": (new_cat or (other if deals == "Others" and other else deals)),
        "new_category": new_cat or None,
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
        cm = re.match(r"^\s*(?:add|new|create)\s+(?:a\s+)?(?:new\s+)?(?:deals?[- ]in\s+)?categor(?:y|ies)\s*[:\-]?\s*(.+)$", text, re.I | re.S)
        if cm and not ev.get("files"):
            await ask_new_categories(channel, ts, [n for n in re.split(r"\s*(?:,|\n|;)\s*", cm.group(1)) if n.strip()], who)
            return
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
        deals_list = await all_categories()
        if settings.ANTHROPIC_API_KEY:
            contacts = await _ask_claude(images, text, deals_list)
        else:
            contacts = _parse_plain(text, deals_list)
            if images:
                reply.append("⚠️ ANTHROPIC_API_KEY isn't set on Railway, so I saved the card photo but couldn't read it.")
        contacts = [c for c in (_clean(x, deals_list) for x in contacts) if c.get("name") or c.get("primary_mobile")]
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
        # Suggested new categories: ask, don't add (2026-11-02).
        new_cats: Dict[str, List[int]] = {}
        for s in saved:
            if s["c"].get("new_category"):
                new_cats.setdefault(s["c"]["new_category"], []).append(s["vendor_id"])
        for name, ids in new_cats.items():
            await _record_request(channel, ts, name, ids, who)
            reply.append(_question(name, ids))
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


# ─── New "deals in" categories, confirmed in Slack (2026-11-02) ────────────
def _question(name: str, ids: List[int]) -> str:
    on = f" (and set it on #{', #'.join(str(i) for i in ids)})" if ids else ""
    return (f"❓ *{name}* isn't one of the \"What do you deal in\" categories yet. "
            f"Add it as a new category{on}?\nReply *yes* in this thread to add it, *yes: Better Name* to add it "
            f"under another name, or *no* to skip.")


async def _record_request(channel: str, ts: str, name: str, ids: List[int], who: str) -> None:
    await database.execute(
        "INSERT INTO slack_category_requests (channel, thread_ts, name, vendor_ids, asked_by) VALUES (:c, :t, :n, :v, :b)",
        {"c": channel, "t": ts, "n": name, "v": ",".join(str(i) for i in ids), "b": (who or "")[:100]})


async def ask_new_categories(channel: str, ts: str, names: List[str], who: str) -> None:
    out = []
    for raw in names[:10]:
        name = tidy_name(raw)
        if len(name) < 3:
            continue
        existing = await find_category(name)
        if existing:
            out.append(f"ℹ️ *{existing}* is already a category.")
            continue
        await _record_request(channel, ts, name, [], who)
        out.append(_question(name, []))
    await slack_api("chat.postMessage", channel=channel, thread_ts=ts,
                    text="\n\n".join(out) or "Tell me the category name, e.g. _add category Hardware Store_.",
                    unfurl_links=False)


_YES = re.compile(r"^\s*(yes|y|yeah|yep|ok|okay|confirm|add it|go ahead|👍)\b\s*(?:[:\-–]\s*(.+))?$", re.I | re.S)
_NO = re.compile(r"^\s*(no|n|nope|skip|cancel|don'?t)\b", re.I)


async def handle_category_reply(ev: Dict[str, Any]) -> bool:
    """A yes / no to a pending category question in this thread. True if handled."""
    text = clean_slack_text(ev.get("text") or "").strip()
    yes, no = _YES.match(text), _NO.match(text)
    if not (yes or no):
        return False
    reqs = await database.fetch_all(
        "SELECT * FROM slack_category_requests WHERE channel = :c AND thread_ts = :t AND status = 'pending' ORDER BY id",
        {"c": ev.get("channel"), "t": ev.get("thread_ts")})
    if not reqs:
        return False
    who = await slack_user_name(ev.get("user") or "")
    other_name = tidy_name(yes.group(2)) if yes and yes.group(2) and len(reqs) == 1 else ""
    out = []
    for r in reqs:
        ids = [int(x) for x in (r["vendor_ids"] or "").split(",") if x.strip().isdigit()]
        if yes:
            final = await add_category(other_name or r["name"], who)
            if ids and final != r["name"]:
                await database.execute(
                    "UPDATE vendor_master SET deals_in = :n WHERE vendor_id = ANY(:ids) AND deals_in = :old",
                    {"n": final, "ids": ids, "old": r["name"]})
            await database.execute("UPDATE slack_category_requests SET status = 'added' WHERE id = :i", {"i": r["id"]})
            out.append(f"✅ Added *{final}* as a category — it now shows on the partner form and in the Partners tab."
                       + (f" Set on #{', #'.join(map(str, ids))}." if ids else ""))
        else:
            await database.execute("UPDATE slack_category_requests SET status = 'declined' WHERE id = :i", {"i": r["id"]})
            out.append(f"👍 Not adding *{r['name']}* as a category."
                       + (" The contact keeps it as a note in \"deals in\" — change it in the Partners tab if needed." if ids else ""))
    await slack_api("chat.postMessage", channel=ev.get("channel"), thread_ts=ev.get("thread_ts"),
                    text="\n".join(out), unfurl_links=False)
    return True
