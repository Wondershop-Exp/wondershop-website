"""
Decorator job card — 2026-11-16, per Shruti.

  "help make a job card for decorators and team ... we'll start with the
   decorator first" — age, venue, date, maps link, decor reference pic,
   decor components breakup (welcome poster, balloon bunches, main decor,
   welcome board, welcome arch, custom requests), materials provided by us
   (flex, cutouts, welcome poster), materials brought by them (stand, balloons,
   age foil balloon / light, cake table), pickup location for the flex, and
   completion photos from the decorator.

Decisions (same day):
  * Lives on the booking page; pre-filled from the booking, the team fills
    in what's missing.
  * Sent as a WhatsApp image + short text + a link; the team copy-pastes the
    message for now. English only.
  * Decorators have very basic phones and little schooling: no confirm /
    "picked up" steps for them — they only open the link and send photos.
  * The decorator never sees the client's name or phone — only the Wondershop
    coordinator. The event is called "Sun, 22nd Nov | Ghatkopar | Premium
    Decor 4:30PM" (the time is the ready-by time). The child's name is shown
    only when the decorator needs it for the work (name lights / letters),
    on that request alone.
  * Three times: venue handover, ready by, venue packup. Agreed amount shown.
  * Optional "to return" box (lights, extension cables lent to them).
  * Completion photos are uploaded through the link (preferred over WhatsApp);
    the team can still upload ones that came on WhatsApp.
  * No quotes for now.

Two trust models, like routers/packaging.py:
  /admin/decor-job/...   the team (X-Admin-Password, admin only — the amount
                         is a payout, so not in security.SALES_ALLOWED).
  /decor-job/{token}     the decorator's link: no login, the long random
                         token IS the access control. Only ever looked up by
                         its exact token; never lists anything.

The link shows `auto` — the booking details frozen when the team last saved
the card — so what the decorator sees is what the team checked and sent.
Tables: decor_job_cards, decor_job_photos (migration 088).
"""
import json
import logging
import re
import secrets
from datetime import date, datetime
from typing import Any, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str

logger = logging.getLogger(__name__)
router = APIRouter()

SITE = "https://www.wondershopexperiences.com"
MAX_IMG_BYTES = 8 * 1024 * 1024
# Completion videos (2026-11-21, per Shruti — "can we give an option to upload
# videos also"): a short walk-around clip from the decorator's phone. Videos
# can't be shrunk on a basic phone, so a 30-second clip is the practical cap.
MAX_VIDEO_BYTES = 30 * 1024 * 1024
_VIDEO_BRANDS = (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  ", b"3gp4", b"3gp5", b"3gp6",
                 b"3g2a", b"dash", b"mmp4", b"MSNV", b"XAVC")
TIERS = ("Classic", "Premium", "Luxury", "Signature")


def _api_base() -> str:
    from routers.decor_refs import PUBLIC_API_BASE
    return PUBLIC_API_BASE


def _img_url(token: str) -> str:
    return f"{_api_base()}/api/decor-job/img/{token}"


def link_for(token: str) -> str:
    return f"{SITE}/decor-job.html?t={token}"


