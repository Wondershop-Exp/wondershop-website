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

    maps = val("venue_maps_link")
    _ed = val("event_date")
    try:
        _ed = datetime.strptime(_ed[:10], "%Y-%m-%d").strftime("%a, %d %b %Y") if _ed else _ed
    except ValueError:
        pass
    out.append("<h2>Event &amp; customer</h2>" + kv_table([
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
    svc_req = {"svc_decor": "decor", "svc_host": "host", "svc_dj": "music", "svc_photo": "photographer",
               "svc_einvite": "einvite_type", "svc_pinata": "pinata_type", "svc_cake": "cake",
               "svc_activities": "activity_notes", "svc_gifts": "return_gifts", "addon_gift_packaging": "packaging",
               "addon_gift_note": "return_gift_tags", "addon_rent_tables": "rentals", "addon_phys_inv_qty": "physical_invites",
               "addon_pinata_bags": "pinata_bags"}
    used_notes = set()
    rows = []
    for sec in ("Services", "Add-ons"):
        for f in secs.get(sec) or []:
            k = f["field_key"]
            if k in ("bill_line_quotes", "activities_notes") or f.get("removed"):
                continue
            v, partner, rm = f.get("customer_choice"), f.get("assigned_value"), f.get("remarks")
            if k == "addon_custom":   # JSON [{"name","price"}]
                items = _j(v) or []
                v = ", ".join(f"{x.get('name')} (₹{x.get('price')})" for x in items if isinstance(x, dict) and x.get("name")) or None
            rk = svc_req.get(k)
            note = req_note.get(rk) if rk else None
            if not (_has(v) or _has(partner) or _has(rm) or note):
                continue
            if rk:
                used_notes.add(rk)
            rows.append(f"<tr><td class='lbl'>{_e(f.get('label'))}</td><td>{_nl(v) if _has(v) else '—'}</td>"
                        f"<td>{_e(partner) if _has(partner) else ''}</td>"
                        f"<td>{_nl(rm) if _has(rm) else ''}{('<div class=note>📝 ' + _nl(note) + '</div>') if note else ''}</td></tr>")
    # sales notes for services not on the booking yet
    for k, lbl in REQ_LABELS:
        if k in req_note and k not in used_notes:
            rows.append(f"<tr><td class='lbl'>{_e(lbl)}</td><td>—</td><td></td><td><div class=note>📝 {_nl(req_note[k])}</div></td></tr>")
    out.append("<h2>Services &amp; add-ons</h2><table class='grid'><tr><th>Item</th><th>Selection</th><th>Partner</th>"
               "<th>Remarks &amp; notes <span class='hint'>(📝 = sales panel note)</span></th></tr>" + "".join(rows) + "</table>"
               if rows else "<h2>Services &amp; add-ons</h2><p class='muted'>Nothing selected.</p>")

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
    notes = [("Customer's remarks (website)", lead.get("remarks")),
             ("Notes / special instructions", val("notes_special_instructions")),
             ("Changes / last-minute updates", val("notes_changes_updates"))]
    notes = [(k, x) for k, x in notes if x and str(x).strip()]
    if notes:
        out.append("<h2>Requests &amp; notes</h2>" + "".join(f"<h3>{_e(k)}</h3><div class='box'>{_nl(x)}</div>" for k, x in notes))
    tnc = val("terms_conditions") or (pb or {}).get("terms_conditions")
    out.append("<h2>Terms &amp; conditions</h2>"
               + (f"<h3>Agreed with the client (sales)</h3><div class='box'>{_nl(tnc)}</div>" if tnc else "")
               + "<p class='muted'>Standard T&amp;C: wondershopexperiences.com/terms.html</p>")

    # ── money ──
    out.append("<h2>Billing</h2>" + kv_table([
        ("Grand total", _e(val("bill_grand_total"))), ("Advance", _e(val("bill_advance"))),
        ("Balance due", _e(val("bill_balance"))), ("Payment status", _e(val("bill_payment_status"))),
    ]))
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
