"""
Internal admin booking-management page (admin.html — NOT accessible to the
end customer). Lets team members review every booking's captured details,
assign a person / value against each field, add remarks, remove a service,
add a coupon, and track payment status.

Two different editing models live side by side here, by design:

  1. "Customer & Event Details" section — DIRECT WRITE. Customer's Choice
     is read-only (frozen, showing exactly what the customer submitted).
     Updated Value is editable; saving it writes straight into the real
     `leads` column (blank + save clears the field to NULL). This is the
     one place this page is allowed to mutate the original booking record.
  2. Everything else (Services / Add-ons / Billing & Rewards) — OVERRIDE.
     Customer's Choice is editable but never touches `leads` or
     builder_snapshot — it's stored in booking_field_overrides, and always
     falls back to the value originally captured from the customer when no
     override exists. Assigned Value holds the vendor/person/admin note.

Every change (direct-write value, customer choice, assigned value,
remarks, removed/restored, new custom field) is appended to
booking_change_log with an IST timestamp and the name of whoever made it.

ROUND 1 SCOPE (2026-08-15, per Shruti): Grand Total and Balance Due are
read-only DISPLAYS of the values captured at checkout — they are NOT yet
live-recalculated when a service/discount changes. Vendor assignment is
free text for every service for now (a proper vendor-master-table + dropdown
is planned as a follow-up once Shruti provides the vendor list). Customer's
Choice for Decor/Host/Music/Photography/Piñata/E-Invite is a dropdown
constrained to the site's actual catalogue options.

NOTE for Shruti: edits made here do NOT re-send emails, do NOT update the
Google Sheet row, and do NOT recalculate real pricing/payment totals — this
page is a team-facing record-keeping + assignment tool on top of the
booking, not a re-trigger of the customer-facing flow.
"""
import json
import logging
import re
from datetime import datetime, timedelta, date as date_cls
from typing import Optional, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from config import settings
import catalogue_data as cat

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


# ─── AUTH ─────────────────────────────────────────────────────────────────
# Single shared password (ADMIN_PASSWORD, set in Railway env vars), sent by
# the frontend on every request as the X-Admin-Password header.

def _require_admin(x_admin_password: Optional[str] = Header(None)):
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin page is not configured (ADMIN_PASSWORD not set).")
    if not x_admin_password or x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect admin password.")


# ─── IST FORMATTING ───────────────────────────────────────────────────────

_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIXES.get(n % 10, 'th')}"


