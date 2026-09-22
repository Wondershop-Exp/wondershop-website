"""
Sales lead / event playbook module (2026-09-16).

The real flow, per Shruti:
  1. A sales team member logs into this module with the shared admin
     password (same as packaging.html / admin.html — _require_admin,
     reused from routers.admin) and registers a lead. That's a REAL row in
     `leads`, tagged lead_origin='sales_module' so it's distinguishable
     from the public website's submissions (lead_origin defaults to
     'website' for everything else). It shows up in admin.html's normal
     Leads tab like any other lead — nothing about the existing pipeline,
     search, or booking dashboard needs to change.
  2. Sales fills in client & event details (mapped onto existing `leads`
     columns wherever one already fits, see LEAD_FIELD_MAP below), event
     requirements + cost, the event schedule, and notes — everything
     sales-module-specific lives in lead_sales_playbook, one row per lead,
     linked by lead_id (same FK pattern packaging_lists.lead_id uses).
  3. Once the booking is confirmed, sales records the Grand Total and
     balance received (leads.client_budget / order_advance /
     payment_method — the exact columns admin.html's Billing & Rewards
     panel already reads) and sends the lead to ops. This reuses
     routers.admin._do_convert_lead — the exact same is_booking flip
     admin.html's "Converted" status performs — so the row moves into the
     Bookings tab exactly as it would from the website pipeline, and
     playbook_stage moves to 'sent_to_ops'.
  4. Ops (Shruti) fills in the rest of the playbook — a volunteer (and
     materials, where relevant) per chosen activity, who's doing decor /
     music, the lead volunteer, the general volunteer list, the ops lead
     — then marks playbook_stage -> 'ops_ready'.
  5. The finished playbook prints as an A4, 2-page sheet from
     sales-lead-print.html via the browser's own Print -> Save as PDF (no
     server-side PDF rendering) — same visual design as the
     Wondershop_Order_Lead_Form.docx template already in use, just
     populated from real data instead of blank.

See migrations/028_sales_lead_sheets.sql for the schema. Every endpoint
here is admin-password gated (there is no public/no-login surface in this
module, unlike packaging's staff share-links) — this is an internal sales
+ ops tool, per Shruti's description of how it's actually used.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import (
    _require_admin, _do_convert_lead,
    LEAD_STATUS_OPTIONS, NON_CONVERT_REASON_OPTIONS, NON_CONVERT_STATUSES,
)
from catalogue_data import (
    DECOR_TIER_META, THEMES, HOST_TIER_PRICES, DJ_TIER_PRICES,
    PHOTO_TIER_PRICES, PHOTO_TIER_FEATURES, PINATA_TIER_PRICES,
    PACKAGING_LABELS, ACTIVITIES, GIFTS, EINVITE_TIER_PRICES,
)

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


def _to_ist_str(dt) -> Optional[str]:
    if not dt:
        return None
    ist = dt + IST_OFFSET
    return ist.strftime("%d %b %Y, %I:%M %p") + " IST"


def _to_ts_ms(dt) -> Optional[float]:
    """Epoch milliseconds — used by the list view's client-side column
    sorting (created/last-modified), since the IST display string above
    isn't lexically sortable."""
    return dt.timestamp() * 1000 if dt else None


# ─── catalogue (real site pricing) ─────────────────────────────────────────
# Cross-checked directly against builder.html's own tier cards / filter
# chips (2026-09-16) rather than reusing earlier assumptions — see the
# comments below on each spot that turned out to disagree with the live
# site and was corrected.

MUSIC_LABELS = {"Classic": "Music Essential", "Premium": "Music Plus"}
MUSIC_ADDONS = [{"name": "Music Lights", "price": 1500}, {"name": "Smoke Machine", "price": 2000}]
# Photographer tier cards in builder.html display "Classic Package" /
# "Premium Package" / "Signature Package" — not the bare tier word.
PHOTO_LABELS = {"Classic": "Classic Package", "Premium": "Premium Package", "Signature": "Signature Package"}
# Return Gifts step's own "Filter by Type" chips (builder.html #s8) — the
# real categories, not a guessed utility/stationery split.
RETURN_GIFT_TYPES = ["Bags & Pouches", "Games", "Personalized", "Stationery", "Home & Lifestyle"]
# Decor tier order as Shruti asked for it on the sales form.
DECOR_TIER_ORDER = ["Classic", "Premium", "Signature", "Luxury"]
# Venue Type — same options + labels as builder.html's own Venue Type
# picker (#s0 venueGrid / checkout coVenueGrid), verified directly against
# the live markup (2026-09-16, per Shruti: "add venue type in event
# details (take options from website)").
VENUE_TYPES = [
    {"value": "Home", "label": "Home"},
    {"value": "Society Banquet", "label": "Banquet Hall"},
    {"value": "Club", "label": "Club / Resort"},
    {"value": "Restaurant", "label": "Restaurant"},
    {"value": "Outdoor", "label": "Outdoor"},
    {"value": "Other", "label": "Other"},
    {"value": "Not Decided", "label": "Not Decided Yet"},
]

