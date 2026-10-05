"""
Google Sheet sync: ONE row per lead/booking, kept up to date (2026-10-05).

Per Shruti: "let's do 1 row per lead/booking, for all types of leads/bookings
from any panel". Before this, the "Leads & Bookings" tab only ever got a row
appended when a customer submitted the website builder — sales-module leads,
Convert to Booking, status changes and admin edits never reached the sheet.

How it works
  * sync_lead_to_sheet(lead_id) reads the lead's CURRENT state from the
    database — through the same get_booking_detail() the admin page uses
    (every admin edit, override and live billing figure), or, for a sales-
    module lead that isn't a booking yet, the sales sheet (same lines and
    Estimated Total as the quotation PDF) — and posts it to the Apps Script
    webhook as action "upsert_lead": the script updates the row whose Lead ID
    matches, or appends one. A lead that no longer exists is sent as
    "delete_lead" so its row goes too.
  * schedule_sync(lead_id) is the fire-and-forget version used after every
    change (main.py's middleware calls it for every successful write to
    /api/admin/bookings/{id}/... and /api/admin/sales-leads/{id}...). Several
    saves within a couple of seconds collapse into one sync.
  * The row is keyed by column NAME, not position (see SHEET_FIELDS), so the
    script fills the right columns whatever order the sheet has. A value of
    None means "leave that cell as it is" (e.g. the scratch-card Reward
    Terms text, which only the website submission carries).

Never raises: a sheet hiccup must never break a save. Failures are logged.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx

from config import settings
from database import database

logger = logging.getLogger(__name__)

IST = timedelta(hours=5, minutes=30)
_pending: set = set()
_DEBOUNCE_SECONDS = 2.0


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _money(v) -> str:
    """'24875.00' / 24875.0 -> '24875'; keeps paise only when there are any."""
    if v in (None, ""):
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _s(v)
    return str(int(f)) if f.is_integer() else f"{f:.2f}"


def _ist(dt) -> str:
    if not dt:
        return ""
    try:
        return (dt + IST).strftime("%Y-%m-%d %H:%M:%S")
    except TypeError:
        return _s(dt)


async def _post(payload: dict) -> Optional[dict]:
    url = settings.GOOGLE_SHEET_WEBHOOK_URL
    if not url:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping sheet sync")
        return None
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.post(url, json=payload)
    try:
        body = r.json()
    except ValueError:
        body = {"success": False, "error": f"HTTP {r.status_code}, not JSON (is the Apps Script deployed?)"}
    if not body.get("success"):
        logger.error(f"Sheet sync {payload.get('action')} #{payload.get('lead_id')} failed: {body.get('error')}")
    return body


async def build_row(lead_id: int) -> Optional[Dict[str, Optional[str]]]:
    """The sheet row for this lead, keyed by sheet column name, or None if
    the lead doesn't exist (any more)."""
    # Lazy imports: routers import FROM modules like this one.
    from routers.admin import get_booking_detail
    from routers.leads import _theme_label, _music_label

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        return None
    lead = dict(lead_row)
    is_booking = bool(lead.get("is_booking"))
    is_sales = (lead.get("lead_origin") or "") == "sales_module"

    detail = await get_booking_detail(lead_id, settings.ADMIN_PASSWORD)
    fields = {f["field_key"]: f for sec in detail.get("sections") or [] for f in sec.get("fields") or []}

    def cur(key) -> str:
        """Current value of an admin field ("Current Value" column), blank if removed."""
        f = fields.get(key)
        if not f or f.get("removed"):
            return ""
        return _s(f.get("customer_choice"))

    dj = cur("svc_dj")
    einvite = cur("svc_einvite")
    services = {
        "Decor": cur("svc_decor"), "Pinata": cur("svc_pinata"), "Return Gifts": cur("svc_gifts"),
        # Admin stores the bare tier ("Classic") — show the name customers see.
        "Music": _music_label(dj) if dj in ("Classic", "Premium") else dj,
        "Host": cur("svc_host"), "Activities": cur("svc_activities"),
        "Photography": cur("svc_photo"), "E-Invite": "" if einvite == "No selection" else einvite,
    }
    grand_total, advance, balance = (_money(cur("bill_grand_total")), _money(cur("bill_advance")),
                                     _money(cur("bill_balance")))
    discount = _money(cur("bill_discount_pct"))
    if not discount and _money(cur("bill_discount_value")):
        discount = "₹" + _money(cur("bill_discount_value"))
    dj_lights, dj_smoke = cur("addon_dj_lights"), cur("addon_dj_smoke")
    remarks = _s(lead.get("remarks"))
    event_end = ""

    # A sales-module lead that isn't a booking yet lives in the sales sheet,
    # not in admin fields — use the same lines/total as its quotation PDF.
    if is_sales and not is_booking:
        from routers.sales_leads import _full_detail, _quotation_data
        sd = await _full_detail(lead_row)
        qd, _paths = _quotation_data(sd, datetime.utcnow())
        by_label = {s["label"]: s for s in qd["sections"]}

        def names(label):
            s = by_label.get(label)
            if not s or s.get("not_selected"):
                return ""
            out = []
            for ln in s["lines"]:
                n = ln["name"]
                if ln.get("price_text") and ln.get("price") is None:
                    n += f" ({ln['price_text'].lower()})"
                out.append(n)
            return ", ".join(out)

        services = {
            "Decor": names("Decor"), "Pinata": names("Pinata"), "Return Gifts": names("Return Gifts"),
            "Music": names("Music"), "Host": names("Host"), "Activities": names("Activities"),
            "Photography": names("Photographer"), "E-Invite": names("E-Invite"),
        }
        t = qd["totals"]
        grand_total = _s(round(t["estimate"]))
        discount = (f"{t['discount'] / t['subtotal'] * 100:.1f}".rstrip("0").rstrip(".")
                    if t.get("subtotal") and t.get("discount") and t["discount"] > 0 else "")
        advance = _money(sd.get("order_advance"))
        balance = ""
        music_addons = ", ".join(a.get("name") for a in ((sd.get("requirements") or {}).get("music") or {}).get("addons") or [] if a)
        dj_lights = "Yes" if "Music Lights" in music_addons else ""
        dj_smoke = "Yes" if "Smoke Machine" in music_addons else ""
        remarks = _s(sd.get("notes_special_instructions"))
        event_end = _s(sd.get("event_end_time"))

    reward_code = await database.fetch_val(
        "SELECT code FROM reward_codes WHERE issued_lead_id = :id ORDER BY issued_at DESC LIMIT 1", values={"id": lead_id})
    referral_code = await database.fetch_val(
        "SELECT code FROM referral_codes WHERE owner_lead_id = :id ORDER BY created_at DESC LIMIT 1", values={"id": lead_id})

    status = detail.get("status") or lead.get("status") or ""
    if is_booking:
        status = f"Booking – {status}"

    snap = lead.get("builder_snapshot")
    if snap is not None and not isinstance(snap, str):
        snap = json.dumps(snap)

    event_time = _s(lead.get("event_time"))
    if event_end:
        event_time = f"{event_time} – {event_end}" if event_time else event_end

    row: Dict[str, Optional[str]] = {
        "Lead ID": _s(lead_id),
        "Submitted At": _ist(lead.get("created_on")),
        "Status": status,
        "Parent Name": cur("parent_name") or _s(lead.get("parent_name")),
        "Phone": cur("phone") or _s(lead.get("phone")),
        "Email": cur("email") or _s(lead.get("email")),
        "Event Date": cur("event_date") or _s(lead.get("event_date")),
        "Kids Count": cur("kids_count") or _s(lead.get("kids_count")),
        "Child Names": cur("child_names") or _s(lead.get("child_names")),
        "Child Ages": cur("child_ages") or _s(lead.get("child_ages")),
        "Child Genders": cur("child_genders") or _s(lead.get("child_genders")),
        "Child DOBs": cur("child_dobs") or _s(lead.get("child_dobs")),
        # Website leads store the theme id ("uni") — show its name.
        "Theme": _theme_label(cur("theme") or lead.get("theme")) if (cur("theme") or lead.get("theme")) else "",
        "Venue": cur("venue") or _s(lead.get("venue")),
        "Venue Maps Link": cur("venue_maps_link"),
        "Venue Contact Name": cur("venue_contact_name"),
        "Venue Contact Phone": cur("venue_contact_phone"),
        "Location Type": cur("location_type"),
        "City": cur("city"),
        "Pincode": cur("pincode"),
        "Budget (₹)": _money(lead.get("client_budget")),
        "Grand Total (₹)": grand_total,
        "Discount %": discount,
        "Advance Paid (₹)": advance,
        "Balance Due (₹)": balance,
        "Reward Type": _s(lead.get("reward_type")),
        "Reward Label": _s(lead.get("reward_label")),
        "Reward Value (₹)": _money(lead.get("reward_value")),
        "Reward Terms": None,           # not stored in the DB — website submit fills it once (extra=)
        "Reward Expiry": _s(lead.get("reward_expiry")),
        "Reward Code Issued": _s(reward_code),
        "Coupon Code Redeemed": _s(lead.get("redeemed_coupon_code")),
        "Referral Code Issued": _s(referral_code),
        "Redeemed Reward Service": _s(lead.get("redeemed_reward_service")),
        "Remarks": remarks,
        "Lead Source": _s(lead.get("lead_source")) or ("Sales Team" if is_sales else ""),
        "Lead Source Detail": _s(lead.get("lead_source_detail")),
        "Referred By": _s(lead.get("referred_by")),
        "Gift Delivery Address": _s(lead.get("gift_delivery_address")),
        "Gift Delivery Maps Link": _s(lead.get("gift_delivery_maps_link")),
        "Gift Delivery Address Type": _s(lead.get("gift_delivery_address_type")),
        "Gift Delivery Contact": _s(lead.get("gift_delivery_contact")),
        "Gift Delivery Contact Phone": _s(lead.get("gift_delivery_contact_phone")),
        "Gift Required By Date": _s(lead.get("gift_required_by_date")),
        "DJ Lights Addon": dj_lights,
        "Smoke Machine Addon": dj_smoke,
        **services,
        "Cart Snapshot (JSON)": _s(snap),
        # Columns added 2026-10-05 (appended at the end of the sheet).
        "Record Type": "Booking" if is_booking else "Lead",
        "Origin": "Sales Team" if is_sales else "Website",
        "Event Time": event_time,
        "Sales Lead": _s(lead.get("event_sales_lead")),
        "Non-conversion Reason": " – ".join(filter(None, [_s(lead.get("non_convert_reason")),
                                                          _s(lead.get("non_convert_reason_other"))])),
        "Last Updated (IST)": _ist(datetime.utcnow()),
    }
    return row