def _sniff(raw: bytes) -> Optional[str]:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:8] == b"ftyp" and raw[8:12] in _VIDEO_BRANDS:
        return ("video/quicktime" if raw[8:12] == b"qt  " else
                "video/3gpp" if raw[8:11] in (b"3gp", b"3g2") else "video/mp4")
    if raw[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def _box_type(p: dict) -> str:
    return "video" if (p or {}).get("type") == "video" else "photo"


def _j(v, default):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _s(v, n: int = 300) -> str:
    return re.sub(r"[ \t]+", " ", str(v if v is not None else "")).strip()[:n]


# ─── formatting ────────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def fmt_date(v: Any) -> str:
    """'2026-11-22' -> 'Sun, 22nd Nov'."""
    try:
        d = v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return _s(v, 40)
    return f"{d.strftime('%a')}, {_ordinal(d.day)} {d.strftime('%b')}"


def fmt_time(v: Any) -> str:
    """'16:30' / '4:30 PM' -> '4:30PM'; '15:00' -> '3PM'. Anything else as typed."""
    t = _s(v, 40)
    if not t:
        return ""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*([AaPp]\.?\s*[Mm]\.?)?", t)
    if not m:
        return t
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").upper().replace(".", "").replace(" ", "")
    if ap:
        if h == 12:
            h = 0
        if ap == "PM":
            h += 12
    if h > 23 or mi > 59:
        return t
    return f"{(h % 12) or 12}{(':%02d' % mi) if mi else ''}{'AM' if h < 12 else 'PM'}"


def _first(v: Any) -> str:
    parts = [p.strip() for p in re.split(r"\s*(?:,|/|&|\band\b)\s*", str(v or "")) if p.strip()]
    return parts[0] if parts else ""


def _age(v: Any) -> str:
    m = re.search(r"\d{1,2}", _first(v))
    return str(int(m.group(0))) if m else ""


# ─── booking -> auto details ──────────────────────────────────────────────

async def _auto_from_booking(lead_id: int, pw: Optional[str]) -> dict:
    """Booking details the job card shows, read from the booking page itself
    (the same data the party plan PDF uses)."""
    from routers.admin import get_booking_detail
    from event_naming import area_of

    d = await get_booking_detail(lead_id, pw)
    fields = {f["field_key"]: f for s in d["sections"] for f in s["fields"]}

    def val(key):
        f = fields.get(key)
        if not f or f.get("removed"):
            return ""
        v = f.get("assigned_value") if f.get("is_direct_write") and f.get("assigned_value") else f.get("customer_choice")
        return _s(v, 500)

    def cust(key):
        f = fields.get(key)
        if not f or f.get("removed"):
            return ""
        return _s(f.get("customer_choice"), 2000)

    venue = val("venue")
    out = {
        "event_date": (val("event_date") or str(d.get("event_date") or ""))[:10],
        "event_time": val("event_time"),
        "handover": val("venue_handover_time"),
        "packup": val("packup_time"),
        "venue": venue,
        "maps": val("venue_maps_link"),
        "area": area_of(venue, val("city")),
        "age": _age(val("child_ages")),
        "child_name": (_first(val("child_names")).split(" ") or [""])[0].title(),
        "theme": val("theme"),
        "package": "Decor", "decor_name": "", "spec": [], "addons": [], "pictures": [],
    }

    # Decor line, its inclusions and add-ons — exactly as on the party plan.
    final_id = ""
    quote_img = ""
    try:
        from booking_quote import booking_quotation_data
        data, _paths = await booking_quotation_data(lead_id, pw)
        final_id = data.get("decor_design_id") or ""
        sec = next((s for s in data.get("sections") or [] if s.get("label") == "Decor"), None)
        lines = (sec or {}).get("lines") or []
        main = next((ln for ln in lines if not str(ln.get("name") or "").startswith("Add-on")), None)
        if main:
            nm = _s(main.get("name"), 120)
            out["decor_name"] = nm
            tier = next((t for t in TIERS if re.search(r"\b" + t + r"\b", nm, re.I)), "")
            out["package"] = f"{tier} Decor" if tier else (nm if "decor" in nm.lower() else (nm + " Decor" if nm else "Decor"))
            from catalogue_data import DECOR_REFERENCE_NOTE
            out["spec"] = [x for x in (main.get("details") or []) if x and x != DECOR_REFERENCE_NOTE
                           and not str(x).startswith("Design as per")][:6]
            img = main.get("image")
            if img and str(img).startswith("img/"):
                quote_img = SITE + "/" + quote(str(img))
        out["addons"] = [_s(str(ln.get("name"))[len("Add-on: "):], 80) for ln in lines
                         if str(ln.get("name") or "").startswith("Add-on: ")]
    except Exception:
        logger.exception(f"Decor job card #{lead_id}: couldn't read the decor from the party plan")

    # Straight from the booking's fields too (2026-11-16): the party plan's
    # Decor line needs the pricing to be there; these don't.
    try:
        import catalogue_data as cat
        from routers.admin import _resolve_decor_override
        if not final_id:
            final_id = cust("addon_decor_design").partition("|")[0].strip()
        nm = cust("svc_decor")
        if nm and not out["decor_name"]:
            out["decor_name"] = _s(nm, 120)
            tier = next((t for t in TIERS if re.search(r"\b" + t + r"\b", nm, re.I)), "")
            out["package"] = f"{tier} Decor" if tier else (nm if "decor" in nm.lower() else nm + " Decor")
        if nm and not out["spec"]:
            ref = _resolve_decor_override(nm) or {}
            res = cat.resolve_decor(ref.get("id"), ref.get("p")) if ref.get("id") else None
            if res:
                incl = [f"{l}: {v}" for l, v, na in res["spec"] if not na]
                out["spec"] = [" · ".join(incl[i:i + 3]) for i in range(0, len(incl), 3)][:6]
        addons = list(out["addons"])
        for key, name in (("addon_decor_cake_table", "Cake Table"), ("addon_decor_age_light", "Age Light"),
                          ("addon_decor_cutouts", "Cutouts"), ("addon_decor_welcome", "Welcome Arch + Welcome Board"),
                          ("addon_decor_welcome_board", "Welcome Board"), ("addon_decor_welcome_arch", "Welcome Arch")):
            if cust(key).lower() == "yes" and name.lower() not in {a.lower() for a in addons}:
                addons.append(name)
        try:
            for c in json.loads(cust("addon_decor_custom") or "[]"):
                n = _s((c or {}).get("name"), 80) if isinstance(c, dict) else ""
                if n and n.lower() not in {a.lower() for a in addons}:
                    addons.append(n)
        except (TypeError, ValueError):
            pass
        out["addons"] = addons
    except Exception:
        logger.exception(f"Decor job card #{lead_id}: couldn't read the decor fields")

    out["pictures"] = await _decor_pictures(lead_id, cust("svc_decor"), final_id, quote_img)
    return out


async def _decor_pictures(lead_id: int, decor_value: str, final_id: str, quote_img: str) -> List[dict]:
    """Every decor picture the booking has, so the card shows what the team
    picked (2026-11-16, per Shruti — "I created a custom decor using image
    uploaded on top. the same image should come here. similarly, if I select a
    decor from the decor dropdown, that should be shown here"):
      1. the decor reference picture uploaded on the booking,
      2. the finalized design (Build-a-Birthday design picker),
      3. the decor picked in the Decor dropdown (catalogue design or a
         website-uploaded design), else the booking's website decor pick.
    Duplicates dropped. The team can untick any of them for the decorator."""
    import catalogue_data as cat
    from routers.decor_refs import current_for_lead, item_with_image, website_ref_options
    pics: List[dict] = []

    def add(url, label):
        if url and url not in {p["url"] for p in pics}:
            pics.append({"url": url, "label": label})

    def site(path):
        return SITE + "/" + quote(str(path)) if path and str(path).startswith("img/") else ""

    async def ref_url(rid: str) -> str:
        if rid.startswith("ref-") and rid[4:].isdigit():
            it = await item_with_image(int(rid[4:]))
            return (it or {}).get("image_url") or ""
        return ""

    try:
        ref = await current_for_lead(lead_id)
        add((ref or {}).get("image_url"), "Uploaded decor picture")
    except Exception:
        logger.exception(f"Decor job card #{lead_id}: uploaded decor picture")
    try:
        if final_id:
            url = await ref_url(final_id) or site((cat.decor_option(final_id) or {}).get("image"))
            add(url, "Finalized design")
    except Exception:
        logger.exception(f"Decor job card #{lead_id}: finalized design picture")
    try:
        url = ""
        v = (decor_value or "").strip()
        if v:
            web = next((o for o in await website_ref_options(refresh=False) if o.get("value") == v), None)
            url = (web or {}).get("image") or ""
            if not url:
                from routers.admin import _resolve_decor_override
                r = _resolve_decor_override(v) or {}
                res = cat.resolve_decor(r.get("id"), r.get("p")) if r.get("id") else None
                url = site((res or {}).get("image_path"))
        if not url:   # a website booking: the decor picked in Build-a-Birthday
            row = await database.fetch_one("SELECT builder_snapshot FROM leads WHERE lead_id = :id", values={"id": lead_id})
            d = (_j(row["builder_snapshot"], {}) if row else {}).get("decor") or {}
            did = str(d.get("id") or "")
            url = await ref_url(did) if did.startswith("ref-") else site((cat.resolve_decor(did, d.get("p")) or {}).get("image_path")) if did else ""
        add(url or quote_img, "Decor selected")
    except Exception:
        logger.exception(f"Decor job card #{lead_id}: selected decor picture")
    return pics


def _spec_has(auto: dict, needle: str) -> bool:
    return any(needle.lower() in str(x).lower() for x in auto.get("spec") or [])


def _addon(auto: dict, *names: str) -> bool:
    return any(a.lower() == n.lower() for a in auto.get("addons") or [] for n in names)


def _slug(label: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:30] or "photo"
    k, i = base, 2
    while k in taken:
        k, i = f"{base}-{i}", i + 1
    taken.add(k)
    return k


def default_data(auto: dict, decor_row: Optional[dict] = None) -> dict:
    """First-time card, pre-filled from the booking."""
    welcome_both = _addon(auto, "Welcome Arch + Welcome Board")
    board = welcome_both or _addon(auto, "Welcome Board") or _spec_has(auto, "Welcome Decor: Welcome board")
    arch = welcome_both or _addon(auto, "Welcome Arch")
    cake = _addon(auto, "Cake Table") or _spec_has(auto, "Cake Table: Included")
    age_light = _addon(auto, "Age Light") or _spec_has(auto, "age light")
    cutouts = _addon(auto, "Cutouts") or (_spec_has(auto, "Cutouts:") and not _spec_has(auto, "Cutouts: Not"))
    panels = _spec_has(auto, "Panels:") and not _spec_has(auto, "Panels: NA")
    known = {"welcome arch + welcome board", "welcome board", "welcome arch", "cake table", "age light", "cutouts"}
    custom = [a for a in auto.get("addons") or [] if a.lower() not in known]

    comps = [
        {"key": "main", "label": "Main decor (backdrop)", "on": True, "qty": "", "notes": "As per decor picture"},
        {"key": "poster", "label": "Welcome poster", "on": True, "qty": "1", "notes": ""},
        {"key": "bunches", "label": "Balloon bunches", "on": True, "qty": "", "notes": ""},
        {"key": "board", "label": "Welcome board", "on": board, "qty": "1" if board else "", "notes": ""},
        {"key": "arch", "label": "Welcome arch", "on": arch, "qty": "1" if arch else "", "notes": ""},
    ]
    taken = {c["key"] for c in comps}
    for c in custom:
        comps.append({"key": _slug(c, taken), "label": c, "on": True, "qty": "", "notes": ""})

    parts = [p.strip() for x in auto.get("spec") or [] for p in str(x).split(" · ")]
    count = next((p.split(":", 1)[1].strip() for p in parts if p.lower().startswith("balloons:")), "")
    cols = next((p.split(":", 1)[1].strip() for p in parts if p.lower().startswith("balloon colours:")), "")
    balloons = ", ".join(x for x in [f"{count} balloons" if count else "",
                                     (f"{cols.lower()} colours" if cols.lower().startswith("up to") else cols) if cols else ""] if x)
    ours = (["Flex"] if panels else []) + (["Cutouts"] if cutouts else []) + ["Welcome poster"]

    taken = set()
    photos = [{"slot": _slug("Full decor", taken), "label": "Full decor", "hint": "Stand back, take the whole setup"},
              {"slot": _slug("Backdrop close-up", taken), "label": "Backdrop close-up", "hint": "Flex and cutouts clearly visible"}]
    for c in comps[1:]:
        if c["on"]:
            photos.append({"slot": _slug(c["label"], taken), "label": c["label"], "hint": ""})
    if cake:
        photos.append({"slot": _slug("Cake table", taken), "label": "Cake table", "hint": "Front view"})
    photos.append({"slot": _slug("Decor video", taken), "label": "Decor video", "hint": "Walk around slowly, 20–30 seconds",
                   "type": "video"})

    return {
        "colours": "", "ready_by": "", "floor": "", "venue_notes": "",
        "components": comps, "custom_requests": "",
        "child_name_needed": False, "child_name": "",
        "ours": ours, "pickup_location": "Wondershop office", "pickup_by": "",
        "stand": "", "balloons": balloons, "age_item": "Light" if age_light else "Foil balloon",
        "cake_table": "Yes" if cake else "No", "bring_other": "",
        "amount": (decor_row or {}).get("amount"), "coordinator_name": "", "coordinator_phone": "",
        "returns": [], "photos": photos,
    }


def clean_data(raw: dict) -> dict:
    """What the team typed, trimmed to known keys and sane sizes."""
    r = raw or {}
    comps = []
    for c in (r.get("components") or [])[:20]:
        if not isinstance(c, dict) or not _s(c.get("label"), 80):
            continue
        comps.append({"key": _s(c.get("key"), 40) or _slug(_s(c.get("label"), 80), {x["key"] for x in comps}),
                      "label": _s(c.get("label"), 80), "on": bool(c.get("on")),
                      "qty": _s(c.get("qty"), 40), "notes": _s(c.get("notes"), 200)})
    taken, photos = set(), []
    for p in (r.get("photos") or [])[:15]:
        if not isinstance(p, dict) or not _s(p.get("label"), 60):
            continue
        slot = re.sub(r"[^a-z0-9-]", "", _s(p.get("slot"), 40).lower())
        if not slot or slot in taken:
            slot = _slug(_s(p.get("label"), 60), taken)
        taken.add(slot)
        photos.append({"slot": slot, "label": _s(p.get("label"), 60), "hint": _s(p.get("hint"), 80), "type": _box_type(p)})
    rets = [{"item": _s(x.get("item"), 80), "qty": _s(x.get("qty"), 20)}
            for x in (r.get("returns") or [])[:15] if isinstance(x, dict) and _s(x.get("item"), 80)]
    amt = r.get("amount")
    try:
        amt = None if amt in (None, "") else round(float(str(amt).replace(",", "").replace("₹", "")), 2)
    except ValueError:
        amt = None
    return {
        "colours": _s(r.get("colours"), 120), "ready_by": _s(r.get("ready_by"), 20),
        "floor": _s(r.get("floor"), 120), "venue_notes": _s(r.get("venue_notes"), 500),
        "components": comps, "custom_requests": _s(r.get("custom_requests"), 800),
        "child_name_needed": bool(r.get("child_name_needed")), "child_name": _s(r.get("child_name"), 60),
        "ours": [_s(x, 60) for x in (r.get("ours") or [])[:15] if _s(x, 60)],
        "pickup_location": _s(r.get("pickup_location"), 200), "pickup_by": _s(r.get("pickup_by"), 60),
        "stand": _s(r.get("stand"), 80), "balloons": _s(r.get("balloons"), 200),
        "age_item": _s(r.get("age_item"), 40), "cake_table": _s(r.get("cake_table"), 60),
        "bring_other": _s(r.get("bring_other"), 300), "amount": amt,
        "coordinator_name": _s(r.get("coordinator_name"), 60), "coordinator_phone": _s(r.get("coordinator_phone"), 20),
        "returns": rets, "photos": photos,
        "hide_pics": [_s(x, 500) for x in (r.get("hide_pics") or [])[:10] if _s(x, 500)],
    }


# ─── what the decorator sees ──────────────────────────────────────────────

def _inr(v) -> str:
    """6500 -> '₹6,500'; 123456 -> '₹1,23,456'."""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return ""
    t = str(abs(n))
    if len(t) > 3:
        t = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", t[:-3]) + "," + t[-3:]
    return ("-" if n < 0 else "") + "₹" + t


def title_of(auto: dict, data: dict) -> str:
    ready = fmt_time(data.get("ready_by") or auto.get("event_time"))
    bits = [fmt_date(auto.get("event_date")) if auto.get("event_date") else "", auto.get("area") or "",
            " ".join(x for x in [auto.get("package") or "Decor", ready] if x)]
    return " | ".join(b for b in bits if b)


def view_of(card: dict, photos: List[dict]) -> dict:
    """Decorator-facing view. No client name/phone; the child's name only
    inside the name request when the team ticked it."""
    a, dt = card["auto"], card["data"]
    done = {p["slot"]: p for p in photos if p["kind"] == "done"}
    hidden = set(dt.get("hide_pics") or [])
    pics = [p for p in a.get("pictures") or [] if p.get("url") not in hidden] + [
        {"url": _img_url(p["token"]), "label": "Reference"} for p in photos if p["kind"] == "ref"]
    bring = []
    if dt.get("stand"):
        bring.append(f"Stand: {dt['stand']}")
    if dt.get("balloons"):
        bring.append(f"Balloons: {dt['balloons']}")
    age = a.get("age")
    if dt.get("age_item") and dt["age_item"] != "Not needed":
        bring.append(f"Age \"{age}\" {dt['age_item'].lower()}" if age else f"Age {dt['age_item'].lower()}")
    cake = dt.get("cake_table") or "No"
    if cake != "No":
        bring.append("Cake table" if cake == "Yes" else f"Cake table ({cake})")
    if dt.get("bring_other"):
        bring.append(dt["bring_other"])
    name_req = ""
    if dt.get("child_name_needed"):
        nm = dt.get("child_name") or a.get("child_name") or ""
        name_req = f"Child's name: {nm.upper()}" if nm else ""
    return {
        "title": title_of(a, dt),
        "date": fmt_date(a.get("event_date")) if a.get("event_date") else "",
        "area": a.get("area") or "", "package": a.get("package") or "Decor",
        "age": age or "", "theme": a.get("theme") or "", "colours": dt.get("colours") or "",
        "times": {"handover": fmt_time(a.get("handover")), "ready": fmt_time(dt.get("ready_by") or a.get("event_time")),
                  "packup": fmt_time(a.get("packup"))},
        "venue": a.get("venue") or "", "floor": dt.get("floor") or "", "venue_notes": dt.get("venue_notes") or "",
        "maps": a.get("maps") or "",
        "pictures": pics,
        "components": [{"label": c["label"], "qty": c.get("qty") or "", "notes": c.get("notes") or ""}
                       for c in dt.get("components") or [] if c.get("on")],
        "custom_requests": dt.get("custom_requests") or "", "name_request": name_req,
        "bring": bring, "ours": dt.get("ours") or [],
        "pickup_location": dt.get("pickup_location") or "", "pickup_by": dt.get("pickup_by") or "",
        "returns": dt.get("returns") or [],
        "amount": _inr(dt.get("amount")) if dt.get("amount") is not None else "",
        "coordinator_name": dt.get("coordinator_name") or "", "coordinator_phone": dt.get("coordinator_phone") or "",
        "photos": [{"slot": p["slot"], "label": p["label"], "hint": p.get("hint") or "", "type": _box_type(p),
                    "url": _img_url(done[p["slot"]]["token"]) if p["slot"] in done else None}
                   for p in dt.get("photos") or []],
        "approved": bool(card.get("approved_at")),
    }


def message_of(v: dict, link: str) -> str:
    """The short WhatsApp text the team copy-pastes (with the image)."""
    t = v["times"]
    L = [f"*{v['title']}*"]
    sub = " · ".join(x for x in [f"Age {v['age']}" if v["age"] else "", v["theme"]] if x)
    if sub:
        L.append(sub)
    L.append("")
    if t["handover"]:
        L.append(f"Handover: {t['handover']}")
    if t["ready"]:
        L.append(f"*Ready by: {t['ready']}*")
    if t["packup"]:
        L.append(f"Packup: {t['packup']}")
    L.append("")
    venue = ", ".join(x for x in [v["venue"], v["floor"]] if x)
    if venue:
        L.append(f"Venue: {venue}")
    if v["maps"]:
        L.append(f"Map: {v['maps']}")
    if v["bring"]:
        L += ["", "You bring: " + ", ".join(v["bring"])]
    if v["ours"]:
        pick = f"Pick up {', '.join(v['ours'])}"
        where = " ".join(x for x in [f"from {v['pickup_location']}" if v["pickup_location"] else "",
                                     f"before {v['pickup_by']}" if v["pickup_by"] else ""] if x)
        L.append(pick + (f" {where}" if where else ""))
    if v["returns"]:
        L.append("Give back after party: " + ", ".join(
            (f"{r['qty']} " if r.get("qty") else "") + r["item"] for r in v["returns"]))
    L.append("")
    if v["amount"]:
        L.append(f"Amount: {v['amount']}")
    if v["coordinator_name"] or v["coordinator_phone"]:
        L.append("Coordinator: " + " ".join(x for x in [v["coordinator_name"], v["coordinator_phone"]] if x))
    has_video = any(p.get("type") == "video" for p in v.get("photos") or [])
    L += ["", "Full details + send photos" + (" & video:" if has_video else ":"), link]
    out, prev = [], None
    for ln in L:   # no double blank lines
        if ln == "" and prev == "":
            continue
        out.append(ln)
        prev = ln
    return "\n".join(out).strip()


# ─── storage helpers ──────────────────────────────────────────────────────

def _card_dict(r) -> dict:
    d = dict(r)
    d["data"] = _j(d.get("data"), {})
    d["auto"] = _j(d.get("auto"), {})
    return d


async def _card_by_lead(lead_id: int) -> Optional[dict]:
    r = await database.fetch_one("SELECT * FROM decor_job_cards WHERE lead_id = :id", values={"id": lead_id})
    return _card_dict(r) if r else None


async def _card_by_token(token: str) -> Optional[dict]:
    if not token or len(token) < 16 or len(token) > 64:
        return None
    r = await database.fetch_one("SELECT * FROM decor_job_cards WHERE token = :t", values={"t": token})
    return _card_dict(r) if r else None


async def _photos(card_id: int) -> List[dict]:
    rows = await database.fetch_all(
        "SELECT id, kind, slot, token, size_bytes, source, uploaded_by, uploaded_at FROM decor_job_photos "
        "WHERE card_id = :c ORDER BY kind, uploaded_at", values={"c": card_id})
    return [dict(r) for r in rows]


async def _decor_partner_row(lead_id: int) -> Optional[dict]:
    """The Decor row from Partners & Expenses, if any — decorator + amount."""
    try:
        r = await database.fetch_one(
            "SELECT person_name, amount FROM event_team WHERE lead_id = :id AND role ILIKE 'decor%' "
            "ORDER BY sort_order, id LIMIT 1", values={"id": lead_id})
    except Exception:
        return None
    return {"partner": r["person_name"], "amount": float(r["amount"]) if r["amount"] is not None else None} if r else None


async def _store_photo(card: dict, kind: str, slot: str, raw: bytes, source: str, by: Optional[str]) -> dict:
    box = next((p for p in card["data"].get("photos") or [] if p.get("slot") == slot), None)
    want = _box_type(box) if kind == "done" else "photo"
    mime = _sniff(raw)
    if want == "video":
        if not mime or not mime.startswith("video/"):
            raise HTTPException(status_code=400, detail="Please send a video (MP4 / MOV).")
        if len(raw) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=413, detail="That video is too long. Please record 30 seconds or less.")
    else:
        if not mime or not mime.startswith("image/"):
            raise HTTPException(status_code=400, detail="Please send a photo (JPG, PNG or WEBP).")
        if len(raw) > MAX_IMG_BYTES:
            raise HTTPException(status_code=413, detail="That photo is too large.")
    token = secrets.token_urlsafe(18)
    await database.execute(
        """INSERT INTO decor_job_photos (card_id, kind, slot, token, image, image_type, size_bytes, source, uploaded_by)
           VALUES (:c, :k, :s, :t, :img, :mt, :n, :src, :by)
           ON CONFLICT (card_id, kind, slot) DO UPDATE SET token = EXCLUDED.token, image = EXCLUDED.image,
               image_type = EXCLUDED.image_type, size_bytes = EXCLUDED.size_bytes, source = EXCLUDED.source,
               uploaded_by = EXCLUDED.uploaded_by, uploaded_at = NOW()""",
        values={"c": card["id"], "k": kind, "s": slot, "t": token, "img": raw, "mt": mime, "n": len(raw),
                "src": source, "by": (by or "")[:80] or None})
    return {"url": _img_url(token)}