# Return Gift Tags ("Personalised Thank You Note") pricing — mirrors
# builder.html's own TAG_NOTE_UNIT_PRICE / TAG_NOTE_MIN_QTY exactly
# (₹10/item, billed for at least 15 items even if fewer return gifts are
# ordered). This REPLACES an earlier GIFT_TAG_FEE=15 / free-above-₹35,000
# pair that was never actually checked against the live site despite a
# comment here claiming it had been — corrected 2026-09-16 per Shruti:
# "price for return gift tags... is not getting added — pick up the
# pricing from the website".
TAG_NOTE_UNIT_PRICE = 10
TAG_NOTE_MIN_QTY = 15

# Packaging (Paper Gift Bag / Gift Wrap / Both) — mirrors builder.html's
# own PACKAGING_UNIT_PRICE exactly. Quantity basis is the same return-gift
# quantity the tag-note price above uses (packagingQty() on the live
# site). Added 2026-09-16 alongside the return-gift-tags fix, per the same
# request ("...paper gift bag, gift wrap is not getting added").
PACKAGING_UNIT_PRICE = {"paper-bag": 35, "wrap": 30, "both": 60}

# Pinata add-ons — sales-only (no equivalent on the live customer site).
# Bags: flat ₹12/bag, one bag per child by default (kids_count), same
# per-child pattern activities already use — no manual quantity entry.
# (2026-09-16, per Shruti — two corrections in sequence: first "₹10/bag",
# then "₹150 for 15 bags, packs of 15", then finally "remove quantity
# from pinata bags, just charge 12 rs. per bag" — this is the final,
# current figure and it replaces the pack-of-15 model entirely.)
# Fillings have no fixed price yet — "team will confirm once we build the
# pinata - mention it on UI" — so that catalogue entry is note-only, with
# no unit price / cost field.
PINATA_BAG_UNIT_PRICE = 12