async def sync_lead_to_sheet(lead_id: int, extra: Optional[dict] = None) -> Optional[dict]:
    """Upsert this lead's row now (or delete it if the lead is gone).
    extra: {column name: value} applied on top, e.g. {"Reward Terms": "..."}."""
    try:
        row = await build_row(lead_id)
        if row is None:
            return await _post({"action": "delete_lead", "lead_id": lead_id})
        if extra:
            row.update({k: v for k, v in extra.items() if v is not None})
        return await _post({"action": "upsert_lead", "lead_id": lead_id, "row": row})
    except Exception as exc:
        logger.exception(f"Sheet sync for lead #{lead_id} failed — {exc}")
        return None


async def _run_later(lead_id: int, delay: float):
    try:
        await asyncio.sleep(delay)
    finally:
        _pending.discard(lead_id)
    await sync_lead_to_sheet(lead_id)


def schedule_sync(lead_id: int, delay: float = _DEBOUNCE_SECONDS) -> None:
    """Fire-and-forget sync after a change; repeat calls within `delay`
    seconds collapse into one (it reads the latest state when it runs)."""
    if not settings.GOOGLE_SHEET_WEBHOOK_URL or lead_id in _pending:
        return
    _pending.add(lead_id)
    try:
        asyncio.get_running_loop().create_task(_run_later(lead_id, delay))
    except RuntimeError:
        _pending.discard(lead_id)


async def sync_all(lead_ids=None, prune: bool = True) -> dict:
    """Re-sync every lead (or the given ids), one by one. Used by the admin
    "Sync Google Sheet" button to fill/repair the sheet in one go. With
    prune, rows whose Lead ID isn't in the database any more are removed
    (only when syncing ALL leads)."""
    if lead_ids is None:
        rows = await database.fetch_all("SELECT lead_id FROM leads ORDER BY lead_id")
        lead_ids = [r["lead_id"] for r in rows]
    else:
        prune = False
    ok, failed = 0, []
    if prune:
        # Remove rows for leads that no longer exist (e.g. deleted test data).
        res = await _post({"action": "prune_leads", "keep_ids": [str(i) for i in lead_ids]})
        if not (res and res.get("success")):
            failed.append("prune")
    for lid in lead_ids:
        res = await sync_lead_to_sheet(lid)
        if res and res.get("success"):
            ok += 1
        else:
            failed.append(lid)
    return {"synced": ok, "failed": failed, "total": len(lead_ids)}