async def _admin_payload(lead_id: int, pw: Optional[str]) -> dict:
    card = await _card_by_lead(lead_id)
    live = await _auto_from_booking(lead_id, pw)
    partner = await _decor_partner_row(lead_id)
    if not card:
        data = default_data(live, partner)
        return {"card": None, "auto": live, "data": data, "decorator": (partner or {}).get("partner") or "",
                "title": title_of(live, data), "photos": [], "partner_row": partner}
    photos = await _photos(card["id"])
    v = view_of(card, photos)
    link = link_for(card["token"])
    return {
        "card": {"id": card["id"], "link": link, "updated_at": _to_ist_str(card.get("updated_at")),
                 "updated_by": card.get("updated_by"), "copied_at": _to_ist_str(card.get("copied_at")),
                 "opened_at": _to_ist_str(card.get("opened_at")),
                 "approved_at": _to_ist_str(card.get("approved_at")), "approved_by": card.get("approved_by")},
        "auto": live, "sent_auto": card["auto"], "data": card["data"], "decorator": card.get("decorator") or "",
        "title": v["title"], "view": v, "message": message_of(v, link),
        "photos": [{"kind": p["kind"], "slot": p["slot"], "url": _img_url(p["token"]), "source": p["source"],
                    "uploaded_by": p.get("uploaded_by"), "uploaded_at": _to_ist_str(p.get("uploaded_at"))}
                   for p in photos],
        "partner_row": partner,
        # booking changed since the card was saved -> the link still shows the old details
        "stale": any(str(live.get(k) or "") != str(card["auto"].get(k) or "")
                     for k in ("event_date", "event_time", "handover", "packup", "venue", "maps", "age",
                               "theme", "package", "area"))
                 or [p.get("url") for p in live.get("pictures") or []] != [p.get("url") for p in card["auto"].get("pictures") or []],
    }