def _to_ist_str(dt) -> Optional[str]:
    """Converts a UTC (aware or naive) datetime — as stored in Postgres
    TIMESTAMPTZ columns — to an IST display string. IST is a fixed
    UTC+5:30 offset (no DST), so this is a straight add, not a timezone
    library conversion."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)  # normalize to naive UTC
    ist = dt + IST_OFFSET
    return f"{_ordinal(ist.day)} {ist.strftime('%b %Y, %I:%M %p')} IST"


def _date_str(d) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.isoformat()


def _display_value(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, date_cls):
        return v.isoformat()
    return str(v)


# ─── FIELD CATALOG ────────────────────────────────────────────────────────
# One entry per predefined field. `admin_only` fields have no source value
# from the customer's submission — the admin fills them in directly.

FIELD_CATALOG = [
    # Customer & Event Details — captured in Step 0 + checkout. DIRECT WRITE:
    # Updated Value here writes straight into the matching `leads` column
    # (field key == column name for every field in this section).
    {"key": "parent_name",         "label": "Parent Name",           "section": "Customer & Event Details"},
    {"key": "phone",                "label": "Phone",                  "section": "Customer & Event Details"},
    {"key": "email",                "label": "Email",                  "section": "Customer & Event Details"},
    {"key": "child_names",          "label": "Child Name(s)",          "section": "Customer & Event Details"},
    {"key": "child_ages",           "label": "Child Age(s)",           "section": "Customer & Event Details"},
    {"key": "child_genders",        "label": "Child Gender(s)",        "section": "Customer & Event Details"},
    {"key": "child_dobs",           "label": "Child DOB(s)",           "section": "Customer & Event Details"},
    {"key": "kids_count",           "label": "Kids Count",             "section": "Customer & Event Details"},
    {"key": "event_date",           "label": "Event Date",             "section": "Customer & Event Details"},
    {"key": "event_time",           "label": "Event Time",             "section": "Customer & Event Details"},
    {"key": "venue",                "label": "Venue",                  "section": "Customer & Event Details"},
    {"key": "venue_maps_link",      "label": "Venue Maps Link",        "section": "Customer & Event Details"},
    {"key": "venue_contact_name",   "label": "Venue Contact Name",     "section": "Customer & Event Details"},
    {"key": "venue_contact_phone",  "label": "Venue Contact Phone",    "section": "Customer & Event Details"},
    {"key": "location_type",        "label": "Location Type",          "section": "Customer & Event Details"},
    {"key": "theme",                "label": "Theme",                  "section": "Customer & Event Details"},
    # 2026-08-19, per Shruti: City moved below Pincode (City auto-fills from
    # Pincode — see PINCODE_CITY_MAP/onPincodeInput() in admin.html — so it
    # reads more naturally once Pincode has already been entered above it).
    {"key": "pincode",              "label": "Pincode",                "section": "Customer & Event Details"},
    {"key": "city",                 "label": "City",                   "section": "Customer & Event Details"},

    # Services — derived from builder_snapshot. Customer's Choice is a
    # dropdown for the fixed-option services; Assigned Value holds the
    # vendor/host/volunteer name (free text for now).
    {"key": "svc_decor",       "label": "Decor",             "section": "Services"},
    {"key": "svc_activities",  "label": "Activities",        "section": "Services"},
    {"key": "svc_host",        "label": "Host",               "section": "Services"},
    {"key": "svc_dj",          "label": "Music (DJ)",        "section": "Services"},
    {"key": "svc_pinata",      "label": "Piñata",            "section": "Services"},
    {"key": "svc_einvite",     "label": "E-Invite",          "section": "Services"},
    {"key": "svc_photo",       "label": "Photography",       "section": "Services"},
    {"key": "svc_gifts",       "label": "Gifts",              "section": "Services"},

    # Add-ons
    {"key": "addon_dj_lights",       "label": "Music Lights",           "section": "Add-ons"},
    {"key": "addon_dj_smoke",        "label": "Music Smoke Machine",    "section": "Add-ons"},
    {"key": "addon_gift_packaging",  "label": "Gift Packaging",         "section": "Add-ons"},
    {"key": "addon_gift_note",       "label": "Gift Thank-You Note",    "section": "Add-ons"},
    {"key": "addon_pinata_bags",     "label": "Piñata Bags",            "section": "Add-ons", "admin_only": True},
    {"key": "addon_pinata_fillings", "label": "Piñata Fillings",        "section": "Add-ons", "admin_only": True},

    # Billing & Rewards — Grand Total / Balance Due are system-calculated
    # displays (read-only, see READ_ONLY_FIELDS below); everything else here
    # is admin-editable.
    {"key": "bill_grand_total",     "label": "Grand Total",            "section": "Billing & Rewards"},
    {"key": "bill_discount_pct",    "label": "Discount %",             "section": "Billing & Rewards"},
    {"key": "bill_advance",         "label": "Advance Paid",           "section": "Billing & Rewards"},
    {"key": "bill_balance",         "label": "Balance Due",            "section": "Billing & Rewards"},
    {"key": "bill_payment_method",  "label": "Payment Method",         "section": "Billing & Rewards"},
    {"key": "bill_payment_status",  "label": "Payment Status",         "section": "Billing & Rewards", "admin_only": True},
    {"key": "bill_coupon_code",     "label": "Coupon Code",            "section": "Billing & Rewards"},
    {"key": "bill_reward_won",      "label": "Reward Won",             "section": "Billing & Rewards"},
    {"key": "bill_reward_redeemed", "label": "Reward Redeemed As",     "section": "Billing & Rewards"},
]

SECTIONS = ["Customer & Event Details", "Services", "Add-ons", "Billing & Rewards"]
CATALOG_BY_KEY = {f["key"]: f for f in FIELD_CATALOG}

DIRECT_WRITE_FIELDS = {f["key"] for f in FIELD_CATALOG if f["section"] == "Customer & Event Details"}
READ_ONLY_FIELDS = {"bill_grand_total", "bill_balance"}

# ─── Dropdown option lists ────────────────────────────────────────────────
# Each option is {"value": ..., "label": ...} — value is what's actually
# stored/compared against booking data, label is what the admin sees (so
# Decor can show "Theme - Tier - Rs. Price" without that price ever being
# saved as part of the value itself, which would break matching against
# older bookings if a price later changes).
# Host/Music/Photo/Piñata/E-Invite/coupon status lists are kept in sync by hand
# with builder.html (same convention catalogue_data.py itself uses).
# Decor is generated from catalogue_data.py's THEMES + DECOR_TIER_META
# directly, so it never drifts out of sync with the real theme/tier/price
# list — last synced 2026-08-15.

def _opt(value, label=None):
    return {"value": value, "label": label if label is not None else value}


_STD_DECOR_NAMES = {
    "Classic": "Classic Balloon Arch",
    "Premium": "Premium Decor",
    "Luxury": "Luxury Decor",
    "Signature": "Signature Decor",
}


def _build_decor_options():
    opts = []
    for theme in cat.THEMES:
        for tier in theme["tierPhotos"].keys():
            price = cat.DECOR_TIER_META[tier]["price"]
            value = f'{theme["n"]} - {tier}'
            opts.append(_opt(value, f'{value} - Rs. {price}'))
    for tier, std_name in _STD_DECOR_NAMES.items():
        price = cat.DECOR_TIER_META[tier]["price"]
        opts.append(_opt(std_name, f'{std_name} - Rs. {price}'))
    opts.append(_opt("Custom Design"))
    return opts


# Tier/pinata labels now carry "Rs. Price" the same way Decor does (2026-08-18,
# per Shruti — "add pricing with the tier name"). Value stays the bare tier/
# pinata name (unpriced) so it still matches historical booking data and the
# DROPDOWN_VALUES membership check in _validate_choice_value below.
DECOR_OPTIONS = _build_decor_options()
HOST_OPTIONS = [_opt(x, f'{x} - Rs. {cat.HOST_TIER_PRICES[x]}') for x in ["Premium", "Signature"]]
DJ_OPTIONS = [_opt(x, f'{x} - Rs. {cat.DJ_TIER_PRICES[x]}') for x in ["Classic", "Premium"]]
PHOTO_OPTIONS = [_opt(x, f'{x} - Rs. {cat.PHOTO_TIER_PRICES[x]}') for x in ["Classic", "Premium", "Signature"]]
PINATA_OPTIONS = [
    _opt(x, f'{x} - Rs. {cat.PINATA_TIER_PRICES[x]}') if x in cat.PINATA_TIER_PRICES else _opt(x)
    for x in ["Square Pinata", "Circle Pinata", "Number Pinata", "Readymade Pinata", "Custom Design"]
]
EINVITE_OPTIONS = [_opt(x) for x in [
    "No selection", "Art Party", "Frozen (Elsa)", "Frozen (Anna)", "Ramayana", "Little Singham",
    "Spy × K-Pop", "Spy Detective", "Spy Party (Classic)", "Spy Squad", "Unicorn",
    "Superhero (3D)", "Superhero (Pop Art)", "Football × Spy Mission", "Football × Spy Mission (Alt)",
    "Harry Potter", "Imposter Mission", "Imposter Mission (Alt)", "K-Pop Idol Collage", "K-Pop Bestie",
    "K-Pop Girl Group (Red)", "K-Pop Girl Group (Green)", "Lilo & Stitch", "Movie Night (Gold)",
    "Movie Night (Classic)", "Nani ka Ghar (Photoreal)", "Nani ka Ghar (Phone Call)",
]]
PAYMENT_METHOD_OPTIONS = [_opt(x) for x in ["Cash", "UPI Transfer", "Bank Transfer", "Internal Settle"]]
PAYMENT_STATUS_OPTIONS = [_opt(x) for x in ["Pending", "Advance Paid Pending Verification", "Advance Paid Verified", "Complete"]]

# ─── Lead → Booking status workflow (2026-08-19, per Shruti; reworked same
# day after her follow-up round — see migrations/017_lead_status_workflow.sql
# then 018_booking_flag_and_status_simplify.sql) ───────────────────────────
# admin.html now shows two separate tables — Leads and Bookings — split by
# the `is_booking` column (a lead becomes a booking either at direct
# checkout, or via the "Convert to Booking" action; never the reverse).
#
#   LEAD rows (is_booking=FALSE): status is one of LEAD_STATUSES, fully
#   editable via a dropdown, with a reason picker for Not Interested/DND
#   (item 5 — "no cancel button for leads, use status to update cancelled/
#   not interested"). No Cancel action here at all.
#
#   BOOKING rows (is_booking=TRUE): status is READ-ONLY, computed live by
#   _booking_display_status() as one of New/Upcoming/Complete/Cancelled —
#   never "Save Status" or "Convert" here (item 3), the only write action is
#   Cancel. Only 'Cancelled' is ever actually stored for a booking row (see
#   that function) — Upcoming/Complete are derived from event_date on every
#   read, so they can never go stale.
LEAD_STATUSES = ["New", "Initial Discussions Done", "Proposal Sent", "Negotiations Ongoing", "Not Interested", "DND"]
LEAD_STATUS_OPTIONS = [_opt(x) for x in LEAD_STATUSES]
BOOKING_DISPLAY_STATUSES = ["New", "Upcoming", "Complete", "Cancelled"]

# Shown only when a lead is marked Not Interested / DND — i.e. it left the
# pipeline without converting.
NON_CONVERT_STATUSES = {"Not Interested", "DND"}
NON_CONVERT_REASONS = [
    "Seeking more discount", "Went ahead with a competitor", "Play area",
    "We did not pitch on time", "Venue monopoly", "Others",
]
NON_CONVERT_REASON_OPTIONS = [_opt(x) for x in NON_CONVERT_REASONS]


def _booking_display_status(lead: dict) -> str:
    if lead.get("status") == "Cancelled":
        return "Cancelled"
    event_date = lead.get("event_date")
    if not event_date:
        return "New"
    today = datetime.utcnow().date()
    ed = event_date if isinstance(event_date, date_cls) else datetime.strptime(str(event_date), "%Y-%m-%d").date()
    return "Complete" if ed < today else "Upcoming"

DROPDOWN_OPTIONS = {
    "svc_decor": DECOR_OPTIONS,
    "svc_host": HOST_OPTIONS,
    "svc_dj": DJ_OPTIONS,
    "svc_photo": PHOTO_OPTIONS,
    "svc_pinata": PINATA_OPTIONS,
    "svc_einvite": EINVITE_OPTIONS,
    "bill_payment_method": PAYMENT_METHOD_OPTIONS,
    "bill_payment_status": PAYMENT_STATUS_OPTIONS,
}
# Plain value sets, for validation (label text is never compared).
DROPDOWN_VALUES = {key: {o["value"] for o in opts} for key, opts in DROPDOWN_OPTIONS.items()}

# Activities/Gifts are MULTI-select (a booking can have several) — Current
# Value stores a comma-joined list ("Canvas Painting, Tote Bag Painting" /
# "900ml Tumbler x2, Personalized Cap x1"), so they can't go through the
# single-value DROPDOWN_VALUES membership check above (a joined list will
# never equal one option value). Kept in a separate dict the frontend uses
# to build a multi-row picker (2026-08-18, per Shruti — "+ for multi-select").
ACTIVITY_OPTIONS = [_opt(n, f'{n} - Rs. {p}' + ('' if flat else '/child')) for _id, n, p, flat in cat.ACTIVITIES]
GIFT_OPTIONS = [_opt(n, f'{n} - Rs. {p}') for _id, n, _img, p in cat.GIFTS]
MULTI_OPTIONS = {
    "svc_activities": ACTIVITY_OPTIONS,
    "svc_gifts": GIFT_OPTIONS,
}
MULTI_WITH_QTY = {"svc_gifts"}   # gifts need a per-item quantity; activities don't

ASSIGNED_PLACEHOLDERS = {
    "svc_decor": "Decorator name",
    "svc_activities": "Vendor(s) / volunteer(s)",
    "svc_host": "Host name",
    "svc_dj": "Music vendor",
    "svc_pinata": "Vendor",
    "svc_photo": "Photographer / vendor",
    "svc_gifts": "Vendor",
}


def _parse_snapshot(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _derive_original_value(key: str, lead: dict, snap: dict):
    """Returns the value originally captured from the customer for a given
    field key, or None if not applicable / not filled in."""

    if key in ("parent_name", "phone", "email", "child_names", "child_ages",
               "child_genders", "child_dobs", "kids_count", "event_time",
               "venue", "venue_maps_link", "venue_contact_name",
               "venue_contact_phone", "location_type", "theme", "city",
               "pincode", "payment_method"):
        v = lead.get(key)
        return str(v) if v is not None else None

    if key == "event_date":
        return _date_str(lead.get("event_date"))

    if key == "svc_decor":
        d = snap.get("decor")
        return d.get("n") if d else None
    if key == "svc_activities":
        acts = snap.get("activities") or []
        names = [a.get("n") for a in acts if a.get("n")]
        return ", ".join(names) if names else None
    if key == "svc_host":
        h = snap.get("host")
        return h.get("tier") if h else None
    if key == "svc_dj":
        dj = snap.get("dj")
        return dj.get("tier") if dj else None
    if key == "svc_pinata":
        p = snap.get("pinata")
        return p.get("n") if p else None
    if key == "svc_einvite":
        e = snap.get("einvite")
        return e.get("n") if e and e.get("n") else "No selection"
    if key == "svc_photo":
        ph = snap.get("photo")
        return ph.get("tier") if ph else None
    if key == "svc_gifts":
        gifts = snap.get("gifts") or []
        parts = [f"{g.get('n')} x{g.get('qty')}" for g in gifts if g.get("n")]
        return ", ".join(parts) if parts else None

    if key == "addon_dj_lights":
        v = lead.get("dj_lights_addon")
        return None if v is None else ("Yes" if v else "No")
    if key == "addon_dj_smoke":
        v = lead.get("dj_smoke_machine_addon")
        return None if v is None else ("Yes" if v else "No")
    if key == "addon_gift_packaging":
        return snap.get("gift_packaging")
    if key == "addon_gift_note":
        v = snap.get("gift_thank_you_note")
        return None if v is None else ("Yes" if v else "No")
    if key in ("addon_pinata_bags", "addon_pinata_fillings"):
        return None  # admin-tracked only, no customer-side source

    if key == "bill_grand_total":
        v = lead.get("order_grand_total")
        return str(v) if v is not None else None
    if key == "bill_discount_pct":
        v = lead.get("order_discount_pct")
        return str(v) if v is not None else None
    if key == "bill_advance":
        v = lead.get("order_advance")
        return str(v) if v is not None else None
    if key == "bill_balance":
        v = lead.get("order_balance")
        return str(v) if v is not None else None
    if key == "bill_payment_status":
        return None  # admin-tracked only, no DB column for this
    if key == "bill_coupon_code":
        return lead.get("redeemed_coupon_code")
    if key == "bill_reward_won":
        return lead.get("reward_label") or lead.get("reward_type")
    if key == "bill_reward_redeemed":
        return lead.get("redeemed_reward_service")

    return None


# ─── SCHEMAS ──────────────────────────────────────────────────────────────

class FieldUpdateRequest(BaseModel):
    field_key: str
    field_label: Optional[str] = None   # required when adding a NEW custom field
    section: Optional[str] = None       # required when adding a NEW custom field
    customer_choice_override: Optional[str] = ""   # "" = no override, show original
    assigned_value: Optional[str] = ""              # also doubles as "Updated Value" for direct-write fields
    remarks: Optional[str] = ""
    removed: bool = False
    changed_by: str


class StatusUpdateRequest(BaseModel):
    status: str
    non_convert_reason: Optional[str] = ""
    non_convert_reason_other: Optional[str] = ""
    changed_by: str


# ─── LOG SENTENCES ────────────────────────────────────────────────────────

def _log_sentence(field_label: str, change_type: str, old_value, new_value, changed_by: str, changed_at) -> str:
    ts = _to_ist_str(changed_at) or ""
    old_d = old_value if old_value not in (None, "") else "—"
    new_d = new_value if new_value not in (None, "") else "—"
    if change_type == "customer_choice":
        return f'{field_label}: customer choice changed from "{old_d}" to "{new_d}" by {changed_by} on {ts}.'
    if change_type == "assigned_value":
        return f'{field_label}: assigned value changed from "{old_d}" to "{new_d}" by {changed_by} on {ts}.'
    if change_type == "field_value":
        return f'{field_label}: changed from "{old_d}" to "{new_d}" by {changed_by} on {ts} (booking record updated).'
    if change_type == "remarks":
        return f'{field_label}: remarks updated by {changed_by} on {ts}.'
    if change_type == "removed":
        return f'{field_label}: removed by {changed_by} on {ts}.'
    if change_type == "restored":
        return f'{field_label}: restored by {changed_by} on {ts}.'
    if change_type == "field_added":
        return f'{field_label}: added by {changed_by} on {ts}.'
    return f'{field_label}: {change_type} changed from "{old_d}" to "{new_d}" by {changed_by} on {ts}.'


# ─── VALIDATION (Services dropdowns + Billing rules) ──────────────────────

async def _validate_choice_value(key: str, value: str, derived_original: Optional[str], lead: dict):
    """Applies to the value about to be saved into Customer's Choice for
    override-based fields. Blank values (= revert to original) always skip
    validation. A value matching the field's current original/derived value
    is always allowed even if it isn't in the dropdown list — this covers
    legacy bookings whose stored text doesn't exactly match today's
    catalogue naming, so a plain re-save (e.g. of remarks) never gets
    blocked."""
    if not value:
        return

    if key in DROPDOWN_VALUES and value not in DROPDOWN_VALUES[key] and value != derived_original:
        raise HTTPException(status_code=400, detail=f'"{value}" is not a valid option for {CATALOG_BY_KEY[key]["label"]}.')

    if key == "bill_discount_pct":
        try:
            pct = float(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Discount % must be a number.")
        if pct < 0 or pct > 100:
            raise HTTPException(status_code=400, detail="Discount % cannot exceed 100%.")

    if key == "bill_advance":
        try:
            adv = float(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Advance Paid must be a number.")
        grand_total = lead.get("order_grand_total")
        if grand_total is not None and adv > float(grand_total):
            raise HTTPException(status_code=400, detail="Advance Paid cannot exceed the Grand Total.")

    if key == "bill_coupon_code":
        row = await database.fetch_one(
            "SELECT coupon_id FROM coupons WHERE UPPER(code) = UPPER(:code) AND is_active = TRUE",
            values={"code": value},
        )
        if not row:
            raise HTTPException(status_code=400, detail=f'"{value}" was not found in the list of verified coupon codes.')


GENDER_VALUES = {"Boy", "Girl", "Prefer not to say"}   # mirrors builder.html's #ld-gender select
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _coerce_direct_value(key: str, raw: str):
    """Type-coerces a raw string from the Updated Value input for a
    direct-write (Customer & Event Details) field, or raises a 400 if it's
    not valid for that field's DB column type.

    child_ages/child_genders/child_dobs can hold several comma-joined values
    for multi-child bookings (e.g. "6, 8") — the admin dropdown/date-picker
    only render when there's a single child, so these still accept a
    comma-list here and validate each segment independently
    (2026-08-18, per Shruti — gender dropdown, numeric age, date pickers,
    email/pincode format checks)."""
    raw = (raw or "").strip()
    if raw == "":
        return None
    if key == "kids_count":
        try:
            return int(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="Kids Count must be a whole number.")
    if key == "event_date":
        # 2026-08-19, per Shruti: "event date is not getting updated" — this
        # used to return the raw 'YYYY-MM-DD' STRING, which asyncpg rejects
        # for a DATE column (leads.event_date is DATE, not TEXT), raising a
        # 500 on every save. Every other direct-write field is a text/int
        # column so a plain string/int coerces fine; date is the one column
        # that needs an actual datetime.date object.
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Event Date must be in YYYY-MM-DD format.")
    if key == "event_time":
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Event Time must be in HH:MM format.")
        return raw
    if key == "email":
        if not _EMAIL_RE.match(raw):
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        return raw
    if key == "pincode":
        if not re.fullmatch(r"\d{6}", raw):
            raise HTTPException(status_code=400, detail="Pincode must be exactly 6 digits.")
        return raw
    if key == "child_ages":
        for part in raw.split(","):
            part = part.strip()
            if part and not part.isdigit():
                raise HTTPException(status_code=400, detail=f'Child Age "{part}" must be a whole number.')
        return raw
    if key == "child_genders":
        for part in raw.split(","):
            part = part.strip()
            if part and part not in GENDER_VALUES:
                raise HTTPException(status_code=400, detail=f'"{part}" is not a valid gender option.')
        return raw
    if key == "child_dobs":
        for part in raw.split(","):
            part = part.strip()
            if part:
                try:
                    datetime.strptime(part, "%Y-%m-%d")
                except ValueError:
                    raise HTTPException(status_code=400, detail=f'Child DOB "{part}" must be in YYYY-MM-DD format.')
        return raw
    return raw


# ─── STATUS AUTO-TRANSITION ────────────────────────────────────────────────
# 2026-08-19, per Shruti: "status should change to completed once the event
# date has passed. if the event is cancelled, then the status remains
# cancelled forever." Run lazily (on every list/detail load, not via a
# separate cron job — the backend has no scheduler infra today) — cheap
# enough as a single bulk UPDATE, and it's always fresh by the time an admin
# is actually looking at the page. Only 'Converted' bookings roll forward;
# every other status (including 'Cancelled') is left untouched.
@router.get("/status-options")
async def get_status_options(x_admin_password: Optional[str] = Header(None)):
    """Lets the list/summary page render its quick status dropdown without
    fetching a full booking detail first."""
    _require_admin(x_admin_password)
    return {
        "lead_status_options": LEAD_STATUS_OPTIONS,
        "booking_display_statuses": BOOKING_DISPLAY_STATUSES,
        "non_convert_reason_options": NON_CONVERT_REASON_OPTIONS,
        "non_convert_statuses": sorted(NON_CONVERT_STATUSES),
    }


# ─── LIST ─────────────────────────────────────────────────────────────────
# 2026-08-19, per Shruti: "Create 2 tables on admin panel - 1 for leads, 1
# for bookings." Same endpoint, split by the `kind` param so the frontend
# can fetch each table independently (and show its own "new" count badge —
# "if there are new entries, show a bubble with the number").

@router.get("/bookings")
async def list_bookings(kind: str = "lead", q: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    is_booking = kind == "booking"
    where = ["is_booking = :is_booking"]
    values = {"is_booking": is_booking}
    if q:
        where.append("(parent_name ILIKE :like OR phone ILIKE :like OR email ILIKE :like OR CAST(lead_id AS TEXT) = :q)")
        values["like"] = f"%{q}%"
        values["q"] = q
    rows = await database.fetch_all(
        f"""
        SELECT lead_id, parent_name, phone, email, event_date, city, status, created_on
        FROM leads
        WHERE {' AND '.join(where)}
        ORDER BY created_on DESC
        LIMIT 200
        """,
        values=values,
    )
    out = []
    new_count = 0
    for r in rows:
        row = dict(r)
        display_status = _booking_display_status(row) if is_booking else row["status"]
        if display_status == "New":
            new_count += 1
        out.append({
            "lead_id": row["lead_id"],
            "parent_name": row["parent_name"],
            "phone": row["phone"],
            "email": row["email"],
            "event_date": _date_str(row["event_date"]),
            "city": row["city"],
            "status": display_status,
            "created_on_ist": _to_ist_str(row["created_on"]),
        })
    return {"rows": out, "new_count": new_count}


# ─── DETAIL ───────────────────────────────────────────────────────────────

@router.get("/bookings/{lead_id}")
async def get_booking_detail(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    lead = dict(lead_row)
    snap = _parse_snapshot(lead.get("builder_snapshot"))

    override_rows = await database.fetch_all(
        "SELECT * FROM booking_field_overrides WHERE lead_id = :id",
        values={"id": lead_id},
    )
    overrides = {r["field_key"]: dict(r) for r in override_rows}

    sections = {s: [] for s in SECTIONS}

    for f in FIELD_CATALOG:
        key = f["key"]
        ov = overrides.get(key)
        is_direct = key in DIRECT_WRITE_FIELDS
        is_read_only = key in READ_ONLY_FIELDS
        derived = None if f.get("admin_only") else _derive_original_value(key, lead, snap)

        if is_direct:
            # "Current Value" always mirrors the live `leads` column — never
            # frozen to a pre-edit snapshot. Previously this froze at the
            # first edit (showing "Aditya" forever even after a save changed
            # it to "Janani"), which made a successful edit look like it
            # hadn't landed (2026-08-18, per Shruti — renamed from "Customer's
            # Choice" to "Current Value" for the same reason).
            customer_choice = derived
            updated_value = ov["assigned_value"] if ov else derived
            # "Original" is the OPPOSITE: it must freeze forever at whatever
            # the customer actually typed at checkout, and never move again —
            # _update_direct_field() already captures that snapshot into
            # customer_choice_override the moment before the first-ever edit
            # overwrites the `leads` column, it just wasn't being read back
            # out here. Before this fix, "Original" used the same live
            # `derived` value as Current Value, so it silently tracked every
            # edit too (2026-08-19, per Shruti — reported as "Original: J"
            # right after a Parent Name edit, when the true original was
            # "Aditya"). No override row yet = nothing has ever overwritten
            # the column = the live value IS still the original.
            original_value = ov["customer_choice_override"] if ov else derived
        else:
            customer_choice = (ov["customer_choice_override"] if ov and ov["customer_choice_override"] else derived)
            updated_value = ov["assigned_value"] if ov else None
            original_value = derived   # sourced from the immutable booking snapshot — never mutated by an override

        sections[f["section"]].append({
            "field_key": key,
            "label": f["label"],
            "admin_only": bool(f.get("admin_only")),
            "is_custom": False,
            "is_direct_write": is_direct,
            "read_only": is_read_only,
            "choice_editable": (not is_direct) and (not is_read_only),
            "updated_editable": not is_read_only,
            "has_override": bool(ov),
            "options": DROPDOWN_OPTIONS.get(key),
            "multi_options": MULTI_OPTIONS.get(key),
            "multi_with_qty": key in MULTI_WITH_QTY,
            "placeholder": ASSIGNED_PLACEHOLDERS.get(key),
            "original_value": original_value,
            "customer_choice": customer_choice,
            "assigned_value": updated_value,
            "remarks": ov["remarks"] if ov else None,
            "removed": bool(ov["removed"]) if ov else False,
            "updated_by": ov["updated_by"] if ov else None,
            "updated_at_ist": _to_ist_str(ov["updated_at"]) if ov else None,
        })

    # ─── Balance Due auto-calculation ──────────────────────────────────────
    # 2026-08-19, per Shruti: "fix the grand total now, it should be
    # autocalculated." Grand Total itself already comes straight from what
    # the customer actually agreed to pay at checkout (order_grand_total —
    # captured live from builder.html's own discount/total math, so it's
    # already correct and is deliberately NOT re-derived from today's
    # service selections here — an admin override like "Host: Premium →
    # Signature" is an operational note, not a new price agreement). What
    # WASN'T auto-calculated was Balance Due: it used to just echo whatever
    # order_balance was captured at the original checkout, so correcting
    # Advance Paid here (e.g. after verifying a bank transfer) never moved
    # Balance Due. Balance Due is now always Grand Total − Advance Paid,
    # using each field's live resolved value (i.e. any admin override to
    # Advance Paid is picked up immediately).
    def _money(s):
        if s in (None, ""):
            return None
        try:
            return float(str(s).replace(",", "").replace("₹", "").strip())
        except ValueError:
            return None

    billing_fields = {f["field_key"]: f for f in sections.get("Billing & Rewards", [])}
    grand_total_val = _money(billing_fields.get("bill_grand_total", {}).get("customer_choice"))
    advance_val = _money(billing_fields.get("bill_advance", {}).get("customer_choice"))
    balance_field = billing_fields.get("bill_balance")
    if balance_field is not None and grand_total_val is not None:
        computed_balance = grand_total_val - (advance_val or 0)
        display = str(int(computed_balance)) if computed_balance == int(computed_balance) else str(computed_balance)
        balance_field["customer_choice"] = display
        balance_field["original_value"] = display

    # Custom (admin-added) fields not in the predefined catalog
    for key, ov in overrides.items():
        if key in CATALOG_BY_KEY or not ov.get("is_custom"):
            continue
        section = ov.get("section") or "Add-ons"
        if section not in sections:
            sections[section] = []
        sections[section].append({
            "field_key": key,
            "label": ov.get("field_label") or key,
            "admin_only": True,
            "is_custom": True,
            "is_direct_write": False,
            "read_only": False,
            "choice_editable": True,
            "updated_editable": True,
            "has_override": True,
            "options": None,
            "placeholder": None,
            "original_value": None,
            "customer_choice": ov["customer_choice_override"] or None,
            "assigned_value": ov["assigned_value"],
            "remarks": ov["remarks"],
            "removed": bool(ov["removed"]),
            "updated_by": ov["updated_by"],
            "updated_at_ist": _to_ist_str(ov["updated_at"]),
        })

    log_rows = await database.fetch_all(
        "SELECT * FROM booking_change_log WHERE lead_id = :id ORDER BY changed_at ASC",
        values={"id": lead_id},
    )
    change_log = [
        {
            "field_key": r["field_key"],
            "field_label": r["field_label"],
            "change_type": r["change_type"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "changed_by": r["changed_by"],
            "changed_at_ist": _to_ist_str(r["changed_at"]),
            "sentence": _log_sentence(r["field_label"] or r["field_key"], r["change_type"], r["old_value"], r["new_value"], r["changed_by"], r["changed_at"]),
        }
        for r in log_rows
    ]

    is_booking = bool(lead.get("is_booking"))
    return {
        "lead_id": lead_id,
        "is_booking": is_booking,
        # Read-only computed status for a booking (New/Upcoming/Complete/
        # Cancelled); the raw editable pipeline status for a lead.
        "status": _booking_display_status(lead) if is_booking else lead.get("status"),
        "non_convert_reason": lead.get("non_convert_reason"),
        "non_convert_reason_other": lead.get("non_convert_reason_other"),
        "lead_status_options": LEAD_STATUS_OPTIONS,
        "non_convert_reason_options": NON_CONVERT_REASON_OPTIONS,
        "created_on_ist": _to_ist_str(lead.get("created_on")),
        "sections": [{"section": s, "fields": sections[s]} for s in sections],
        "change_log": change_log,
    }


# ─── UPDATE A FIELD ───────────────────────────────────────────────────────

async def _update_direct_field(lead_id: int, key: str, body: FieldUpdateRequest, lead: dict, existing, who: str):
    """Customer & Event Details fields: Updated Value writes straight into
    the matching `leads` column. Customer's Choice is frozen (captured from
    whatever was in that column right before the FIRST-ever edit) and never
    touched again, so it keeps showing the true original submission."""
    label = CATALOG_BY_KEY[key]["label"]
    section = CATALOG_BY_KEY[key]["section"]

    coerced = _coerce_direct_value(key, body.assigned_value)
    new_remarks = (body.remarks or "").strip()

    old_value_display = _display_value(lead.get(key))
    new_value_display = _display_value(coerced)

    frozen_original = existing["customer_choice_override"] if existing else old_value_display
    old_remarks = existing["remarks"] if existing else None

    now = datetime.utcnow()
    log_entries = []
    if old_value_display != new_value_display:
        log_entries.append(("field_value", old_value_display, new_value_display, now))
    if (old_remarks or None) != (new_remarks or None):
        log_entries.append(("remarks", old_remarks, new_remarks or None, now))

    # The one place this page writes to the real booking record.
    await database.execute(f"UPDATE leads SET {key} = :val WHERE lead_id = :lead_id", values={"val": coerced, "lead_id": lead_id})

    if existing:
        await database.execute(
            """
            UPDATE booking_field_overrides
            SET assigned_value = :av, remarks = :rm, updated_by = :by, updated_at = :now
            WHERE lead_id = :lead_id AND field_key = :key
            """,
            values={"av": new_value_display, "rm": new_remarks or None, "by": who, "now": now, "lead_id": lead_id, "key": key},
        )
    else:
        await database.execute(
            """
            INSERT INTO booking_field_overrides
                (lead_id, field_key, field_label, section, customer_choice_override,
                 assigned_value, remarks, removed, is_custom, updated_by, updated_at)
            VALUES
                (:lead_id, :key, :label, :section, :cco, :av, :rm, FALSE, FALSE, :by, :now)
            """,
            values={
                "lead_id": lead_id, "key": key, "label": label, "section": section,
                "cco": frozen_original, "av": new_value_display, "rm": new_remarks or None,
                "by": who, "now": now,
            },
        )

    for change_type, old_v, new_v, ts in log_entries:
        await database.execute(
            """
            INSERT INTO booking_change_log
                (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
            VALUES
                (:lead_id, :key, :label, :change_type, :old_v, :new_v, :by, :ts)
            """,
            values={
                "lead_id": lead_id, "key": key, "label": label, "change_type": change_type,
                "old_v": old_v, "new_v": new_v, "by": who, "ts": ts,
            },
        )

    # field_label + the actual old/new values ride along on the response so
    # the admin page can pop up a specific "Parent Name: Aditya → Janani"
    # confirmation instead of a bare "Saved." (2026-08-18, per Shruti).
    return {
        "success": True, "field_key": key, "field_label": label, "changes_logged": len(log_entries),
        "log_entries": [{"change_type": ct, "old_value": ov_, "new_value": nv} for ct, ov_, nv, ts in log_entries],
    }


@router.post("/bookings/{lead_id}/field")
async def update_booking_field(lead_id: int, body: FieldUpdateRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    who = body.changed_by.strip()

    key = body.field_key
    if key in READ_ONLY_FIELDS:
        raise HTTPException(status_code=400, detail=f"{CATALOG_BY_KEY[key]['label']} is system-calculated and can't be edited here.")

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    lead = dict(lead_row)
    snap = _parse_snapshot(lead.get("builder_snapshot"))

    existing = await database.fetch_one(
        "SELECT * FROM booking_field_overrides WHERE lead_id = :lead_id AND field_key = :key",
        values={"lead_id": lead_id, "key": key},
    )

    if key in DIRECT_WRITE_FIELDS:
        return await _update_direct_field(lead_id, key, body, lead, existing, who)

    # ─── Override-based fields: Services / Add-ons / Billing & Rewards / custom ───
    is_new_custom = key not in CATALOG_BY_KEY
    label = body.field_label or (CATALOG_BY_KEY.get(key, {}).get("label")) or key
    section = body.section or (CATALOG_BY_KEY.get(key, {}).get("section")) or "Add-ons"

    if is_new_custom and not existing and not body.field_label:
        raise HTTPException(status_code=400, detail="field_label is required when adding a new custom field.")

    new_customer_choice = (body.customer_choice_override or "").strip()
    new_assigned = (body.assigned_value or "").strip()
    new_remarks = (body.remarks or "").strip()

    derived_original = None if CATALOG_BY_KEY.get(key, {}).get("admin_only") else _derive_original_value(key, lead, snap)

    await _validate_choice_value(key, new_customer_choice, derived_original, lead)

    old_customer_choice_stored = existing["customer_choice_override"] if existing else None
    old_assigned = existing["assigned_value"] if existing else None
    old_remarks = existing["remarks"] if existing else None
    old_removed = bool(existing["removed"]) if existing else False

    old_customer_choice_display = old_customer_choice_stored if old_customer_choice_stored else derived_original
    new_customer_choice_display = new_customer_choice if new_customer_choice else derived_original

    now = datetime.utcnow()
    log_entries = []

    if not existing and is_new_custom:
        log_entries.append(("field_added", None, label, now))

    if old_customer_choice_display != new_customer_choice_display:
        log_entries.append(("customer_choice", old_customer_choice_display, new_customer_choice_display, now))
    if (old_assigned or None) != (new_assigned or None):
        log_entries.append(("assigned_value", old_assigned, new_assigned or None, now))
    if (old_remarks or None) != (new_remarks or None):
        log_entries.append(("remarks", old_remarks, new_remarks or None, now))
    if old_removed != body.removed:
        log_entries.append(("removed" if body.removed else "restored", None, None, now))

    if existing:
        await database.execute(
            """
            UPDATE booking_field_overrides
            SET customer_choice_override = :cco, assigned_value = :av, remarks = :rm,
                removed = :removed, field_label = :label, section = :section,
                updated_by = :by, updated_at = :now
            WHERE lead_id = :lead_id AND field_key = :key
            """,
            values={
                "cco": new_customer_choice or None, "av": new_assigned or None, "rm": new_remarks or None,
                "removed": body.removed, "label": label, "section": section,
                "by": who, "now": now,
                "lead_id": lead_id, "key": key,
            },
        )
    else:
        await database.execute(
            """
            INSERT INTO booking_field_overrides
                (lead_id, field_key, field_label, section, customer_choice_override,
                 assigned_value, remarks, removed, is_custom, updated_by, updated_at)
            VALUES
                (:lead_id, :key, :label, :section, :cco, :av, :rm, :removed, :is_custom, :by, :now)
            """,
            values={
                "lead_id": lead_id, "key": key, "label": label, "section": section,
                "cco": new_customer_choice or None, "av": new_assigned or None, "rm": new_remarks or None,
                "removed": body.removed, "is_custom": is_new_custom, "by": who, "now": now,
            },
        )

    for change_type, old_v, new_v, ts in log_entries:
        await database.execute(
            """
            INSERT INTO booking_change_log
                (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
            VALUES
                (:lead_id, :key, :label, :change_type, :old_v, :new_v, :by, :ts)
            """,
            values={
                "lead_id": lead_id, "key": key, "label": label, "change_type": change_type,
                "old_v": old_v, "new_v": new_v, "by": who, "ts": ts,
            },
        )

    return {
        "success": True, "field_key": key, "field_label": label, "changes_logged": len(log_entries),
        "log_entries": [{"change_type": ct, "old_value": ov_, "new_value": nv} for ct, ov_, nv, ts in log_entries],
    }


async def _log_status_change(lead_id: int, old_v, new_v, who: str, now):
    if old_v == new_v:
        return
    await database.execute(
        """
        INSERT INTO booking_change_log
            (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
        VALUES
            (:lead_id, 'status', 'Status', 'field_value', :old_v, :new_v, :by, :ts)
        """,
        values={"lead_id": lead_id, "old_v": old_v, "new_v": new_v, "by": who, "ts": now},
    )


# ─── LEAD STATUS UPDATE ─────────────────────────────────────────────────────
# 2026-08-19, per Shruti's follow-up — this now ONLY applies to lead rows
# (is_booking=FALSE): the pipeline dropdown + non-conversion reason. A
# booking row is rejected here with a 400 (item 3: "convert to booking and
# save status buttons are not eligible for confirmed bookings") — use
# /cancel instead, the only write action a booking row ever gets.
@router.post("/bookings/{lead_id}/status")
async def update_lead_status(lead_id: int, body: StatusUpdateRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    who = body.changed_by.strip()

    new_status = (body.status or "").strip()
    if new_status not in LEAD_STATUSES:
        raise HTTPException(status_code=400, detail=f'"{new_status}" is not a valid lead status.')

    lead_row = await database.fetch_one("SELECT status, is_booking FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if lead_row["is_booking"]:
        raise HTTPException(status_code=400, detail="This is already a confirmed booking — only Cancel is available here.")
    old_status = lead_row["status"]

    new_reason = (body.non_convert_reason or "").strip()
    new_reason_other = (body.non_convert_reason_other or "").strip()
    if new_status not in NON_CONVERT_STATUSES:
        # Reason only makes sense for Not Interested / DND — clear it on any
        # other status so a stale reason doesn't linger from an earlier detour.
        new_reason, new_reason_other = "", ""
    elif new_reason and new_reason not in NON_CONVERT_REASONS:
        raise HTTPException(status_code=400, detail=f'"{new_reason}" is not a valid non-conversion reason.')

    now = datetime.utcnow()
    await database.execute(
        "UPDATE leads SET status = :status, non_convert_reason = :reason, non_convert_reason_other = :reason_other WHERE lead_id = :id",
        values={"id": lead_id, "status": new_status, "reason": new_reason or None, "reason_other": new_reason_other or None},
    )
    await _log_status_change(lead_id, old_status, new_status, who, now)
    return {"success": True, "status": new_status}


class ChangedByRequest(BaseModel):
    changed_by: str


# ─── CONVERT LEAD → BOOKING ─────────────────────────────────────────────────
@router.post("/bookings/{lead_id}/convert")
async def convert_lead_to_booking(lead_id: int, body: ChangedByRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    who = body.changed_by.strip()

    lead_row = await database.fetch_one("SELECT status, is_booking, converted_on FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if lead_row["is_booking"]:
        raise HTTPException(status_code=400, detail="Already a confirmed booking.")

    now = datetime.utcnow()
    set_clauses = ["is_booking = TRUE", "status = 'New'", "non_convert_reason = NULL", "non_convert_reason_other = NULL"]
    values = {"id": lead_id}
    if not lead_row["converted_on"]:
        set_clauses.append("converted_on = :converted_on")
        values["converted_on"] = now
    await database.execute(f"UPDATE leads SET {', '.join(set_clauses)} WHERE lead_id = :id", values=values)
    await _log_status_change(lead_id, lead_row["status"], "Converted to Booking", who, now)
    return {"success": True, "is_booking": True}


# ─── CANCEL (booking rows only) ─────────────────────────────────────────────
# 2026-08-19, per Shruti: "give an option to cancel the event" — the only
# write action available on a confirmed booking row (see item 3/6 above).
@router.post("/bookings/{lead_id}/cancel")
async def cancel_booking(lead_id: int, body: ChangedByRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    who = body.changed_by.strip()

    lead_row = await database.fetch_one("SELECT status, is_booking FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if not lead_row["is_booking"]:
        raise HTTPException(status_code=400, detail="This is a lead, not a confirmed booking — use the status dropdown (Not Interested/DND) instead.")

    now = datetime.utcnow()
    await database.execute("UPDATE leads SET status = 'Cancelled' WHERE lead_id = :id", values={"id": lead_id})
    await _log_status_change(lead_id, lead_row["status"], "Cancelled", who, now)
    return {"success": True, "status": "Cancelled"}
