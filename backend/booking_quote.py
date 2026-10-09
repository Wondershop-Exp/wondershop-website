"""
Quotation / party-plan PDF from the BOOKINGS panel — 2026-10-06, per Shruti:
"add the quote pdf in the bookings panel as well. it's useful to inform the
client of all the details of the party".

Built from the booking page itself (get_booking_detail): every service as
currently set on the booking, priced exactly like its Total MRP, with the
same look as the sales module's quotation (quotation_builder). A confirmed
booking prints as a "PARTY PLAN" (Booking No., Grand Total, no validity
window); a not-yet-booked lead prints as a normal QUOTATION.

Also home of apply_decor_ref(): puts the lead's uploaded decor reference
image (routers/decor_refs.py) on the Decor line of either PDF.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, Response

import catalogue_data as cat

logger = logging.getLogger(__name__)
router = APIRouter()

IST_OFFSET = timedelta(hours=5, minutes=30)
DECOR_REF_KEY = "__decor_ref__"
MUSIC_LABELS = {"Classic": "Music Essential", "Premium": "Music Plus"}


def apply_decor_ref(data: dict, images: dict, ref: Optional[dict], own: bool = True) -> None:
    """Uploaded decor reference photo on the Decor line (no "reference
    picture" disclaimer — it's the client's own chosen design). With no decor
    selected yet, adds a "Decor — as per your reference picture" line."""
    if not ref or not ref.get("image"):
        return
    images[DECOR_REF_KEY] = ref["image"]
    for sec in data.get("sections") or []:
        if sec.get("label") != "Decor":
            continue
        if sec.get("lines"):
            ln = sec["lines"][0]
            ln["image"] = DECOR_REF_KEY
            ln["details"] = [d for d in (ln.get("details") or []) if d != cat.DECOR_REFERENCE_NOTE]
            if own:
                ln["details"].append("Design as per the reference picture shared")
        else:
            sec["lines"] = [{"name": "Decor — as per your reference picture", "image": DECOR_REF_KEY,
                             "details": ["Balloon colours and flex/sunboard designs (as applicable) will be "
                                         "finalised with you by your party manager."],
                             "price": None, "price_text": "To be confirmed"}]
            sec["not_selected"] = False
        break


def _money(v) -> Optional[float]:
    try:
        return None if v in (None, "") else float(str(v).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


async def booking_quotation_data(lead_id: int, pw: Optional[str], by: Optional[str] = None):
    """(data for build_quotation_pdf, image paths) from the booking page."""
    from routers.admin import get_booking_detail, _resolve_decor_override
    from routers.sales_leads import _fmt_time_12h, _ordinal_age, QUOTE_VALID_HOURS
    from quotation_builder import inr, SECTION_ICONS, MASCOT_PATH

    d = await get_booking_detail(lead_id, pw)
    fields = {f["field_key"]: f for s in d["sections"] for f in s["fields"]}

    def val(key):
        f = fields.get(key)
        if not f or f.get("removed"):
            return None
        v = f.get("assigned_value") if f.get("is_direct_write") and f.get("assigned_value") else f.get("customer_choice")
        v = (str(v).strip() if v is not None else "")
        return v or None

    def cust_val(key):   # the client's choice (services) — not the vendor name in assigned_value
        f = fields.get(key)
        if not f or f.get("removed"):
            return None
        v = (str(f.get("customer_choice") or "")).strip()
        return v or None

    P = d.get("pricing") or {}
    items = [(i["label"], float(i["amount"] or 0)) for i in (P.get("items") or [])]
    extras = [(i["label"], float(i["amount"] or 0)) for i in (P.get("extra_items") or [])]
    gift_items = [(i["label"], float(i["amount"] or 0)) for i in (P.get("gift_items") or [])]
    unpriced = list(P.get("unpriced") or [])
    has_unpriced = {"any": bool(unpriced)}

    def take(prefix):
        out = [(l, a) for l, a in items if l.startswith(prefix)]
        for x in out:
            items.remove(x)
        return out

    def take_unpriced(prefix):
        out = [u for u in unpriced if u.startswith(prefix)]
        for x in out:
            unpriced.remove(x)
        return out

    def after(label):
        name = label.split(":", 1)[1].strip() if ":" in label else label
        name = re.sub(r"\s*\((confirmed|quoted, to be confirmed)\)$", "", name)
        return re.sub(r"\s*\(custom\)$", "", name)   # custom activity (2026-10-07) — internal tag

    sections = []

    def add(label, lines, **kw):
        sections.append({"label": label, "lines": lines, "not_selected": not lines, **kw})

    # 1. Decor
    lines = []
    for label, amt in take("Decor"):
        name = after(label)
        ref = _resolve_decor_override(name) or {}
        res = cat.resolve_decor(ref.get("id"), ref.get("p")) if ref.get("id") else None
        det = []
        if res:
            incl = [f"{l}: {v}" for l, v, na in res["spec"] if not na]
            if incl:
                det.append(" · ".join(incl[:3]))
                if len(incl) > 3:
                    det.append(" · ".join(incl[3:]))
            if res.get("reference"):
                det.append(cat.DECOR_REFERENCE_NOTE)
        lines.append({"name": name, "details": det, "image": res["image_path"] if res else None, "price": amt})
    for u in take_unpriced("Decor"):
        lines.append({"name": after(u), "details": [], "image": None, "price": None, "price_text": "To be confirmed"})
    add("Decor", lines)

    # 2. Activities
    lines = []
    # Custom activities' reference photos (2026-10-08) — "aref:<token>".
    custom_photo = {t.get("name"): "aref:" + t["photo"] for t in (d.get("to_be_confirmed") or [])
                    if t.get("kind") == "custom" and t.get("photo")}
    for label, amt in take("Activity"):
        name = after(label)
        det = []
        m = re.match(r"^(.*?) \((\d+) kids × ₹([\d.,]+)\)$", name)
        if m:
            name = m.group(1)
            det.append(f"{m.group(2)} kids × {inr(float(m.group(3).replace(',', '')))} per child")
        note = cat.activity_venue_note(None, name)
        lines.append({"name": name, "details": det + ([note] if note else []),
                      "image": custom_photo.get(name) or cat.resolve_activity_image(None, name), "price": amt})
    for u in take_unpriced("Activity"):
        name = after(u)
        note = cat.activity_venue_note(None, name)
        lines.append({"name": name, "details": [note] if note else [], "image": custom_photo.get(name) or cat.resolve_activity_image(None, name),
                      "price": None, "price_text": "Price on request"})
    if cust_val("activities_notes"):   # remarks about the activities (2026-10-07)
        lines.append({"name": "Activity notes", "details": cust_val("activities_notes").splitlines(),
                      "image": None, "price": None})
    add("Activities", lines)

    # 3. Host
    lines = []
    for label, amt in take("Host"):
        name = after(label)
        tier = name.split(" (")[0].strip()
        included = "included" in name.lower()
        ln = {"name": f"{tier} Host", "image": cat.HOST_TIER_IMAGES.get(tier) or cat.HOST_TIER_IMAGES.get("Signature"),
              "details": [(lambda t: t[:1].upper() + t[1:])(name[len(tier):].strip(" ()")) + " — no extra cost"] if included else [],
              "price": None if included else amt}
        if included:
            ln["price_text"] = "Included"
        lines.append(ln)
    for u in take_unpriced("Host"):
        lines.append({"name": after(u), "details": [], "image": None, "price": None, "price_text": "To be confirmed"})
    add("Host", lines)

    # 4. Music (+ lights / smoke)
    lines = []
    for label, amt in take("Music:"):
        tier = after(label)
        lines.append({"name": MUSIC_LABELS.get(tier, tier), "details": [], "image": cat.MUSIC_IMAGES.get(tier), "price": amt})
    for label, amt in take("Music lights") + take("Smoke machine"):
        lines.append({"name": f"Add-on: {label}", "details": [], "image": None, "price": amt})
    add("Music", lines)

    # 5. Pinata
    lines = []
    for label, amt in take("Piñata"):
        name = after(label)
        lines.append({"name": name, "details": [], "image": cat.resolve_pinata_image(cat.PINATA_NAME_TO_ID.get(name)), "price": amt})
    for u in take_unpriced("Piñata"):
        lines.append({"name": after(u), "details": [], "image": None, "price": None, "price_text": "To be confirmed"})
    add("Pinata", lines)

    # 6. Photographer
    lines = []
    for label, amt in take("Photography"):
        tier = after(label)
        lines.append({"name": f"{tier} Photography", "details": [" · ".join(cat.PHOTO_TIER_FEATURES.get(tier, []))],
                      "image": cat.PHOTO_IMAGES.get(tier), "price": amt})
    add("Photographer", lines)

    # 6b. Cake (sales-module only, 2026-10-07)
    lines = []
    for label, amt in take("Cake"):
        lines.append({"name": "Cake", "details": [after(label)], "image": "img/checklist-cake.jpg", "price": amt})
    for u in take_unpriced("Cake"):
        lines.append({"name": "Cake", "details": [after(u)], "image": "img/checklist-cake.jpg",
                      "price": None, "price_text": "To be confirmed"})
    if lines:
        add("Cake", lines)

    # 7. E-Invite (+ Save the Date)
    lines = []
    for label, amt in take("E-Invite"):
        name = after(label)
        lines.append({"name": name if name.lower().startswith(("save", "video")) else f"{name} E-Invite",
                      "details": [], "image": None, "price": amt})
    for u in take_unpriced("E-Invite"):
        lines.append({"name": after(u), "details": [], "image": None, "price": None, "price_text": "To be confirmed"})
    add("E-Invite", lines)

    # 8. Return gifts (billed separately when the booking says so)
    lines = []
    for label, amt in gift_items + take("Gift"):
        name = after(label)
        m = re.match(r"^(.*?) × (\d+)$", name)
        gname, qty = (m.group(1), int(m.group(2))) if m else (name, 0)
        lines.append({"name": gname, "details": [f"{qty} × {inr(amt / qty)}"] if qty else [],
                      "image": cat.resolve_gift_image_by_name(gname), "price": amt})
    for u in take_unpriced("Gift"):
        lines.append({"name": after(u), "details": [], "image": None, "price": None, "price_text": "To be confirmed"})
    add("Return Gifts", lines, billed_separately=bool(P.get("gifts_separate")))

    # Anything else on the bill (confirmed TBC items, packaging fees, …)
    others = [{"name": l, "details": [], "image": None, "price": a} for l, a in items + extras]
    others += [{"name": u, "details": [], "image": None, "price": None, "price_text": "To be confirmed"} for u in unpriced]
    if others:
        add("Other", others)
    has_unpriced["any"] = any(ln.get("price") is None and ln.get("price_text") not in ("Included",)
                              for s in sections for ln in s["lines"])

    # ── totals: the booking's own Total MRP / discount / Grand Total ─────
    total_mrp = float(P.get("total_mrp") or 0)
    extra_total = round(sum(a for _l, a in extras), 2)
    grand = _money(val("bill_grand_total"))
    discount = float(P.get("discount_amt") or 0)
    subtotal = round(total_mrp + extra_total, 2)
    if grand is None:
        grand = round(subtotal - discount, 2)

    # ── header / details ────────────────────────────────────────────────
    now_ist = datetime.utcnow() + IST_OFFSET
    fmt = lambda t: t.strftime("%d %b %Y, %I:%M %p").lstrip("0").replace(", 0", ", ") + " IST"
    child = (val("child_names") or "").split(",")[0].strip()
    age_ord = _ordinal_age((val("child_ages") or "").split(",")[0].strip() or None)
    party_title = (f"{child}'s {age_ord} Birthday Party" if age_ord else f"{child}'s Birthday Party") if child else "Your Birthday Party"
    event_date = None
    if val("event_date"):
        try:
            event_date = date.fromisoformat(val("event_date")[:10]).strftime("%a, %d %b %Y").replace(" 0", " ")
        except ValueError:
            event_date = val("event_date")
    kids = val("kids_count")
    details = [
        ("Prepared for", val("parent_name")),
        ("Mobile", val("phone")),
        ("Birthday child", ", ".join(filter(None, [child, f"turning {(val('child_ages') or '').split(',')[0].strip()}" if val("child_ages") else None]))),
        ("Event date", event_date),
        ("Time", _fmt_time_12h(val("event_time"))),
        ("Venue handover", _fmt_time_12h(val("venue_handover_time")) or "To be confirmed"),
        ("Packup", _fmt_time_12h(val("packup_time")) or "To be confirmed"),
        ("No. of kids", kids),
        ("Venue", val("venue")),
        ("Theme", (cat._THEMES_BY_ID.get(val("theme") or "") or {}).get("n") or val("theme")),
    ]
    schedule = []
    for line in (val("event_schedule_text") or "").splitlines():
        if not line.strip():
            continue
        t, _, i = line.partition("\t")
        t, i = (t.strip(), i.strip()) if i else ("", t.strip())
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", t):
            t = _fmt_time_12h(t)
        schedule.append((t, i))
    booked = bool(d.get("is_booking"))
    data = {
        "booked": booked,
        "schedule": schedule,
        "quote_no": f"#{lead_id}" if booked else f"WSQ-{lead_id}-{now_ist.strftime('%d%m%y-%H%M')}",
        "issued_at_text": fmt(now_ist),
        "valid_until_text": fmt(now_ist + timedelta(hours=QUOTE_VALID_HOURS)),
        "valid_hours": QUOTE_VALID_HOURS,
        "prepared_by": (by or "").strip() or None,
        "party_title": party_title,
        "client_name": val("parent_name"),
        "client_first_name": cat.greeting_name(val("parent_name")),
        "child_first_name": child,
        "details": details,
        "sections": sections,
        "totals": {
            "subtotal": subtotal, "discount": round(subtotal - grand, 2), "estimate": grand,
            "discount_items": 0, "discount_extra": 0,
            "gift_total": float(P.get("gift_total") or 0) if P.get("gifts_separate") else 0,
            "gift_mrp": 0, "has_unpriced": has_unpriced["any"],
        },
        "extra_terms": cust_val("terms_conditions"),
    }
    paths = [MASCOT_PATH] + list(SECTION_ICONS.values())
    for s in sections:
        paths += [ln.get("image") for ln in s["lines"] if ln.get("image")]
    return data, paths


@router.get("/admin/bookings/{lead_id}/quotation.pdf")
async def booking_quotation_pdf(lead_id: int, by: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    from routers.admin import _require_admin
    from routers.decor_refs import current_for_lead
    from quotation_builder import build_quotation_pdf, fetch_images, quotation_filename
    _require_admin(x_admin_password)
    data, paths = await booking_quotation_data(lead_id, x_admin_password, by)
    images = await fetch_images([p for p in paths if not str(p).startswith("aref:")])
    from routers.sales_leads import load_activity_photos
    await load_activity_photos(images, paths)
    ref = await current_for_lead(lead_id, with_image=True)
    own = bool(ref)
    if not ref:
        # A website design picked in Build-a-Birthday (decor id "ref-<n>").
        from database import database
        import json
        from routers.decor_refs import item_with_image
        row = await database.fetch_one("SELECT builder_snapshot FROM leads WHERE lead_id = :id", values={"id": lead_id})
        snap = (row and row["builder_snapshot"]) or {}
        snap = json.loads(snap) if isinstance(snap, str) else snap
        did = str(((snap or {}).get("decor") or {}).get("id") or "")
        if did.startswith("ref-") and did[4:].isdigit():
            ref = await item_with_image(int(did[4:]))
    apply_decor_ref(data, images, ref, own=own)
    pdf = build_quotation_pdf(data, images)
    fname = quotation_filename(data)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Quote-Filename": fname, "Access-Control-Expose-Headers": "X-Quote-Filename",
                 "Cache-Control": "no-store"},
    )


# ── 1-day-before WhatsApp message (2026-10-09, per Shruti) ──────────────
# "a message to send to the client 1 day before the event" — sent by hand
# on WhatsApp for now (copy / open WhatsApp from the booking page), to be
# automated later. Built from the same booking data as the party plan PDF
# above, so it always matches what's on the booking.
def _plan_names(section: Optional[dict]) -> list:
    if not section:
        return []
    out = []
    for ln in section.get("lines") or []:
        name = (ln.get("name") or "").strip()
        if not name or name == "Activity notes":
            continue
        if name.startswith("Add-on: "):
            name = name[len("Add-on: "):]
        if ln.get("price_text") == "To be confirmed":
            name += " (to be confirmed)"
        out.append(name)
    return out


async def pre_event_message_text(lead_id: int, pw: Optional[str]) -> dict:
    from routers.admin import get_booking_detail
    from routers.sales_leads import _fmt_time_12h, _ordinal_age
    from quotation_builder import inr
    from database import database
    import json

    d = await get_booking_detail(lead_id, pw)
    fields = {f["field_key"]: f for s in d["sections"] for f in s["fields"]}

    def val(key):
        f = fields.get(key)
        if not f or f.get("removed"):
            return None
        v = f.get("assigned_value") if f.get("is_direct_write") and f.get("assigned_value") else f.get("customer_choice")
        v = (str(v).strip() if v is not None else "")
        return v or None

    data, _paths = await booking_quotation_data(lead_id, pw)
    secs = {s["label"]: s for s in data["sections"]}

    child = (val("child_names") or "").split(",")[0].strip()
    age_ord = _ordinal_age((val("child_ages") or "").split(",")[0].strip() or None)
    title = (f"{child}'s {age_ord} Birthday" if age_ord else f"{child}'s Birthday") if child else "the Birthday Party"
    tbc = "To be confirmed"
    t = lambda k: _fmt_time_12h(val(k)) or tbc
    event_date = tbc
    if val("event_date"):
        try:
            event_date = date.fromisoformat(val("event_date")[:10]).strftime("%A, %d %B %Y").replace(" 0", " ")
        except ValueError:
            event_date = val("event_date")

    # Host game gifts live on the sales panel only.
    host_gifts = None
    try:
        row = await database.fetch_one("SELECT requirements FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
        reqs = (row and row["requirements"]) or {}
        reqs = json.loads(reqs) if isinstance(reqs, str) else reqs
        hg = (reqs or {}).get("host_gifts") or {}
        host_gifts = (str(hg.get("selected") or "").strip() or None) if isinstance(hg, dict) else None
    except Exception:
        logger.exception(f"Lead #{lead_id}: couldn't read host gifts for the pre-event message")

    none = "Not included"
    host_lines = [n for n in _plan_names(secs.get("Host")) if n.lower() != "host gifts"]
    engagement = " + ".join(filter(None, [
        " + ".join(host_lines) or None,
        ("Activities: " + ", ".join(_plan_names(secs.get("Activities")))) if _plan_names(secs.get("Activities")) else None,
    ])) or none
    gifts = ", ".join(_plan_names(secs.get("Return Gifts"))) or none
    if gifts != none and secs.get("Return Gifts", {}).get("billed_separately"):
        gifts += " (billed separately)"
    extras = _plan_names(secs.get("E-Invite")) + _plan_names(secs.get("Other"))
    terms = [x.strip(" •-\t") for x in (data.get("extra_terms") or "").splitlines() if x.strip(" •-\t")]

    plan = [
        ("Decor", ", ".join(_plan_names(secs.get("Decor"))) or none),
        ("Engagement", engagement),
        ("Music", ", ".join(_plan_names(secs.get("Music"))) or none),
        ("Cake", ", ".join(ln["details"][0] for ln in (secs.get("Cake") or {}).get("lines", []) if ln.get("details")) or none),
        ("Return gifts", gifts),
        ("Piñata", ", ".join(_plan_names(secs.get("Pinata"))) or none),
        ("Host game gifts", host_gifts or none),
        ("Photographer", ", ".join(_plan_names(secs.get("Photographer"))) or none),
    ]
    lines = [
        f"Hi {data.get('client_first_name') or 'there'}! 🎉",
        "",
        f"We're all set for *{title}* tomorrow! Here's a quick recap of the plan:",
        "",
        f"📅 *Date:* {event_date}",
        f"⏰ *Event start time:* {t('event_time')}",
        f"⏳ *Event end time:* {t('event_end_time')}",
        f"🔑 *Venue handover time:* {t('venue_handover_time')}",
        f"✨ *Setup ready by:* {t('setup_ready_time')}",
    ]
    if val("venue"):
        lines.append(f"📍 *Venue:* {val('venue')}")
    lines += ["", "*Event Plan*"]
    for i, (k, v) in enumerate(plan, 1):
        lines.append(f"{i}. *{k}:* {v}")
    lines.append(f"9. *Anything else / T&C:*" + ("" if (extras or terms) else " None"))
    for x in extras + terms:
        lines.append(f"   • {x}")

    grand = _money(val("bill_grand_total"))
    adv = _money(val("bill_advance"))
    bal = _money(val("bill_balance"))
    if bal is None and grand is not None:
        bal = round(grand - (adv or 0), 2)
    money = lambda n: inr(n) if n is not None else tbc
    lines += [
        "",
        "*Payment Summary*",
        f"Total event amount: {money(grand)}",
        f"Advance received: {money(adv)}",
        f"Amount payable: *{money(bal)}*",
        "",
        (f"We'd be grateful if the balance of {money(bal)} could be kept ready before the event begins, "
         "so the handover goes smoothly and you can enjoy the party stress-free. 🙏") if (bal or 0) > 0
        else "Your payment is all settled — thank you! 🙏",
        "",
        "Please let us know if anything needs a change. Looking forward to celebrating with you tomorrow! 🎈",
        "",
        "Warm regards,",
        "Team Wondershop Experiences",
    ]
    phone = re.sub(r"\D", "", val("phone") or "")
    if len(phone) == 10:
        phone = "91" + phone
    return {"text": "\n".join(lines), "phone": phone}


@router.get("/admin/bookings/{lead_id}/pre-event-message")
async def booking_pre_event_message(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    from routers.admin import _require_admin
    _require_admin(x_admin_password)
    return await pre_event_message_text(lead_id, x_admin_password)
