"""
Ops sheet for a booking — 2026-11-13, per Shruti (booking #1267: a decor note
Sidhant typed in the sales panel showed on the sales quote but not on the
booking's print, so the ops manager would have missed it):

  "instead of print on the booking page, can we have an ops sheet option
  where we list all options with comments, remarks, requests, T&C entered
  by the user?"

One printable page with everything ops needs, pulled live every time:
  * the booking's details, services and add-ons — the current value, the
    partner assigned and the booking remarks for each;
  * the sales panel's notes for each service (requirements.*.customization),
    read straight from the sales sheet, so edits made there after the lead
    was converted still show;
  * activities notes, to-be-confirmed items, event schedule, return gifts and
    delivery, the venue form (answers + photo/video count), the customer's own
    remarks from the website, notes / special instructions, T&C agreed by
    sales, and the money summary.

GET /api/admin/bookings/{lead_id}/ops-sheet   -> HTML (X-Admin-Password; sales login allowed)
"""
import html
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse

from database import database

logger = logging.getLogger(__name__)
router = APIRouter()

IST = timedelta(hours=5, minutes=30)
SKIP_VALUES = {"", "no", "no selection", "none", "0", "—", "-", "not selected", "no packaging"}

# Sales-panel requirement keys -> label shown on the sheet.
REQ_LABELS = [
    ("decor", "Decor"), ("host", "Host"), ("music", "Music"), ("photographer", "Photographer"),
    ("einvite_type", "E-Invite"), ("save_the_date", "Save the Date"), ("pinata_type", "Piñata"),
    ("pinata_bags", "Piñata bags"), ("cake", "Cake"), ("activity_notes", "Activities"),
    ("return_gifts", "Return gifts"), ("packaging", "Gift packaging"), ("return_gift_tags", "Gift tags"),
    ("rentals", "Tables & chairs"), ("physical_invites", "Physical invites"),
    ("host_gifts", "Host gifts"), ("pinata_fillings", "Piñata fillings"),
]


