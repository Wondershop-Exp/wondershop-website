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
from routers.admin import _require_admin, _do_convert_lead
from catalogue_data import (
    DECOR_TIER_META, THEMES, HOST_TIER_PRICES, DJ_TIER_PRICES,
    PHOTO_TIER_PRICES, PHOTO_TIER_FEATURES, PINATA_TIER_PRICES,
    PACKAGING_LABELS, ACTIVITIES, GIFTS,
)

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


def _to_ist_str(dt) -> Optional[str]:
    if not dt:
        return None
    ist = dt + IST_OFFSET
    return ist.strftime("%d %b %Y, %I:%M %p") + " IST"


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
    packaging = [{"id": pid, "label": label} for pid, label in PACKAGING_LABELS.items()]
    activities = [
        {"id": aid, "name": name, "price": price, "flat": flat}
        for aid, name, price, flat in ACTIVITIES
    ]
    return_gifts_catalogue = [{"id": gid, "name": name, "price": price} for gid, name, _img, price in GIFTS]

    threshold_row = await database.fetch_one(
        "SELECT config_value FROM platform_config WHERE config_key = 'gift_tag_free_threshold'"
    )
    fee_row = await database.fetch_one(
        "SELECT config_value FROM platform_config WHERE config_key = 'gift_tag_personalisation_fee'"
    )
    gift_tag_threshold = float(threshold_row["config_value"]) if threshold_row else 35000
    gift_tag_fee = float(fee_row["config_value"]) if fee_row else 15

    return {
        "decor_tiers": decor_tiers,
        "decor_themes": decor_themes,
        "host_reference": host_reference,
        "music": music,
        "music_addons": MUSIC_ADDONS,
        "photographer": photographer,
        "pinata_type": pinata_type,
        "packaging": packaging,
        "activities": activities,
        "return_gift_types": RETURN_GIFT_TYPES,
        "return_gifts_catalogue": return_gifts_catalogue,
        "return_gift_tags": {
            "fee_per_gift": gift_tag_fee,
            "free_at_or_above": gift_tag_threshold,
            "note": f"₹{gift_tag_fee:.0f}/gift below ₹{gift_tag_threshold:,.0f} order value, free at/above",
        },
        "cake_note": "Starting ₹1,850/kg (brochure)",
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
}

# Scalar fields that live on lead_sales_playbook (not on `leads`).
PLAYBOOK_SCALAR_FIELDS = [
    "event_end_time", "venue_handover_time", "packup_time",
    "notes_special_instructions", "notes_changes_updates",
    "volunteers_general", "lead_volunteer", "decor_assigned_to",
    "music_assigned_to", "ops_lead_name",
    "post_event_missing_items", "post_event_client_feedback", "post_event_internal_notes",
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
        "client_budget": float(lead["client_budget"]) if lead.get("client_budget") is not None else None,
        "order_advance": float(lead["order_advance"]) if lead.get("order_advance") is not None else None,
        "payment_method": lead.get("payment_method"),

        "event_end_time": pb.get("event_end_time"),
        "venue_handover_time": pb.get("venue_handover_time"),
        "packup_time": pb.get("packup_time"),
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

        "estimated_total": _estimate_total(reqs, acts, lead.get("kids_count")),

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
        f"""SELECT l.lead_id, l.parent_name, l.phone, l.child_names, l.event_date, l.is_booking, l.status,
                   p.id AS playbook_id, p.playbook_stage, p.created_by, p.updated_by, p.updated_at,
                   p.new_activity_suggestions
            FROM leads l
            JOIN lead_sales_playbook p ON p.lead_id = l.lead_id
            WHERE {where}
            ORDER BY p.updated_at DESC LIMIT 300""",
        values=values,
    )
    out = []
    for r in rows:
        d = dict(r)
        sugg = d.get("new_activity_suggestions")
        sugg = json.loads(sugg) if isinstance(sugg, str) else (sugg or [])
        out.append({
            "lead_id": d["lead_id"],
            "client_name": d["parent_name"],
            "mobile": d["phone"],
            "child_name": d["child_names"],
            "event_date": str(d["event_date"]) if d["event_date"] else None,
            "is_booking": bool(d["is_booking"]),
            "status": d["status"],
            "playbook_stage": d["playbook_stage"],
            "created_by": d["created_by"],
            "updated_by": d["updated_by"],
            "updated_at": _to_ist_str(d.get("updated_at")),
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
            lead_sets.append(f"{col} = :{col}")
            lead_values[col] = val
            changed.append(key)
        elif key in PLAYBOOK_SCALAR_FIELDS:
            pb_sets.append(f"{key} = :{key}")
            pb_values[key] = val
            changed.append(key)

    if body.requirements:
        pb_sets.append("requirements = requirements || :req_patch::jsonb")
        pb_values["req_patch"] = json.dumps(body.requirements)
        changed.extend(f"requirements.{k}" for k in body.requirements.keys())

    if body.event_schedule is not None:
        pb_sets.append("event_schedule = :sched::jsonb")
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
        "UPDATE lead_sales_playbook SET activities = activities || :item::jsonb, updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
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
        "UPDATE lead_sales_playbook SET activities = :acts::jsonb, updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
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
        "UPDATE lead_sales_playbook SET activities = :acts::jsonb, updated_by = :by, updated_at = NOW() WHERE lead_id = :id",
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
        "UPDATE lead_sales_playbook SET new_activity_suggestions = new_activity_suggestions || :entry::jsonb, "
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