# ─── admin endpoints ──────────────────────────────────────────────────────

class CardIn(BaseModel):
    decorator: Optional[str] = None
    data: dict = {}
    changed_by: Optional[str] = None


class ApproveIn(BaseModel):
    approved: bool = True
    by: Optional[str] = None


class RemoveIn(BaseModel):
    kind: str = "done"
    by: Optional[str] = None


@router.get("/admin/decor-job/{lead_id}")
async def admin_get(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    return await _admin_payload(lead_id, x_admin_password)


@router.post("/admin/decor-job/{lead_id}")
async def admin_save(lead_id: int, body: CardIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    live = await _auto_from_booking(lead_id, x_admin_password)
    data = clean_data(body.data)
    who = _s(body.changed_by, 80) or None
    card = await _card_by_lead(lead_id)
    if card:
        await database.execute(
            """UPDATE decor_job_cards SET decorator = :dec, data = :data, auto = :auto,
               updated_at = NOW(), updated_by = :by WHERE id = :id""",
            values={"id": card["id"], "dec": _s(body.decorator, 120) or None, "data": json.dumps(data),
                    "auto": json.dumps(live), "by": who})
    else:
        await database.execute(
            """INSERT INTO decor_job_cards (lead_id, token, decorator, data, auto, created_by, updated_at, updated_by)
               VALUES (:lid, :tok, :dec, :data, :auto, :by, NOW(), :by)
               ON CONFLICT (lead_id) DO UPDATE SET decorator = EXCLUDED.decorator, data = EXCLUDED.data,
                   auto = EXCLUDED.auto, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
            values={"lid": lead_id, "tok": secrets.token_urlsafe(24), "dec": _s(body.decorator, 120) or None,
                    "data": json.dumps(data), "auto": json.dumps(live), "by": who})
    return await _admin_payload(lead_id, x_admin_password)


@router.post("/admin/decor-job/{lead_id}/copied")
async def admin_copied(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("UPDATE decor_job_cards SET copied_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"ok": True}


@router.post("/admin/decor-job/{lead_id}/photo/{slot}")
async def admin_upload(lead_id: int, slot: str, image: UploadFile = File(...), kind: str = Form("done"),
                       uploaded_by: Optional[str] = Form(None), x_admin_password: Optional[str] = Header(None)):
    """The team adds a completion photo that came on WhatsApp (kind=done),
    or an extra decor reference picture (kind=ref, slot ref-1 / ref-2 / ref-3)."""
    _require_admin(x_admin_password)
    card = await _card_by_lead(lead_id)
    if not card:
        raise HTTPException(status_code=400, detail="Save the job card first.")
    kind = "ref" if kind == "ref" else "done"
    slot = re.sub(r"[^a-z0-9-]", "", slot.lower())[:40]
    if kind == "ref":
        if slot not in ("ref-1", "ref-2", "ref-3"):
            raise HTTPException(status_code=400, detail="Up to 3 extra reference pictures.")
    elif slot not in {p["slot"] for p in card["data"].get("photos") or []}:
        raise HTTPException(status_code=400, detail="That photo box isn't on the job card.")
    await _store_photo(card, kind, slot, await image.read(), "team", uploaded_by)
    return await _admin_payload(lead_id, x_admin_password)


@router.post("/admin/decor-job/{lead_id}/photo/{slot}/remove")
async def admin_remove_photo(lead_id: int, slot: str, body: RemoveIn, x_admin_password: Optional[str] = Header(None)):
    """Ask for a re-take (the box is empty again on the decorator's link), or
    drop an extra reference picture."""
    _require_admin(x_admin_password)
    card = await _card_by_lead(lead_id)
    if not card:
        raise HTTPException(status_code=404, detail="No job card yet.")
    await database.execute(
        "DELETE FROM decor_job_photos WHERE card_id = :c AND kind = :k AND slot = :s",
        values={"c": card["id"], "k": "ref" if body.kind == "ref" else "done", "s": slot})
    if body.kind != "ref" and card.get("approved_at"):
        await database.execute("UPDATE decor_job_cards SET approved_at = NULL, approved_by = NULL WHERE id = :id",
                               values={"id": card["id"]})
    return await _admin_payload(lead_id, x_admin_password)


@router.post("/admin/decor-job/{lead_id}/approve")
async def admin_approve(lead_id: int, body: ApproveIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    card = await _card_by_lead(lead_id)
    if not card:
        raise HTTPException(status_code=404, detail="No job card yet.")
    if body.approved:
        await database.execute("UPDATE decor_job_cards SET approved_at = NOW(), approved_by = :by WHERE id = :id",
                               values={"id": card["id"], "by": _s(body.by, 80) or None})
    else:
        await database.execute("UPDATE decor_job_cards SET approved_at = NULL, approved_by = NULL WHERE id = :id",
                               values={"id": card["id"]})
    return await _admin_payload(lead_id, x_admin_password)


# ─── decorator's link (no login — the token is the access) ────────────────

@router.get("/decor-job/img/{token}")
async def public_img(token: str, request: Request):
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail="Not found.")
    r = await database.fetch_one("SELECT image, image_type FROM decor_job_photos WHERE token = :t", values={"t": token})
    if not r:
        raise HTTPException(status_code=404, detail="Not found.")
    if str(r["image_type"]).startswith("video/"):   # Safari needs byte ranges to play a video
        from routers.venue_info import _range_response
        return _range_response(bytes(r["image"]), r["image_type"], request.headers.get("range"))
    return Response(content=bytes(r["image"]), media_type=r["image_type"],
                    headers={"Cache-Control": "public, max-age=604800"})


@router.get("/decor-job/{token}")
async def public_view(token: str):
    card = await _card_by_token(token)
    if not card:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    if not card.get("opened_at"):
        await database.execute("UPDATE decor_job_cards SET opened_at = NOW() WHERE id = :id", values={"id": card["id"]})
    return view_of(card, await _photos(card["id"]))


@router.post("/decor-job/{token}/photo/{slot}")
async def public_upload(token: str, slot: str, image: UploadFile = File(...)):
    card = await _card_by_token(token)
    if not card:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    if card.get("approved_at"):
        raise HTTPException(status_code=409, detail="Photos are already approved. Please call the coordinator.")
    if slot not in {p["slot"] for p in card["data"].get("photos") or []}:
        raise HTTPException(status_code=400, detail="Please refresh the page.")
    return await _store_photo(card, "done", slot, await image.read(), "decorator", card.get("decorator"))