def _e(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _j(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def _nl(v) -> str:
    return _e(v).replace("\n", "<br>")


SITE = "https://www.wondershopexperiences.com/"


async def _decor_photo(lead_id: int, decor_val, sales_decor) -> Optional[str]:
    """Decor photo for the sheet: the customer's uploaded reference picture
    first, then the booked decor's catalogue photo, then the sales panel's
    tier/theme photo. None when nothing fits; never raises."""
    try:
        from routers.decor_refs import current_for_lead
        ref = await current_for_lead(lead_id)
        if ref and ref.get("image_url"):
            return ref["image_url"]
    except Exception:
        logger.exception(f"Lead #{lead_id}: ops sheet couldn't read the decor reference")
    try:
        import catalogue_data as cat
        from urllib.parse import quote
        path = None
        if decor_val:
            from routers.admin import _resolve_decor_override
            o = _resolve_decor_override(decor_val) or {}
            r = cat.resolve_decor(o.get("id"), o.get("p")) if o.get("id") else None
            path = r and r.get("image_path")
        if not path and sales_decor:
            path = cat.resolve_decor_image_by_name((sales_decor.get("theme_name") or "").strip() or None, sales_decor.get("selected"))
        return (SITE + quote(path)) if path else None
    except Exception:
        logger.exception(f"Lead #{lead_id}: ops sheet couldn't resolve the decor photo")
        return None


def _has(v) -> bool:
    return str(v or "").strip().lower() not in SKIP_VALUES


@router.get("/admin/bookings/{lead_id}/ops-sheet", response_class=HTMLResponse)
async def ops_sheet(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    from routers.admin import _require_admin, get_booking_detail
    from routers.sales_leads import _fmt_time_12h
    _require_admin(x_admin_password)
    d = await get_booking_detail(lead_id, x_admin_password)
    lead = dict(await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id}))
    pb = None
    try:
        pb = await database.fetch_one("SELECT * FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
        pb = dict(pb) if pb else None
    except Exception:
        logger.exception(f"Lead #{lead_id}: ops sheet couldn't read the sales sheet")
    reqs = (_j(pb.get("requirements")) if pb else None) or {}

    secs = {s["section"]: s["fields"] for s in d.get("sections") or []}
    fields = {f["field_key"]: f for fl in secs.values() for f in fl}

    def val(k):
        f = fields.get(k) or {}
        if f.get("removed"):
            return None
        v = f.get("assigned_value") if f.get("is_direct_write") and f.get("assigned_value") else f.get("customer_choice")
        return (str(v).strip() or None) if v is not None else None

    def t12(k):
        v = val(k)
        return (_fmt_time_12h(v) or v) if v else None

    out = []
    # ── header ──
    child = val("child_names") or ""
    ages = val("child_ages") or ""
    title = f"{child.split(',')[0].strip()}'s Birthday" if child else "Birthday party"
    now = (datetime.utcnow() + IST).strftime("%d %b %Y, %I:%M %p")
    out.append(f"<h1>Ops sheet · Booking #{lead_id}</h1><div class='sub'>{_e(title)} · {_e(d.get('status') or '')}"
               f" · generated {now} IST</div>")

    def kv_table(rows):
        rows = [(k, v) for k, v in rows if v not in (None, "")]
        if not rows:
            return ""
        return "<table class='kv'>" + "".join(f"<tr><th>{_e(k)}</th><td>{v}</td></tr>" for k, v in rows) + "</table>"

    def kv_grid(rows):
        """Two columns of label/value pairs (2026-11-13: saves space at the top)."""
        rows = [(k, v) for k, v in rows if v not in (None, "")]
        if not rows:
            return ""
        return "<div class='kv2'>" + "".join(f"<div class='kvi'><span>{_e(k)}</span><b>{v}</b></div>" for k, v in rows) + "</div>"

    maps = val("venue_maps_link")
    _ed = val("event_date")
    try:
        _ed = datetime.strptime(_ed[:10], "%Y-%m-%d").strftime("%a, %d %b %Y") if _ed else _ed
    except ValueError:
        pass
    out.append("<h2>Event &amp; customer</h2>" + kv_grid([
        ("Event date", _e(_ed)), ("Event time", _e(t12("event_time"))),
        ("Venue handover", _e(t12("venue_handover_time") or "To be confirmed")),
        ("Packup", _e(t12("packup_time") or "To be confirmed")),
        ("Venue", _e(val("venue")) + (f" · <a href='{_e(maps)}'>Map</a>" if maps else "")),
        ("Venue type", _e(val("location_type"))), ("Pincode / city", _e(" · ".join(x for x in [val("pincode"), val("city")] if x))),
        ("Parent", _e(val("parent_name"))), ("Phone", _e(val("phone"))), ("Email", _e(val("email"))),
        ("On-site contact", _e(" · ".join(x for x in [val("venue_contact_name"), val("venue_contact_phone")] if x))),
        ("Birthday child", _e(child + (f" (turning {ages})" if ages else ""))), ("Kids", _e(val("kids_count"))),
        ("Theme", _e(val("theme"))), ("Sales lead", _e(lead.get("event_sales_lead"))),
        ("Lead source", _e(lead.get("lead_source"))),
    ]))

    # ── services & add-ons: value | partner | booking remarks | sales notes ──
    req_note = {}
    for k, lbl in REQ_LABELS:
        c = (reqs.get(k) or {}).get("customization") if isinstance(reqs.get(k), dict) else None
        if c and str(c).strip():
            req_note[k] = str(c).strip()
    decor_img = await _decor_photo(lead_id, val("svc_decor"), reqs.get("decor") if isinstance(reqs.get("decor"), dict) else None)
    # Every service / add-on is listed, selected or not (2026-11-13, per
    # Shruti: "so that our team knows that they have not selected").
    F = {f["field_key"]: f for sec in ("Services", "Add-ons") for f in (secs.get(sec) or [])}

    def part(k, sub=None):
        """(selection, partner, remark) for one booking field, or None when empty."""
        f = F.get(k)
        if not f or f.get("removed"):
            return None
        v, partner, rm = f.get("customer_choice"), f.get("assigned_value"), f.get("remarks")
        if k == "addon_custom":   # JSON [{"name","price"}]
            items = _j(v) or []
            v = ", ".join(f"{x.get('name')} (₹{x.get('price')})" for x in items if isinstance(x, dict) and x.get("name")) or None
        if not (_has(v) or _has(partner) or _has(rm)):
            return None
        sel = (f"{_e(sub)}: " if sub else "") + (_nl(v) if _has(v) else "—")
        return sel, (_e(partner) if _has(partner) else ""), (_nl(rm) if _has(rm) else "")

    def sreq(k):
        r = reqs.get(k)
        x = (r.get("selected") if isinstance(r, dict) else None)
        return str(x).strip() if _has(x) else None

    NS = "<span class='ns'>Not selected</span>"
    rows = []

    def notes_for(*keys):
        return [req_note[k] for k in keys if k in req_note]

    def row(label, parts, always=True, extra=None, pic="", notes=()):
        parts = [x for x in parts if x]
        notes = [n for n in notes if n]
        if not parts and not notes and not always:
            return
        if parts:
            sel = "<br>".join(x[0] for x in parts)
            partner = "<br>".join(x[1] for x in parts if x[1])
            rm = "<br>".join(x[2] for x in parts if x[2])
        else:
            sel, partner, rm = NS, "", ""
        if extra:
            sel += "".join(f"<div class='xsub'>{x}</div>" for x in extra)
        # sales panel notes for this section, read live (2026-11-13)
        sel += "".join(f"<div class='note'>📝 <b>Sales:</b> {_nl(n)}</div>" for n in notes)
        rows.append(f"<tr{'' if parts else ' class=nsr'}><td class='lbl'>{_e(label)}</td><td>{sel}{pic if parts else ''}</td>"
                    f"<td>{partner}</td><td>{rm}</td></tr>")

    def sales_part(k, sub=None):
        x = sreq(k)
        return ((f"{_e(sub)}: " if sub else "") + _e(x) + " <span class='hint'>(sales panel)</span>", "", "") if x else None

    pic = f"<div><img class='dimg' src='{_e(decor_img)}' alt='Decor'></div>" if decor_img else ""
    row("Decor", [part("svc_decor")] + [part(k, l) for k, l in (
        ("addon_decor_cake_table", "Cake table"), ("addon_decor_age_light", "Age light"), ("addon_decor_cutouts", "Cutouts"),
        ("addon_decor_welcome", "Welcome arch + board"), ("addon_decor_welcome_board", "Welcome board"),
        ("addon_decor_welcome_arch", "Welcome arch"))], pic=pic, notes=notes_for("decor"))
    row("Host", [part("svc_host")], notes=notes_for("host"))
    sugg = [str(x.get("text")).strip() for x in (_j((pb or {}).get("new_activity_suggestions")) or [])
            if isinstance(x, dict) and str(x.get("text") or "").strip()]
    row("Activities", [part("svc_activities")], notes=notes_for("activity_notes")
        + (["Not in our list yet (to evaluate): " + ", ".join(sugg)] if sugg else []))
    row("Music", [part("svc_dj"), part("addon_dj_lights", "Lights"), part("addon_dj_smoke", "Smoke machine")], notes=notes_for("music"))
    row("Piñata", [part("svc_pinata")], notes=notes_for("pinata_type"))
    row("Photographer", [part("svc_photo")], notes=notes_for("photographer"))
    pk, nt, own = part("addon_gift_packaging"), part("addon_gift_note"), part("addon_gift_pack_qty", "Customer's own gifts to pack")
    row("Return gifts", [part("svc_gifts"), own], extra=[
        "Packaging: " + (pk[0] if pk else "No packaging"),
        "Personalised thank-you notes: " + (nt[0] if nt else "No"),
    ] + [x for x in ((pk[2] if pk else ""), (nt[2] if nt else "")) if x],
        notes=notes_for("return_gifts", "packaging", "return_gift_tags"))
    row("E-Invite", [part("svc_einvite")], notes=notes_for("einvite_type", "save_the_date"))
    row("Cake", [part("svc_cake"), part("svc_cake_price", "Price")], notes=notes_for("cake"))
    rows.append("<tr class='grp'><td colspan='4'>Add-ons</td></tr>")
    row("Tables", [part("addon_rent_tables"), part("addon_rent_table_cover", "Table cover")], notes=notes_for("rentals"))
    row("Chairs", [part("addon_rent_chairs", "Chiavari chairs"), part("addon_rent_kids_chairs", "Kids' crossback chairs")])
    row("Tables & chairs setup notes", [part("addon_rent_notes")], always=False)
    row("Host gifts", [sales_part("host_gifts")], notes=notes_for("host_gifts"))
    row("Piñata bags", [part("addon_pinata_bags") or sales_part("pinata_bags")], notes=notes_for("pinata_bags"))
    row("Piñata fillings", [part("addon_pinata_fillings") or sales_part("pinata_fillings")], notes=notes_for("pinata_fillings"))
    row("Physical invites", [part("addon_phys_inv_qty", "Quantity"), part("addon_phys_inv_notes", "Notes")],
        notes=notes_for("physical_invites"))
    row("Custom add-ons", [part("addon_custom")])
    rows.append("<tr class='grp'><td colspan='4'>Requests</td></tr>")
    for k, lbl in (("notes_special_instructions", "Special requests"), ("notes_changes_updates", "Last-minute changes")):
        x = val(k)
        sx = str((pb or {}).get(k) or "").strip()
        sales = (f"<div class='note'>📝 <b>Sales sheet:</b> {_nl(sx)}</div>" if sx and sx != (x or "").strip() else "")
        rows.append(f"<tr{'' if (x or sales) else ' class=nsr'}><td class='lbl'>{lbl}</td><td colspan='3'>"
                    f"{_nl(x) if x else '<span class=ns>None</span>'}{sales}</td></tr>")
    out.append("<h2>Services &amp; add-ons</h2><table class='grid'><tr><th>Item</th><th>Selection</th><th>Partner</th>"
               "<th>Booking remarks</th></tr>" + "".join(rows) + "</table>")

    if val("activities_notes"):
        out.append("<h2>Activity notes</h2><div class='box'>" + _nl(val("activities_notes")) + "</div>")
    tbc = d.get("to_be_confirmed") or []
    if tbc:
        out.append("<h2>To be confirmed</h2><ul>" + "".join(
            f"<li>{_e(t.get('label') or t.get('name'))} — {_e(t.get('status') or 'pending')}"
            f"{(' · ₹' + _e(t.get('price'))) if t.get('price') not in (None, '') else ''}</li>" for t in tbc) + "</ul>")

    sched = val("event_schedule_text")
    if sched:
        rows = []
        for line in sched.splitlines():
            if not line.strip():
                continue
            tm, _, item = line.partition("\t")
            tm, item = (tm.strip(), item.strip()) if item else ("", tm.strip())
            rows.append(f"<tr><td class='lbl'>{_e(_fmt_time_12h(tm) or tm)}</td><td>{_e(item)}</td></tr>")
        out.append("<h2>Event schedule</h2><table class='grid'>" + "".join(rows) + "</table>")

    # ── return gifts ──
    go = d.get("gift_order") or {}
    gd = kv_table([
        ("Gift order", _e(go.get("status_label")) + (f" · ₹{go.get('total'):,.0f}" if isinstance(go.get("total"), (int, float)) else "")),
        ("Delivery address", _e(lead.get("gift_delivery_address"))),
        ("Address type", _e(lead.get("gift_delivery_address_type"))),
        ("Maps link", (f"<a href='{_e(lead.get('gift_delivery_maps_link'))}'>Map</a>" if lead.get("gift_delivery_maps_link") else "")),
        ("Contact", _e(" · ".join(x for x in [lead.get("gift_delivery_contact"), lead.get("gift_delivery_contact_phone")] if x))),
        ("Required by", _e(lead.get("gift_required_by_date"))),
    ])
    if gd:
        out.append("<h2>Return gifts</h2>" + gd)

    # ── venue form ──
    try:
        from routers.venue_info import admin_get as _ven
        v = await _ven(lead_id, x_admin_password)
        answered = [r for r in v["rows"] if r.get("answer")]
        if not (v.get("updated_at") or v.get("media")):
            out.append("<h2>Venue details (customer form)</h2><p class='muted'>The customer hasn't filled the venue form yet"
                       " — share it from the booking page (Venue Details).</p>")
        elif answered or v.get("media"):
            out.append("<h2>Venue details (customer form)</h2><table class='kv'>" + "".join(
                f"<tr><th>{_e(r['label'])}</th><td>{_e(r['answer'])}</td></tr>" for r in answered) + "</table>"
                + (f"<p class='muted'>{len(v['media'])} venue photo(s)/video(s) on the booking page"
                   f"{' · tags: ' + _e(', '.join(sorted({t for m in v['media'] for t in m['tags']}))) if any(m['tags'] for m in v['media']) else ''}.</p>"
                   if v.get("media") else "")
                + (f"<p class='muted'>Still unanswered: {_e(', '.join(v['missing']))}</p>" if v.get("missing") else ""))
    except Exception:
        logger.exception(f"Lead #{lead_id}: ops sheet couldn't read the venue form")

    # ── customer requests, notes, T&C ──
    notes = [("Customer's remarks (website)", lead.get("remarks"))]   # special requests / changes are in the table above
    notes = [(k, x) for k, x in notes if x and str(x).strip()]
    if notes:
        out.append("<h2>Requests &amp; notes</h2>" + "".join(f"<h3>{_e(k)}</h3><div class='box'>{_nl(x)}</div>" for k, x in notes))
    tnc = val("terms_conditions") or (pb or {}).get("terms_conditions")
    out.append("<h2>Terms &amp; conditions</h2>"
               + (f"<h3>Agreed with the client (sales)</h3><div class='box'>{_nl(tnc)}</div>" if tnc else "")
               + "<p class='muted'>Standard T&amp;C: wondershopexperiences.com/terms.html</p>")

    # ── money ──
    bill = kv_table([
        ("Grand total", _e(val("bill_grand_total"))), ("Advance", _e(val("bill_advance"))),
        ("Balance due", _e(val("bill_balance"))), ("Payment status", _e(val("bill_payment_status"))),
    ])
    if bill:
        out.append("<h2>Billing</h2>" + bill)
    pe = [(k, val(k)) for k in ("post_event_missing_items", "post_event_client_feedback", "post_event_internal_notes")]
    if any(x for _k, x in pe):
        out.append("<h2>Post-event notes</h2>" + kv_table([(fields[k]["label"] if k in fields else k, _nl(x)) for k, x in pe]))

    css = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#2D2140;margin:0;padding:24px;font-size:13px}
.bar{position:sticky;top:0;background:#fff;padding:8px 0 12px;text-align:right}
.bar button{background:#E65A96;color:#fff;border:none;border-radius:8px;padding:9px 16px;font-weight:700;cursor:pointer}
h1{font-size:22px;margin:0}.sub{color:#6B6280;margin:2px 0 14px}
h2{font-size:15px;color:#6C4AB6;border-bottom:2px solid #EDE6FA;padding-bottom:4px;margin:20px 0 8px;break-after:avoid}
h3{font-size:12.5px;margin:10px 0 4px;color:#2D2140}
table{border-collapse:collapse;width:100%}
.kv th{text-align:left;width:190px;color:#6B6280;font-weight:600;padding:4px 8px;vertical-align:top}
.kv td{padding:4px 8px;vertical-align:top}
.grid th{background:#F7F3FF;text-align:left;padding:6px 8px;font-size:12px}
.grid td{border-top:1px solid #F0E9FA;padding:6px 8px;vertical-align:top}
.grid td.lbl{font-weight:700;white-space:nowrap}
.kv2{display:grid;grid-template-columns:1fr 1fr;gap:2px 22px}
.kvi{display:flex;gap:8px;padding:3px 0;border-bottom:1px dashed #F0E9FA;break-inside:avoid}
.kvi span{color:#6B6280;font-weight:600;min-width:110px;flex:none}.kvi b{font-weight:500}
.dimg{max-width:240px;max-height:170px;border-radius:8px;margin-top:6px;border:1px solid #EDE6FA;display:block}
.sn td{background:#FFFBF0}
.ns{color:#B0A6C2;font-style:italic}.nsr td.lbl{color:#9A90AD}
.grp td{background:#F7F3FF;font-weight:700;color:#6C4AB6;font-size:12px;padding:5px 8px}
.xsub{font-size:12px;color:#5B4F70;margin-top:3px}
.note{background:#FFF6E3;border-radius:6px;padding:4px 7px;margin-top:4px;color:#5B4B2A}
.hint{font-weight:400;color:#8B7FA0}
.box{background:#FBF9FF;border:1px solid #EDE6FA;border-radius:8px;padding:8px 10px;white-space:normal}
.muted{color:#8B7FA0}
a{color:#6C4AB6}
tr{break-inside:avoid}
@media print{.bar{display:none}body{padding:0}}
"""
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Ops sheet #{lead_id}</title>"
            f"<style>{css}</style></head><body><div class='bar'><button onclick='window.print()'>🖨 Print</button></div>"
            + "".join(out) + "</body></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