@router.get("/admin/sales-leads/catalogue")
async def get_catalogue(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    # Decor: tier is a plain pick list now (+ "Others") — cost is typed in
    # by the sales person, not auto-filled, since a real quote is often
    # negotiated off-tier. Reference prices are still sent along so the
    # frontend can show them as a hint. decor_themes is the named-design
    # picker ("select from an existing decor") sourced from the same THEMES
    # list the public builder uses.
    decor_tiers = [{"name": t, "price": DECOR_TIER_META[t]["price"]} for t in DECOR_TIER_ORDER if t in DECOR_TIER_META]
    decor_themes = [{"id": t["id"], "name": t["n"]} for t in THEMES]
    # Host: no tier dropdown anymore (Shruti — "remove dropdown, just keep
    # cost") — reference prices are still sent for the hint text next to
    # the free-entry cost field.
    host_reference = [{"name": tier, "price": price} for tier, price in HOST_TIER_PRICES.items()]
    # 2026-09-17, per Shruti — sales module e-invite section: "give an
    # option for video invite and save the date. charges same as the
    # website." Static/Video + Reminder pricing straight from
    # EINVITE_TIER_PRICES (see catalogue_data.py for where that's sourced
    # from). Save the Date isn't a real website item — Shruti confirmed it
    # has no fixed price and is quoted per-lead, so it's not in this list;
    # the frontend renders it as a plain cost-entry add-on instead.
    einvite_type = [{"name": name, "price": price} for name, price in EINVITE_TIER_PRICES.items()]
    music = [{"name": MUSIC_LABELS.get(tier, tier), "price": price} for tier, price in DJ_TIER_PRICES.items()]
    photographer = [
        {"name": PHOTO_LABELS.get(tier, tier), "price": price, "features": PHOTO_TIER_FEATURES.get(tier, [])}
        for tier, price in PHOTO_TIER_PRICES.items()
    ]
    # Pinata: builder.html's own card names ARE "Square Pinata" / "Circle
    # Pinata" / etc. verbatim — a previous draft of this endpoint shortened
    # them to "Square"/"Circle", which drifted from the live site. Fixed to
    # match exactly.
    pinata_type = [
        {"name": name, "price": price} for name, price in PINATA_TIER_PRICES.items()
    ] + [{"name": "Custom", "price": None, "note": "No fixed price — quote separately"}]
    # Packaging: real site labels + real site unit prices, plus a "None"
    # option — Shruti's sales form needs to record when a client doesn't
    # want packaging at all, which isn't a real builder.html choice but is
    # a real sales scenario (None carries no price).
    packaging = [
        {"id": pid, "label": label, "price": PACKAGING_UNIT_PRICE.get(pid)}
        for pid, label in PACKAGING_LABELS.items()
    ] + [{"id": "none", "label": "None", "price": None}]
    activities = [
        {"id": aid, "name": name, "price": price, "flat": flat}
        for aid, name, price, flat in ACTIVITIES
    ]
    return_gifts_catalogue = [{"id": gid, "name": name, "price": price} for gid, name, _img, price in GIFTS]

    return {
        "decor_tiers": decor_tiers,
        "decor_themes": decor_themes,
        "host_reference": host_reference,
        "music": music,
        "music_addons": MUSIC_ADDONS,
        "photographer": photographer,
        "einvite_type": einvite_type,
        "pinata_type": pinata_type,
        "packaging": packaging,
        "activities": activities,
        "return_gift_types": RETURN_GIFT_TYPES,
        "return_gifts_catalogue": return_gifts_catalogue,
        "return_gift_tags": {
            "unit_price": TAG_NOTE_UNIT_PRICE,
            "min_qty": TAG_NOTE_MIN_QTY,
            "note": f"₹{TAG_NOTE_UNIT_PRICE:.0f}/item, billed for at least {TAG_NOTE_MIN_QTY} items",
        },
        "pinata_bags": {
            "unit_price": PINATA_BAG_UNIT_PRICE,
            "note": f"₹{PINATA_BAG_UNIT_PRICE:.0f}/bag, one per child",
        },
        "pinata_fillings": {
            "note": "Price to be confirmed by the team once the pinata is built",
        },
        "cake_note": "Starting ₹1,850/kg (brochure)",
        # Same lead-status pipeline admin.html's Leads tab uses — lets the
        # sales list/detail views render an identical status dropdown +
        # non-conversion-reason picker (2026-09-16, per Shruti: "add a
        # button to update status ... same as admin module").
        "lead_status_options": LEAD_STATUS_OPTIONS,
        "non_convert_reason_options": NON_CONVERT_REASON_OPTIONS,
        "non_convert_statuses": sorted(NON_CONVERT_STATUSES),
        "venue_types": VENUE_TYPES,
    }


# ─── field mapping ──────────────────────────────────────────────────────────

# Client & event detail keys the frontend uses -> the real `leads` column.
# Reuses existing columns wherever one already fits (this is what makes a
# sales-module lead a first-class row in the same Leads/Bookings pipeline
# admin.html already runs) instead of shadowing them in a side table.
LEAD_FIELD_MAP = {
    "client_name": "parent_name",
    "mobile": "phone",
    "child_name": "child_names",
    "child_age": "child_ages",
    "child_gender": "child_genders",
    "event_date": "event_date",
    "event_start_time": "event_time",
    "venue": "venue",
    "theme": "theme",
    "kids_count": "kids_count",
    # 010_order_form.sql already added this column for exactly this purpose
    # ("Event Sales Lead") — reused rather than duplicated.
    "sales_lead_name": "event_sales_lead",
    # 2026-09-22, per Shruti bug report — "Total Agreed with Client" (and
    # its neighbouring balance/payment fields) looked editable like every
    # other field on the page but was never wired to save at all; see the
    # client_budget_manual column (migration 035) and the mirror-skip logic
    # in _full_detail() below for why a plain autosave alone wasn't enough.
    "client_budget": "client_budget",
    "order_advance": "order_advance",
    "payment_method": "payment_method",
}

# LEAD_FIELD_MAP keys whose target `leads` column is a real numeric type
# (kids_count is INTEGER) — coerced in patch_sheet() below since `fields`
# is untyped (Dict[str, Any]) and a raw JS input's .value arrives as a
# string, which Postgres's raw-SQL binding otherwise rejects outright.
NUMERIC_LEAD_FIELDS = {"kids_count"}

# Same defense-in-depth as NUMERIC_LEAD_FIELDS above, but for the two
# DECIMAL(10,2) money columns now editable via the generic PATCH (see
# LEAD_FIELD_MAP) — coerced with float(), not int(), since these carry
# paise.
NUMERIC_FLOAT_LEAD_FIELDS = {"client_budget", "order_advance"}

# Scalar fields that live on lead_sales_playbook (not on `leads`).
PLAYBOOK_SCALAR_FIELDS = [
    "event_end_time", "venue_handover_time", "packup_time", "venue_type",
    "notes_special_instructions", "notes_changes_updates",
    "volunteers_general", "lead_volunteer", "decor_assigned_to",
    "music_assigned_to", "ops_lead_name",
    "post_event_missing_items", "post_event_client_feedback", "post_event_internal_notes",
    # 2026-09-16, per Shruti: "add a t&c column, to be input by the
    # salesman - optional" — free text, saved via the same generic
    # saveField()/PATCH path as the notes fields above, section 6 (Confirm
    # Booking & Balance) on the frontend.
    "terms_conditions",
]


# ─── request/response models ───────────────────────────────────────────────

class SheetIn(BaseModel):
    created_by: str
    client_name: Optional[str] = None
    mobile: Optional[str] = None
    child_name: Optional[str] = None
    child_age: Optional[str] = None
    child_gender: Optional[str] = None
    event_date: Optional[str] = None
    event_start_time: Optional[str] = None
    event_end_time: Optional[str] = None
    venue: Optional[str] = None
    venue_handover_time: Optional[str] = None
    packup_time: Optional[str] = None
    kids_count: Optional[int] = None
    sales_lead_name: Optional[str] = None
    requirements: Optional[Dict[str, Any]] = None
    notes_special_instructions: Optional[str] = None
    notes_changes_updates: Optional[str] = None


class PatchIn(BaseModel):
    updated_by: str
    fields: Dict[str, Any] = {}                     # any subset of LEAD_FIELD_MAP / PLAYBOOK_SCALAR_FIELDS keys
    requirements: Optional[Dict[str, Any]] = None    # shallow-merged in, category by category
    event_schedule: Optional[list] = None            # full replace — [{"time","item"}]


class ActivityIn(BaseModel):
    updated_by: str
    id: Optional[str] = None
    name: str
    price: Optional[float] = None
    flat: Optional[bool] = None


class ActivityFieldIn(BaseModel):
    # ops filling in volunteer/materials against an already-chosen activity
    updated_by: str
    id: str
    volunteer: Optional[str] = None
    materials: Optional[str] = None


class ActivityRemoveIn(BaseModel):
    updated_by: str
    id: Optional[str] = None
    name: Optional[str] = None


class NewActivityIn(BaseModel):
    added_by: str
    text: str


class ConfirmBookingIn(BaseModel):
    updated_by: str
    grand_total: Optional[float] = None
    advance_received: Optional[float] = None
    payment_method: Optional[str] = None


class OpsReadyIn(BaseModel):
    updated_by: str


# ─── helpers ────────────────────────────────────────────────────────────────

async def _log(playbook_id: int, actor: str, action: str, detail: Optional[str] = None):
    await database.execute(
        "INSERT INTO lead_sales_playbook_log (playbook_id, actor, action, detail) VALUES (:pid, :actor, :action, :detail)",
        values={"pid": playbook_id, "actor": actor, "action": action, "detail": detail},
    )


async def _get_lead_row(lead_id: int):
    row = await database.fetch_one(
        "SELECT * FROM leads WHERE lead_id = :id AND lead_origin = 'sales_module'", values={"id": lead_id}
    )
    if not row:
        raise HTTPException(status_code=404, detail="This sales lead worksheet doesn't exist (or isn't a sales-module lead).")
    return row


async def _get_playbook_row(lead_id: int):
    row = await database.fetch_one("SELECT * FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
    if not row:
        raise HTTPException(status_code=404, detail="No playbook found for this lead.")
    return row


def _estimate_total(requirements: dict, activities: list, kids_count: Optional[int]) -> float:
    total = 0.0
    for r in (requirements or {}).values():
        if isinstance(r, dict) and r.get("cost") is not None:
            try:
                total += float(r["cost"])
            except (TypeError, ValueError):
                pass
        if isinstance(r, dict):
            for addon in (r.get("addons") or []):
                try:
                    total += float(addon.get("price") or 0)
                except (TypeError, ValueError):
                    pass
    for a in (activities or []):
        try:
            price = float(a.get("price") or 0)
        except (TypeError, ValueError):
            price = 0
        if a.get("flat"):
            total += price
        else:
            total += price * (kids_count or 1)
    return round(total, 2)


# ─── "completely blank" leads (2026-09-21, per Shruti) ───────────────────────
# "+ Register a lead" creates the row straight away, so a stray click leaves an
# empty lead behind. A lead may be deleted ONLY while nothing at all has been
# filled in — the check runs on the server, so a real lead can never be removed
# through this, whatever the page says.

def _has_content(v) -> bool:
    """True if a value holds anything a person could have entered. Numbers count
    (a typed 0 is still an entry) — callers that store a computed 0 (e.g.
    client_budget, which _full_detail keeps mirrored to the running estimate)
    handle that themselves."""
    if v is None or v is False:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, dict):
        return any(_has_content(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has_content(x) for x in v)
    return True


def _json_val(v):
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _is_blank_sheet(lead, pb) -> bool:
    lead, pb = dict(lead or {}), dict(pb or {})
    if not lead or not pb:
        return False
    if lead.get("is_booking") or lead.get("status") != "New":
        return False
    name = (lead.get("parent_name") or "").strip()
    if name and name != "New Sales Lead":
        return False
    # every field a salesperson can type into on the leads side
    for col in ("phone", "child_names", "child_ages", "child_genders", "event_date", "event_time",
                "venue", "theme", "kids_count", "event_sales_lead", "payment_method",
                "non_convert_reason", "non_convert_reason_other", "order_id", "converted_on"):
        if _has_content(lead.get(col)):
            return False
    # money columns: the page keeps client_budget mirrored to the running estimate
    # (0 when nothing is picked), so only a NON-zero amount counts as content.
    for col in ("client_budget", "order_advance"):
        v = lead.get(col)
        if v is not None and float(v) != 0:
            return False
    # …and on the playbook side
    if pb.get("playbook_stage") != "sales_intake" or pb.get("sent_to_ops_by") or pb.get("ops_ready_by"):
        return False
    for col in PLAYBOOK_SCALAR_FIELDS:
        if _has_content(pb.get(col)):
            return False
    for col in ("requirements", "activities", "new_activity_suggestions", "event_schedule"):
        if _has_content(_json_val(pb.get(col))):
            return False
    return True


async def _full_detail(lead_row) -> dict:
    lead = dict(lead_row)
    pb_row = await database.fetch_one("SELECT * FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead["lead_id"]})
    pb = dict(pb_row) if pb_row else {}

    reqs = pb.get("requirements")
    reqs = json.loads(reqs) if isinstance(reqs, str) else (reqs or {})
    acts = pb.get("activities")
    acts = json.loads(acts) if isinstance(acts, str) else (acts or [])
    sugg = pb.get("new_activity_suggestions")
    sugg = json.loads(sugg) if isinstance(sugg, str) else (sugg or [])
    sched = pb.get("event_schedule")
    sched = json.loads(sched) if isinstance(sched, str) else (sched or [])

    log_rows = []
    if pb.get("id"):
        log_rows = await database.fetch_all(
            "SELECT actor, action, detail, created_at FROM lead_sales_playbook_log WHERE playbook_id = :pid ORDER BY created_at DESC LIMIT 40",
            values={"pid": pb["id"]},
        )

    # 2026-09-17, per Shruti — "leads from sales module also tie into the
    # dashboard". They already did for lead/booking COUNTS (dashboard.py's
    # queries have no lead_origin filter), but revenue was invisible for any
    # sales lead that hadn't been confirmed yet: every dashboard revenue
    # figure (Weekly trend, Monthly Realized/Booked/Potential) reads
    # leads.client_budget, and confirm_booking() below is the ONLY place
    # that ever wrote it for a sales-module lead — so a warm, in-progress
    # sales lead's running total (decor + host + gifts + ... picked so far)
    # never reached client_budget, and showed up as ₹0 everywhere,
    # including the new potential-revenue-by-rep table. Keeping
    # client_budget mirrored to the live estimate here — the one chokepoint
    # every read AND every save path already returns through — fixes that
    # for every consumer at once, without touching each save endpoint
    # individually. Stops once a lead is a confirmed booking, so it never
    # overwrites the final Grand Total a sales rep deliberately typed in at
    # confirm-booking time.
    estimated_total = _estimate_total(reqs, acts, lead.get("kids_count"))
    if not lead.get("is_booking") and not lead.get("client_budget_manual"):
        stored_budget = float(lead["client_budget"]) if lead.get("client_budget") is not None else None
        if stored_budget != estimated_total:
            await database.execute(
                "UPDATE leads SET client_budget = :v WHERE lead_id = :id",
                values={"v": estimated_total, "id": lead["lead_id"]},
            )
            lead["client_budget"] = estimated_total

    out = {
        "lead_id": lead["lead_id"],
        "client_name": lead.get("parent_name"),
        "mobile": lead.get("phone"),
        "child_name": lead.get("child_names"),
        "child_age": lead.get("child_ages"),
        "child_gender": lead.get("child_genders"),
        "event_date": str(lead["event_date"]) if lead.get("event_date") else None,
        "event_start_time": lead.get("event_time"),
        "venue": lead.get("venue"),
        "theme": lead.get("theme"),
        "kids_count": lead.get("kids_count"),
        "sales_lead_name": lead.get("event_sales_lead"),
        "status": lead.get("status"),
        "is_booking": bool(lead.get("is_booking")),
        "is_blank": _is_blank_sheet(lead, pb),
        "non_convert_reason": lead.get("non_convert_reason"),
        "non_convert_reason_other": lead.get("non_convert_reason_other"),
        "client_budget": float(lead["client_budget"]) if lead.get("client_budget") is not None else None,
        "order_advance": float(lead["order_advance"]) if lead.get("order_advance") is not None else None,
        "payment_method": lead.get("payment_method"),

        "event_end_time": pb.get("event_end_time"),
        "venue_handover_time": pb.get("venue_handover_time"),
        "packup_time": pb.get("packup_time"),
        "venue_type": pb.get("venue_type"),
        "terms_conditions": pb.get("terms_conditions"),
        "requirements": reqs,
        "activities": acts,
        "new_activity_suggestions": sugg,
        "event_schedule": sched,
        "notes_special_instructions": pb.get("notes_special_instructions"),
        "notes_changes_updates": pb.get("notes_changes_updates"),
        "volunteers_general": pb.get("volunteers_general"),
        "lead_volunteer": pb.get("lead_volunteer"),
        "decor_assigned_to": pb.get("decor_assigned_to"),
        "music_assigned_to": pb.get("music_assigned_to"),
        "ops_lead_name": pb.get("ops_lead_name"),
        "post_event_missing_items": pb.get("post_event_missing_items"),
        "post_event_client_feedback": pb.get("post_event_client_feedback"),
        "post_event_internal_notes": pb.get("post_event_internal_notes"),

        "playbook_stage": pb.get("playbook_stage"),
        "sent_to_ops_by": pb.get("sent_to_ops_by"),
        "sent_to_ops_at": _to_ist_str(pb.get("sent_to_ops_at")),
        "ops_ready_by": pb.get("ops_ready_by"),
        "ops_ready_at": _to_ist_str(pb.get("ops_ready_at")),

        "created_by": pb.get("created_by"),
        "created_at": _to_ist_str(pb.get("created_at")),
        "updated_by": pb.get("updated_by"),
        "updated_at": _to_ist_str(pb.get("updated_at")),

        "estimated_total": estimated_total,

        "activity_log": [
            {"actor": r["actor"], "action": r["action"], "detail": r["detail"], "at": _to_ist_str(r["created_at"])}
            for r in log_rows
        ],
    }
    return out


# ─── list / create ──────────────────────────────────────────────────────────

@router.get("/admin/sales-leads")
async def list_sheets(search: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    where = "l.lead_origin = 'sales_module'"
    values: Dict[str, Any] = {}
    if search:
        where += " AND (l.parent_name ILIKE :q OR l.phone ILIKE :q OR l.child_names ILIKE :q)"
        values["q"] = f"%{search}%"
    rows = await database.fetch_all(
        f"""SELECT l.lead_id, l.parent_name, l.phone, l.event_date, l.is_booking, l.status,
                   l.child_ages, l.child_genders, l.client_budget,
                   p.id AS playbook_id, p.playbook_stage, p.created_by, p.created_at,
                   p.updated_by, p.updated_at, p.new_activity_suggestions
            FROM leads l
            JOIN lead_sales_playbook p ON p.lead_id = l.lead_id
            WHERE {where}
            ORDER BY p.updated_at DESC LIMIT 300""",
        values=values,
    )
    # Cheap pre-filter on what the list query already has, then the full check
    # on those few rows only.
    cand = [r["lead_id"] for r in rows
            if not r["is_booking"] and r["status"] == "New" and r["playbook_stage"] == "sales_intake"
            and not (r["phone"] or "").strip() and not r["event_date"]
            and (r["parent_name"] or "").strip() in ("", "New Sales Lead")]
    blank_ids = set()
    if cand:
        lrows = await database.fetch_all("SELECT * FROM leads WHERE lead_id = ANY(:ids)", values={"ids": cand})
        prows = await database.fetch_all("SELECT * FROM lead_sales_playbook WHERE lead_id = ANY(:ids)", values={"ids": cand})
        pmap = {p["lead_id"]: p for p in prows}
        blank_ids = {l["lead_id"] for l in lrows if _is_blank_sheet(l, pmap.get(l["lead_id"]))}
    out = []
    for r in rows:
        d = dict(r)
        sugg = d.get("new_activity_suggestions")
        sugg = json.loads(sugg) if isinstance(sugg, str) else (sugg or [])
        out.append({
            "lead_id": d["lead_id"],
            "client_name": d["parent_name"],
            "mobile": d["phone"],
            "child_age": d["child_ages"],
            "child_gender": d["child_genders"],
            "event_date": str(d["event_date"]) if d["event_date"] else None,
            # 2026-09-22, per Shruti — "show Total Agreed with Client in the
            # table, rename the field to Revenue Potential." Same value as
            # leads.client_budget on the detail page (auto-estimated until a
            # rep locks in a real figure — see client_budget_manual), just
            # surfaced on the list too so a rep doesn't have to open every
            # row to see it. Renamed here rather than duplicated under both
            # names, since it's the same number either way.
            "revenue_potential": float(d["client_budget"]) if d["client_budget"] is not None else None,
            "is_booking": bool(d["is_booking"]),
            "is_blank": d["lead_id"] in blank_ids,
            "status": d["status"],
            "playbook_stage": d["playbook_stage"],
            "created_by": d["created_by"],
            "created_at": _to_ist_str(d.get("created_at")),
            "created_at_ts": _to_ts_ms(d.get("created_at")),
            "updated_by": d["updated_by"],
            "updated_at": _to_ist_str(d.get("updated_at")),
            "updated_at_ts": _to_ts_ms(d.get("updated_at")),
            "pending_activity_suggestions": len(sugg),
        })
    return {"sheets": out}


@router.post("/admin/sales-leads")
async def create_sheet(body: SheetIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    created_by = body.created_by.strip()
    if not created_by:
        raise HTTPException(status_code=400, detail="Your name is required to register a lead.")

    lead_values = {
        "parent_name": (body.client_name or "").strip() or "New Sales Lead",
        "phone": (body.mobile or "").strip(),
        "child_names": body.child_name,
        "child_ages": body.child_age,
        "child_genders": body.child_gender,
        "event_date": body.event_date,
        "event_time": body.event_start_time,
        "venue": body.venue,
        "kids_count": body.kids_count,
        "event_sales_lead": body.sales_lead_name,
    }
    lead_id = await database.execute(
        """INSERT INTO leads
             (parent_name, phone, child_names, child_ages, child_genders, event_date, event_time,
              venue, kids_count, event_sales_lead, lead_origin, lead_source, status, is_booking)
           VALUES
             (:parent_name, :phone, :child_names, :child_ages, :child_genders, :event_date, :event_time,
              :venue, :kids_count, :event_sales_lead, 'sales_module', 'Sales Team', 'New', FALSE)
           RETURNING lead_id""",
        values=lead_values,
    )

    playbook_id = await database.execute(
        """INSERT INTO lead_sales_playbook
             (lead_id, requirements, event_end_time, venue_handover_time, packup_time,
              notes_special_instructions, notes_changes_updates, created_by)
           VALUES
             (:lead_id, :requirements, :event_end_time, :venue_handover_time, :packup_time,
              :notes_special_instructions, :notes_changes_updates, :created_by)
           RETURNING id""",
        values={
            "lead_id": lead_id,
            "requirements": json.dumps(body.requirements or {}),
            "event_end_time": body.event_end_time,
            "venue_handover_time": body.venue_handover_time,
            "packup_time": body.packup_time,
            "notes_special_instructions": body.notes_special_instructions,
            "notes_changes_updates": body.notes_changes_updates,
            "created_by": created_by,
        },
    )
    await _log(playbook_id, created_by, "created")
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


@router.get("/admin/sales-leads/{lead_id}")
async def get_sheet(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead_row = await _get_lead_row(lead_id)
    return await _full_detail(lead_row)


class DeleteBlankIn(BaseModel):
    updated_by: str = ""


@router.post("/admin/sales-leads/{lead_id}/delete-blank")
async def delete_blank_sheet(lead_id: int, body: DeleteBlankIn, x_admin_password: Optional[str] = Header(None)):
    """Removes a lead that was registered by mistake — refuses (409) unless it is
    still completely blank. Nothing else can be deleted through this."""
    _require_admin(x_admin_password)
    lead_row = await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    if not _is_blank_sheet(lead_row, pb_row):
        raise HTTPException(
            status_code=409,
            detail="This lead has details filled in, so it can't be deleted here. "
                   "Set its status to Not Interested instead if you no longer need it.",
        )
    try:
        async with database.transaction():
            # the edit-trail rows go with the playbook (ON DELETE CASCADE)
            await database.execute("DELETE FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
            await database.execute("DELETE FROM leads WHERE lead_id = :id AND lead_origin = 'sales_module'", values={"id": lead_id})
    except Exception as exc:  # something else still points at this lead — leave everything as it was
        logger.warning(f"Blank sales lead {lead_id} could not be deleted: {exc}")
        raise HTTPException(status_code=409, detail="This lead is linked to other records, so it can't be deleted.")
    logger.info(f"Blank sales lead #{lead_id} deleted by {(body.updated_by or 'someone').strip() or 'someone'}")
    return {"ok": True, "lead_id": lead_id}


# ─── update ──────────────────────────────────────────────────────────────

@router.patch("/admin/sales-leads/{lead_id}")
async def patch_sheet(lead_id: int, body: PatchIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead_row = await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"

    lead_sets, lead_values = [], {"id": lead_id}
    pb_sets, pb_values = [], {"id": lead_id}
    changed = []

    for key, val in body.fields.items():
        if key in LEAD_FIELD_MAP:
            col = LEAD_FIELD_MAP[key]
            # `fields` is Dict[str, Any] with no per-key type coercion —
            # a value straight from a JS `<input type="number">` (whose
            # .value is always a string) was going straight into a raw
            # SQL UPDATE against an INTEGER column and failing Postgres's
            # type check with an unhandled 500. Confirmed live: PATCHing
            # kids_count="7" (string) 500'd, kids_count=7 (number) worked.
            # 2026-09-16, per Shruti: "#kids gets refreshed and that no.
            # is not updated in return gifts or activities" — this was the
            # actual cause (the frontend fix sends a real number now too;
            # this is defense-in-depth against the same bug recurring).
            if key in NUMERIC_LEAD_FIELDS and val is not None:
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"{key} must be a number")
            elif key in NUMERIC_FLOAT_LEAD_FIELDS and val is not None:
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"{key} must be a number")
            lead_sets.append(f"{col} = :{col}")
            lead_values[col] = val
            changed.append(key)
            # A sales rep deliberately saving a Total Agreed with Client
            # figure (even null, to clear it) takes it out of the
            # live-estimate mirror in _full_detail() — see migration 035.
            if key == "client_budget":
                lead_sets.append("client_budget_manual = :cbm")
                lead_values["cbm"] = val is not None
        elif key in PLAYBOOK_SCALAR_FIELDS:
            pb_sets.append(f"{key} = :{key}")
            pb_values[key] = val
            changed.append(key)

    if body.requirements:
        # 2026-09-16 — was "requirements || :req_patch::jsonb". SQLAlchemy's
        # text() bind-param parser (which `databases` compiles every raw
        # query through — see _build_query() in databases/core.py) doesn't
        # recognise a :name immediately followed by a Postgres :: cast; it
        # raised "This text() construct doesn't define a bound parameter
        # named 'req_patch'" on every call, an unhandled exception that
        # showed up in the browser as a bare "Failed to fetch" (same failure
        # shape as the missing-column bugs elsewhere in this app, which is
        # what made it look like the same root cause — it isn't). Verified
        # directly against the pinned sqlalchemy==2.0.30 from requirements.txt.
        # CAST(:x AS JSONB) is semantically identical and parses cleanly.
        pb_sets.append("requirements = requirements || CAST(:req_patch AS JSONB)")
        pb_values["req_patch"] = json.dumps(body.requirements)
        changed.extend(f"requirements.{k}" for k in body.requirements.keys())

    if body.event_schedule is not None:
        pb_sets.append("event_schedule = CAST(:sched AS JSONB)")
        pb_values["sched"] = json.dumps(body.event_schedule)
        changed.append("event_schedule")

    if lead_sets:
        await database.execute(f"UPDATE leads SET {', '.join(lead_sets)} WHERE lead_id = :id", values=lead_values)

    if pb_sets:
        pb_sets.append("updated_by = :by")
        pb_sets.append("updated_at = NOW()")
        pb_values["by"] = by
        await database.execute(f"UPDATE lead_sales_playbook SET {', '.join(pb_sets)} WHERE lead_id = :id", values=pb_values)
        await _log(pb_row["id"], by, "updated", detail=", ".join(changed) if changed else None)
    elif lead_sets:
        # lead-only change (e.g. client name) still needs to bump who/when on the playbook
        await database.execute(
            "UPDATE lead_sales_playbook SET updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
            values={"id": lead_id, "by": by},
        )
        await _log(pb_row["id"], by, "updated", detail=", ".join(changed) if changed else None)

    updated_lead = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(updated_lead)


@router.post("/admin/sales-leads/{lead_id}/activities")
async def add_activity(lead_id: int, body: ActivityIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"
    item = {"id": body.id or f"a{pb_row['id']}{int(datetime.utcnow().timestamp())}",
            "name": body.name.strip(), "price": body.price, "flat": bool(body.flat),
            "volunteer": None, "materials": None}
    await database.execute(
        # See the CAST(...) note above patch_sheet()'s requirements write —
        # same SQLAlchemy text()-vs-::cast bug, same fix.
        "UPDATE lead_sales_playbook SET activities = activities || CAST(:item AS JSONB), updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
        values={"id": lead_id, "item": json.dumps([item]), "by": by},
    )
    await _log(pb_row["id"], by, "activity_added", detail=item["name"])
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


@router.post("/admin/sales-leads/{lead_id}/activities/remove")
async def remove_activity(lead_id: int, body: ActivityRemoveIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"
    acts = pb_row["activities"]
    acts = json.loads(acts) if isinstance(acts, str) else (acts or [])
    kept = [a for a in acts if not (
        (body.id and a.get("id") == body.id) or (body.name and not body.id and a.get("name") == body.name)
    )]
    await database.execute(
        "UPDATE lead_sales_playbook SET activities = CAST(:acts AS JSONB), updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
        values={"id": lead_id, "acts": json.dumps(kept), "by": by},
    )
    await _log(pb_row["id"], by, "activity_removed", detail=body.name or body.id)
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


@router.post("/admin/sales-leads/{lead_id}/activities/field")
async def set_activity_field(lead_id: int, body: ActivityFieldIn, x_admin_password: Optional[str] = Header(None)):
    """Ops filling in a volunteer/materials against an already-chosen activity."""
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"
    acts = pb_row["activities"]
    acts = json.loads(acts) if isinstance(acts, str) else (acts or [])
    found = False
    for a in acts:
        if a.get("id") == body.id:
            if body.volunteer is not None:
                a["volunteer"] = body.volunteer
            if body.materials is not None:
                a["materials"] = body.materials
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="That activity isn't on this lead.")
    await database.execute(
        "UPDATE lead_sales_playbook SET activities = CAST(:acts AS JSONB), updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
        values={"id": lead_id, "acts": json.dumps(acts), "by": by},
    )
    await _log(pb_row["id"], by, "updated", detail=f"activity assignment: {body.id}")
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


@router.post("/admin/sales-leads/{lead_id}/new-activity")
async def suggest_new_activity(lead_id: int, body: NewActivityIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Enter what the activity is before submitting it.")
    by = body.added_by.strip() or "Someone"
    entry = {"text": text, "added_by": by, "added_on": datetime.utcnow().isoformat()}
    await database.execute(
        "UPDATE lead_sales_playbook SET new_activity_suggestions = new_activity_suggestions || CAST(:entry AS JSONB), "
        "updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
        values={"id": lead_id, "entry": json.dumps([entry]), "by": by},
    )
    await _log(pb_row["id"], by, "new_activity_suggested", detail=text)
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


# ─── workflow: confirm booking -> send to ops -> ops ready ─────────────────

@router.post("/admin/sales-leads/{lead_id}/confirm-booking")
async def confirm_booking(lead_id: int, body: ConfirmBookingIn, x_admin_password: Optional[str] = Header(None)):
    """Sales' final step: lock in the Grand Total / balance received, flip
    the lead to a confirmed booking (same is_booking conversion admin.html's
    "Converted" status runs), and hand it to ops."""
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"

    try:
        await _do_convert_lead(lead_id, by)
    except HTTPException as e:
        if e.status_code != 400:
            raise
        # already a confirmed booking — fine, this can be called again to
        # correct the billing fields without re-converting.

    lead_sets, lead_values = [], {"id": lead_id}
    if body.grand_total is not None:
        lead_sets.append("client_budget = :gt")
        lead_values["gt"] = body.grand_total
        lead_sets.append("client_budget_manual = :cbm2")
        lead_values["cbm2"] = True
    if body.advance_received is not None:
        lead_sets.append("order_advance = :adv")
        lead_values["adv"] = body.advance_received
    if body.payment_method:
        lead_sets.append("payment_method = :pm")
        lead_values["pm"] = body.payment_method
    if lead_sets:
        await database.execute(f"UPDATE leads SET {', '.join(lead_sets)} WHERE lead_id = :id", values=lead_values)

    # only move the stage forward — calling this again to fix a number
    # shouldn't undo ops having already started.
    if pb_row["playbook_stage"] == "sales_intake":
        await database.execute(
            "UPDATE lead_sales_playbook SET playbook_stage = 'sent_to_ops', sent_to_ops_by = :by, sent_to_ops_at = NOW(), "
            "updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
            values={"id": lead_id, "by": by},
        )
        await _log(pb_row["id"], by, "sent_to_ops")
    else:
        await database.execute(
            "UPDATE lead_sales_playbook SET updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
            values={"id": lead_id, "by": by},
        )
        await _log(pb_row["id"], by, "updated", detail="billing details updated")

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)


@router.post("/admin/sales-leads/{lead_id}/ops-ready")
async def mark_ops_ready(lead_id: int, body: OpsReadyIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get_lead_row(lead_id)
    pb_row = await _get_playbook_row(lead_id)
    by = body.updated_by.strip() or "Someone"
    if pb_row["playbook_stage"] == "sales_intake":
        raise HTTPException(status_code=400, detail="This lead hasn't been sent to ops yet.")
    await database.execute(
        "UPDATE lead_sales_playbook SET playbook_stage = 'ops_ready', ops_ready_by = :by, ops_ready_at = NOW(), "
        "updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
        values={"id": lead_id, "by": by},
    )
    await _log(pb_row["id"], by, "ops_ready")
    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    return await _full_detail(lead_row)
