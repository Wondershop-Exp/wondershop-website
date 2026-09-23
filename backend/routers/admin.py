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
read-only DISPLAYS — no Current Value/Save on either row, they're always
system-computed. Balance Due is Grand Total − Advance Paid, live off each
field's resolved value (2026-08-19). Grand Total itself is the actual
payable total (client_budget), live-recalculated when Discount % changes
but NOT re-derived from today's service selections otherwise — an admin
override like "Host: Premium → Signature" is an operational note, not a
new price agreement (2026-09-10 — see the recalculation block in
get_booking_detail() for the exact formula and its one known limitation).
Vendor assignment is free text for every service for now (a proper
vendor-master-table + dropdown is planned as a follow-up once Shruti
provides the vendor list). Customer's Choice for Decor/Host/Music/
Photography/Piñata/E-Invite is a dropdown constrained to the site's actual
catalogue options.

NOTE for Shruti: edits made here do NOT re-send emails and do NOT
recalculate real pricing/payment totals — this page is a team-facing
record-keeping + assignment tool on top of the booking, not a re-trigger of
the customer-facing flow. 2026-09-22 exception: saving Event Photos
Link(s) DOES push a row to the "Event Photos" tab of the Google Sheet (see
_push_event_photos_to_sheet below) — every other field still only writes
here.
"""
import asyncio
import hmac
import httpx
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
from types import SimpleNamespace
from invoice_builder import assemble_invoice_data, build_invoice_pdf, invoice_filename
from booking_pricing import (
    recompute_grand_total, freebie_activity_names, parse_csv as _parse_csv_names,
    PACKAGING_KEY_TO_LABEL, PACKAGING_UNIT_PRICE, DJ_LIGHTS_PRICE, DJ_SMOKE_PRICE,
    TAG_NOTE_UNIT_PRICE, TAG_NOTE_MIN_QTY, PINATA_BAG_PRICE,
)
from routers.leads import (
    _services_detail_list, _party_title, _fmt_date_long, _gmail_send, _get_gmail_access_token,
    _get_or_create_invoice_number, _order_addon_rows_raw, _sheet_service_columns,
    _send_user_ack, LeadSubmitRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


# ─── AUTH ─────────────────────────────────────────────────────────────────
# Single shared password (ADMIN_PASSWORD, set in Railway env vars), sent by
# the frontend on every request as the X-Admin-Password header.

def _require_admin(x_admin_password: Optional[str] = Header(None)):
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin page is not configured (ADMIN_PASSWORD not set).")
    # Constant-time compare (a plain != leaks how many leading characters matched).
    if not x_admin_password or not hmac.compare_digest(
            x_admin_password.encode("utf-8"), settings.ADMIN_PASSWORD.encode("utf-8")):
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
    # is admin-editable. Grand Total = client_budget (the real payable
    # total), live-recalculated only when Discount % changes — see
    # get_booking_detail()'s recalculation block (2026-09-10, per Shruti).
    {"key": "bill_grand_total",     "label": "Grand Total",            "section": "Billing & Rewards"},
    {"key": "bill_discount_pct",    "label": "Discount %",             "section": "Billing & Rewards"},
    # 2026-08-24, per Shruti (Image 3c) — "the same [freebies/discounts]
    # should be visible on the admin page." System-calculated, same as
    # Grand Total (read-only, see READ_ONLY_FIELDS below) — bill_discount_pct
    # above is a % of the grand total and doesn't include freebie item
    # value, so these two carry the fuller picture (see order_total_savings/
    # order_freebies_text on LeadSubmitRequest in routers/leads.py).
    {"key": "bill_total_savings",   "label": "Total Savings (incl. Freebies)", "section": "Billing & Rewards"},
    {"key": "bill_freebies",        "label": "Freebies Unlocked",      "section": "Billing & Rewards"},
    {"key": "bill_advance",         "label": "Advance Paid",           "section": "Billing & Rewards"},
    {"key": "bill_balance",         "label": "Balance Due",            "section": "Billing & Rewards"},
    {"key": "bill_payment_method",  "label": "Payment Method",         "section": "Billing & Rewards"},
    {"key": "bill_payment_status",  "label": "Payment Status",         "section": "Billing & Rewards", "admin_only": True},
    # 2026-09-11, per Shruti — separate from Payment Status/Method above:
    # confirms the EVENT ITSELF settled (amount + mode), entered by the
    # event admin once delivered. The new monthly dashboard's "Realized"
    # revenue bucket depends on both of these being filled in, not just on
    # the event date having passed.
    {"key": "event_payment_confirmed_amount", "label": "Event Payment Confirmed (Rs.)", "section": "Billing & Rewards", "admin_only": True},
    {"key": "event_payment_confirmed_mode",   "label": "Event Payment Mode",            "section": "Billing & Rewards", "admin_only": True},
    # 2026-09-22, per Shruti — "every image has a google photos link
    # attached to it, add a field in admin to update this." Free text
    # (rendered as a textarea, see admin.html) since one event can have
    # several links; saving this ALSO pushes a row to the "Event Photos"
    # tab of the Google Sheet — see _push_event_photos_to_sheet below.
    {"key": "event_photos_link",    "label": "Event Photos Link(s)",   "section": "Billing & Rewards", "admin_only": True},
    {"key": "bill_coupon_code",     "label": "Coupon Code",            "section": "Billing & Rewards"},
    # 2026-09-22, per Shruti — clarified this is specifically the
    # scratch-card reveal reward (reward_label/reward_type on the lead),
    # not some other kind of "reward", so the label makes that explicit.
    {"key": "bill_reward_won",      "label": "Scratch Card Reward Won", "section": "Billing & Rewards"},
    {"key": "bill_reward_redeemed", "label": "Scratch Card Reward Redeemed As", "section": "Billing & Rewards"},
]

SECTIONS = ["Customer & Event Details", "Services", "Add-ons", "Billing & Rewards"]
CATALOG_BY_KEY = {f["key"]: f for f in FIELD_CATALOG}

DIRECT_WRITE_FIELDS = {f["key"] for f in FIELD_CATALOG if f["section"] == "Customer & Event Details"}
# Payment Status values that mean the team HAS seen the advance arrive.
ADVANCE_CONFIRMED_STATUSES = ("Advance Paid Verified", "Complete")
READ_ONLY_FIELDS = {"bill_grand_total", "bill_balance", "bill_total_savings", "bill_freebies"}

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
_STD_DECOR_NAMES_REV = {v: k for k, v in _STD_DECOR_NAMES.items()}
_THEMES_BY_NAME = {t["n"]: t for t in cat.THEMES}


def _resolve_decor_override(value: Optional[str]) -> Optional[dict]:
    """Best-effort reconstruction of a builder_snapshot-shaped decor entry
    ({"n","id","p"}) from the admin override's plain display string -- see
    _build_decor_options above for exactly how that string is built.
    Used to fill the summary email's Decor section for bookings entered
    through the sales admin panel, which never populate builder_snapshot
    at all (2026-09-23, per Shruti — "decor is chosen in admin but is not
    showing up in the email"). id is left None (image/inclusions just get
    skipped, name + price still show) when the string doesn't match a
    known theme/tier or standard name -- e.g. a free-typed legacy value."""
    value = (value or "").strip()
    if not value:
        return None
    if value == "Custom Design":
        return {"n": value, "id": None, "p": None}
    if " - " in value:
        theme_name, tier = value.rsplit(" - ", 1)
        theme_match = _THEMES_BY_NAME.get(theme_name)
        if theme_match and tier in cat.DECOR_TIER_META:
            return {"n": value, "id": f"{theme_match['id']}-{tier.lower()}", "p": cat.DECOR_TIER_META[tier]["price"]}
    tier = _STD_DECOR_NAMES_REV.get(value)
    if tier:
        return {"n": value, "id": f"std-{tier.lower()}", "p": cat.DECOR_TIER_META[tier]["price"]}
    return {"n": value, "id": None, "p": None}
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
# "Partial Payment Pending" added 2026-09-22, per Shruti — the event-
# payment combined row (admin.html eventPaymentRowHtml/saveEventPaymentRow)
# offers this alongside "Complete" whenever the amount entered is less
# than Balance Due, so an admin recording a shortfall has an honest status
# to land on instead of being forced to either overstate it as Complete or
# leave Payment Status stale.
PAYMENT_STATUS_OPTIONS = [_opt(x) for x in ["Pending", "Advance Paid Pending Verification", "Advance Paid Verified", "Partial Payment Pending", "Complete"]]
# 2026-09-11, per Shruti — event-completion confirmation (distinct from
# Payment Status/Method above, which track advance-payment collection
# before the event). This is the event admin confirming how the event
# itself was settled.
EVENT_PAYMENT_MODE_OPTIONS = [_opt(x) for x in ["Cash", "GPay", "Internal Settle"]]

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
# "Converted" (2026-08-19, per Shruti follow-up: "add converted to the status
# dropdown for leads") is a DROPDOWN-ONLY value — it is never written to the
# `status` column (the leads_status_check constraint from migration 018
# deliberately excludes it; is_booking is the real conversion flag). Picking
# it and saving is special-cased in update_lead_status() to run the exact
# same conversion as the old dedicated Convert button (see _do_convert_lead())
# — hence LEAD_STATUSES (the real, storable set) stays separate from the
# dropdown's full option list.
LEAD_STATUS_DROPDOWN_VALUES = ["New", "Initial Discussions Done", "Proposal Sent", "Negotiations Ongoing", "Converted", "Not Interested", "DND"]
LEAD_STATUS_OPTIONS = [_opt(x) for x in LEAD_STATUS_DROPDOWN_VALUES]
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


# 2026-08-19, per Shruti follow-up: "if a booking is marked as cancelled, no
# further updates can be done on the values of the booking. same for leads
# that are marked as not converted." Locks the generic field-value editor
# (update_booking_field() below) only — status changes stay open for leads
# (Not Interested/DND -> anything else, including Converted) so a mis-click
# isn't a permanent dead end; a cancelled booking has no "un-cancel" path at
# all by design, so it's frozen for good once cancelled.
def _is_locked(is_booking: bool, status: Optional[str]) -> bool:
    if is_booking:
        return status == "Cancelled"
    return status in NON_CONVERT_STATUSES

# 2026-09-21, per Shruti (Image 7): the four Add-ons rows were plain text
# boxes — they are now dropdowns of the values the site itself offers. Prices
# shown are the same ones builder.html charges (mirrored in booking_pricing.py).
ADDON_LIGHTS_OPTIONS = [_opt("Yes", f"Yes - Rs. {DJ_LIGHTS_PRICE}"), _opt("No")]
ADDON_SMOKE_OPTIONS = [_opt("Yes", f"Yes - Rs. {DJ_SMOKE_PRICE}"), _opt("No")]
ADDON_NOTE_OPTIONS = [_opt("Yes", f"Yes - Rs. {TAG_NOTE_UNIT_PRICE}/gift (min. {TAG_NOTE_MIN_QTY})"), _opt("No")]
ADDON_PACKAGING_OPTIONS = [
    _opt("Paper Gift Bag", f"Paper Gift Bag - Rs. {PACKAGING_UNIT_PRICE['paper-bag']}/gift"),
    _opt("Gift Wrap", f"Gift Wrap - Rs. {PACKAGING_UNIT_PRICE['wrap']}/gift"),
    _opt("Gift Wrap + Paper Bag", f"Gift Wrap + Paper Bag - Rs. {PACKAGING_UNIT_PRICE['both']}/gift"),
    _opt("No packaging"),
]
# 2026-09-22, per Shruti — "this also should be a dropdown. don't add an
# MOQ. just give per bag pricing": same Yes/No + rate-in-the-label pattern
# as Lights/Smoke above, deliberately with no "(min. X)" clause like the
# Gift Note dropdown has, since there's no MOQ here.
ADDON_PINATA_BAGS_OPTIONS = [_opt("Yes", f"Yes - Rs. {PINATA_BAG_PRICE}/bag"), _opt("No")]

DROPDOWN_OPTIONS = {
    "addon_dj_lights": ADDON_LIGHTS_OPTIONS,
    "addon_dj_smoke": ADDON_SMOKE_OPTIONS,
    "addon_gift_packaging": ADDON_PACKAGING_OPTIONS,
    "addon_gift_note": ADDON_NOTE_OPTIONS,
    "addon_pinata_bags": ADDON_PINATA_BAGS_OPTIONS,
    "svc_decor": DECOR_OPTIONS,
    "svc_host": HOST_OPTIONS,
    "svc_dj": DJ_OPTIONS,
    "svc_photo": PHOTO_OPTIONS,
    "svc_pinata": PINATA_OPTIONS,
    "svc_einvite": EINVITE_OPTIONS,
    "bill_payment_method": PAYMENT_METHOD_OPTIONS,
    "bill_payment_status": PAYMENT_STATUS_OPTIONS,
    "event_payment_confirmed_mode": EVENT_PAYMENT_MODE_OPTIONS,
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
    # 2026-09-10, per Shruti — Balance Due only ever reads Discount %/Advance
    # Paid's CURRENT VALUE (see the Balance Due auto-calc below); Assigned
    # Value has no effect on either field, so a real number typed in here
    # instead used to silently do nothing to the totals. There's no
    # "vendor" for a percentage or a payment amount either, so this
    # placeholder just makes the dead end explicit instead of inviting it.
    "bill_discount_pct": "Not used — edit Current Value",
    "bill_advance": "Not used — edit Current Value",
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


_CUSTOMER_PAYMENT_LABELS = {
    "online": "UPI / Bank Transfer",
    "branch": "Cash Deposit at Wondershop Experiences Head Office",
    "collect": "Cash Collection at Venue",
}


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
        pk = snap.get("gift_packaging")
        if pk:
            return PACKAGING_KEY_TO_LABEL.get(pk, pk)
        return "No packaging" if snap.get("gifts") else None
    if key == "bill_payment_method":
        # Was missing, so the admin page said "None selected" for every order.
        pm = lead.get("payment_method")
        return _CUSTOMER_PAYMENT_LABELS.get(pm, pm) if pm else None
    if key == "addon_gift_note":
        v = snap.get("gift_thank_you_note")
        return None if v is None else ("Yes" if v else "No")
    if key in ("addon_pinata_bags", "addon_pinata_fillings"):
        return None  # admin-tracked only, no customer-side source

    if key == "bill_grand_total":
        # 2026-09-10, per Shruti — this used to read order_grand_total,
        # which is actually the CART SUBTOTAL BEFORE DISCOUNT (builder.html
        # calls it rawT() internally), not what the customer agreed to pay.
        # client_budget is builder.html's payTotal() — tp() (post-discount)
        # plus any collection fee/packaging/thank-you-note charges — i.e.
        # the real Grand Total. order_grand_total is still used internally
        # (see the live-recalculation block below) to work out how a
        # changed Discount % should move this number.
        v = lead.get("client_budget")
        return str(v) if v is not None else None
    if key == "bill_discount_pct":
        v = lead.get("order_discount_pct")
        return str(v) if v is not None else None
    if key == "bill_total_savings":
        v = lead.get("order_total_savings")
        return str(v) if v is not None else None
    if key == "bill_freebies":
        return lead.get("order_freebies_text") or None
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
    if change_type == "confirmed_by_parent":
        return f'{field_label}: confirmed by parent as "{new_d}" via the registration page on {ts}.'
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
        grand_total = lead.get("client_budget")
        if grand_total is not None and adv > float(grand_total):
            raise HTTPException(status_code=400, detail="Advance Paid cannot exceed the Grand Total.")

    if key == "event_payment_confirmed_amount":
        try:
            amt = float(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Event Payment Confirmed must be a number.")
        if amt < 0:
            raise HTTPException(status_code=400, detail="Event Payment Confirmed can't be negative.")

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

SORTABLE_COLUMNS = {"status", "created", "event_date", "modified"}


@router.get("/bookings")
async def list_bookings(kind: str = "lead", q: Optional[str] = None, sort: str = "created", dir: str = "desc", x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    is_booking = kind == "booking"
    where = ["is_booking = :is_booking"]
    values = {"is_booking": is_booking}
    if q:
        where.append("(parent_name ILIKE :like OR phone ILIKE :like OR email ILIKE :like OR CAST(lead_id AS TEXT) = :q)")
        values["like"] = f"%{q}%"
        values["q"] = q
    # No SQL-level ORDER BY/LIMIT here — sorting by "status" has to sort on
    # the DISPLAY status (New/Upcoming/Complete/Cancelled for bookings),
    # which for Upcoming/Complete only exists after _booking_display_status()
    # runs in Python (2026-08-19, per Shruti: "give sort on status, created,
    # event date ... applicable for bookings and leads"). Fetches every
    # matching row, computes display status, sorts, THEN slices to 200 — an
    # admin's lead/booking table is expected to stay well within a size where
    # that's cheap; if this table ever grows to tens of thousands of rows,
    # this should move to a SQL-side sort instead.
    rows = await database.fetch_all(
        f"""
        SELECT lead_id, parent_name, phone, email, event_date, city, status, created_on, updated_on, lead_origin
        FROM leads
        WHERE {' AND '.join(where)}
        """,
        values=values,
    )
    enriched = []
    new_count = 0
    for r in rows:
        row = dict(r)
        row["_display_status"] = _booking_display_status(row) if is_booking else row["status"]
        if row["_display_status"] == "New":
            new_count += 1
        enriched.append(row)

    # 2026-09-11, per Shruti — "add modified timestamp column ... add a sort
    # functionality on this as well." leads.updated_on alone only moves on a
    # DIRECT-WRITE edit (Customer & Event Details) or a status change — every
    # override edit (Services/Add-ons/Billing & Rewards, remarks, add/remove
    # field) writes to booking_field_overrides + booking_change_log instead
    # and never touches the leads row, so updated_on alone would miss most
    # actual admin edits. Modified is the more recent of the two: leads.
    # updated_on, and this lead's latest booking_change_log entry.
    lead_ids = [row["lead_id"] for row in enriched]
    latest_change = {}
    if lead_ids:
        # Named placeholders per id rather than a single array-bound ANY(:ids)
        # — safer across `databases`/asyncpg versions, and this only ever
        # covers however many leads/bookings matched the search (same size
        # ceiling the sort/slice above already accepts).
        id_params = {f"lid{i}": lid for i, lid in enumerate(lead_ids)}
        placeholders = ", ".join(f":{k}" for k in id_params)
        change_rows = await database.fetch_all(
            f"SELECT lead_id, MAX(changed_at) AS latest FROM booking_change_log WHERE lead_id IN ({placeholders}) GROUP BY lead_id",
            values=id_params,
        )
        latest_change = {r["lead_id"]: r["latest"] for r in change_rows}
    for row in enriched:
        candidates = [v for v in (row.get("updated_on"), latest_change.get(row["lead_id"])) if v is not None]
        row["modified_on"] = max(candidates) if candidates else None

    sort_key = sort if sort in SORTABLE_COLUMNS else "created"
    sort_desc = dir != "asc"

    def _sort_val(row):
        if sort_key == "status":
            return row["_display_status"]
        if sort_key == "event_date":
            return row["event_date"]
        if sort_key == "modified":
            return row["modified_on"]
        return row["created_on"]

    # None-safe: always push rows missing the sort value (e.g. no event_date
    # yet) to the end, regardless of asc/desc — reverse=True would otherwise
    # flip them to the front instead.
    with_val = [r for r in enriched if _sort_val(r) is not None]
    without_val = [r for r in enriched if _sort_val(r) is None]
    with_val.sort(key=_sort_val, reverse=sort_desc)
    ordered = (with_val + without_val)[:200]

    out = [{
        "lead_id": row["lead_id"],
        "parent_name": row["parent_name"],
        "phone": row["phone"],
        "email": row["email"],
        "event_date": _date_str(row["event_date"]),
        "city": row["city"],
        "status": row["_display_status"],
        "created_on_ist": _to_ist_str(row["created_on"]),
        "modified_on_ist": _to_ist_str(row["modified_on"]),
        # 2026-09-17, per Shruti — merging the admin Leads tab and the sales
        # module's own list into one browsable list: every row now says
        # where it came from, so the frontend can badge/filter Website vs
        # Sales-team leads and route a click into whichever detail page
        # actually has the right editor for that lead (sales-leads.html's
        # bespoke playbook UI for lead_origin='sales_module', this page's
        # generic field-table editor for everything else).
        "origin": "Sales" if row.get("lead_origin") == "sales_module" else "Website",
    } for row in ordered]
    return {"rows": out, "new_count": new_count}


# ─── DETAIL ───────────────────────────────────────────────────────────────

def _snapshot_has_spy_activity(snap: dict) -> bool:
    """True if builder_snapshot.activities (BAB origin) contains a Spy
    activity, matched by id — see catalogue_data.SPY_ACTIVITY_IDS."""
    acts = (snap or {}).get("activities") or []
    return any((a.get("id") in cat.SPY_ACTIVITY_IDS) for a in acts)


async def _sales_playbook_has_spy_activity(lead_id: int) -> bool:
    """True if the sales panel's own activities list (lead_sales_playbook —
    entirely separate from builder_snapshot, see sales_leads.py's
    _full_detail()) contains a Spy activity, matched by id. Only sales-
    origin leads have a playbook row at all; anything else is a no-op."""
    pb = await database.fetch_one(
        "SELECT activities FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id}
    )
    if not pb:
        return False
    acts = pb["activities"]
    acts = json.loads(acts) if isinstance(acts, str) else (acts or [])
    return any((a.get("id") in cat.SPY_ACTIVITY_IDS) for a in acts)


def _override_text_has_spy_activity(text: Optional[str]) -> bool:
    """True if an admin's own free-text edit of the Activities field (which
    only ever stores names, never ids — see update_booking_field()) names a
    Spy activity."""
    if not text:
        return False
    low = text.lower()
    if cat.SPY_MISSION_NAME_HINT in low:
        return True
    names = {n.strip() for n in text.split(",")}
    return bool(names & cat.SPY_ACTIVITY_NAMES)


async def _is_spy_booking(lead: dict, snap: dict, svc_activities_field: Optional[dict]) -> bool:
    """2026-09-23, per Shruti — "spy themed should be spy in the activities
    ... theme can be anything." Replaces the old theme-substring check
    (admin.html used to gate the Spy Agent Registration card on
    leads.theme.toLowerCase().includes('spy')) with the actual signal: a
    Spy activity actually on the booking, checked across every place one
    can be entered — the website builder, the sales panel, and a manual
    admin edit — OR the booking came from the dedicated Spy package sold on
    the homepage (spy-basic.html), even if that particular booking ended up
    with no individual Spy activity line item.
    """
    if (snap or {}).get("package_origin") == "spy-basic":
        return True
    if _snapshot_has_spy_activity(snap):
        return True
    # The live Activities field, whichever source is currently in effect
    # (admin override takes precedence over the derived original — same
    # precedence _full_detail()'s field-building loop already uses).
    if svc_activities_field and _override_text_has_spy_activity(svc_activities_field.get("customer_choice")):
        return True
    if lead.get("lead_origin") == "sales_module" and await _sales_playbook_has_spy_activity(lead["lead_id"]):
        return True
    return False


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
            # Items the customer got FREE at checkout (the Tattoo Station unlocked
            # by the discount slabs) — shown as locked "Freebie" rows, not editable.
            "locked_items": (freebie_activity_names(snap) or None) if key == "svc_activities" else None,
            "placeholder": ASSIGNED_PLACEHOLDERS.get(key),
            "original_value": original_value,
            "customer_choice": customer_choice,
            "assigned_value": updated_value,
            "remarks": ov["remarks"] if ov else None,
            "removed": bool(ov["removed"]) if ov else False,
            "updated_by": ov["updated_by"] if ov else None,
            "updated_at_ist": _to_ist_str(ov["updated_at"]) if ov else None,
        })

    # ─── Grand Total / Balance Due auto-calculation ────────────────────────
    # 2026-08-19, per Shruti: "fix the grand total now, it should be
    # autocalculated." 2026-09-10: it followed Discount % only. 2026-09-21
    # (Image 3/6): "grand total not changing even after making changes at the
    # admin side like changing category of the host, adding music, changing
    # the discount %" and "upon adding gifts, the final amount did not
    # change" — so Grand Total now follows EVERY change on this page.
    #
    # The customer's checkout total (leads.client_budget) is the starting
    # point; booking_pricing.recompute_grand_total() prices each difference
    # between what was booked (builder_snapshot) and what the page says now
    # (service tiers, music add-ons, activities, gifts + their packaging /
    # note fees, Discount %) and adds it on. An untouched booking therefore
    # always equals its checkout total. The rules and known limits are in
    # that module's docstring, and the itemised changes travel with the
    # response ("breakdown") so the page can show its working.
    #
    # Balance Due = Grand Total − Advance Paid, using each field's live
    # value (so it follows all of the above, and any Advance override).
    def _money(s):
        if s in (None, ""):
            return None
        try:
            return float(str(s).replace(",", "").replace("₹", "").strip())
        except ValueError:
            return None

    def _num_str(v):
        return str(int(v)) if v == int(v) else str(round(v, 2))

    all_fields = {f["field_key"]: f for fl in sections.values() for f in fl}
    billing_fields = {f["field_key"]: f for f in sections.get("Billing & Rewards", [])}
    grand_total_field = billing_fields.get("bill_grand_total")
    grand_total_val = _money(grand_total_field.get("customer_choice")) if grand_total_field else None

    discount_field = billing_fields.get("bill_discount_pct")
    orig_discount_val = _money(discount_field.get("original_value")) if discount_field else None
    new_discount_val = _money(discount_field.get("customer_choice")) if discount_field else None

    pricing = None
    if grand_total_field is not None:
        pricing = recompute_grand_total(
            lead, snap,
            {k: f.get("customer_choice") for k, f in all_fields.items()},
            {k for k, f in all_fields.items() if f.get("removed")},
            orig_discount_val, new_discount_val,
        )
    if pricing:
        grand_total_val = pricing["grand_total"]
        grand_total_field["customer_choice"] = _num_str(grand_total_val)
        grand_total_field["checkout_total"] = pricing["checkout_total"]
        grand_total_field["breakdown"] = pricing["adjustments"]
        grand_total_field["unpriced"] = pricing["unpriced"]

    advance_val = _money(billing_fields.get("bill_advance", {}).get("customer_choice"))
    balance_field = billing_fields.get("bill_balance")
    if balance_field is not None and grand_total_val is not None:
        computed_balance = grand_total_val - (advance_val or 0)
        display = _num_str(computed_balance)
        balance_field["customer_choice"] = display
        balance_field["original_value"] = display

    # 2026-09-21, per Shruti (Image 4): until the team has confirmed the
    # advance actually arrived (Payment Status = Advance Paid Verified or
    # Complete), the sub-note below (admin.html) flags it as not yet
    # confirmed. 2026-09-22: the label itself used to flip to "Advance
    # Pending" too, but that was dropped as redundant with the sub-note.
    pay_status_field = billing_fields.get("bill_payment_status")
    advance_confirmed = ((pay_status_field or {}).get("customer_choice") in ADVANCE_CONFIRMED_STATUSES)
    adv_field = billing_fields.get("bill_advance")
    if adv_field is not None:
        adv_field["advance_confirmed"] = advance_confirmed

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
    is_spy_booking = is_booking and await _is_spy_booking(lead, snap, all_fields.get("svc_activities"))
    return {
        "lead_id": lead_id,
        "is_booking": is_booking,
        "is_spy_booking": is_spy_booking,
        # Read-only computed status for a booking (New/Upcoming/Complete/
        # Cancelled); the raw editable pipeline status for a lead.
        "status": _booking_display_status(lead) if is_booking else lead.get("status"),
        # 2026-08-19, per Shruti follow-up — see _is_locked(): true once a
        # booking is Cancelled or a lead is Not Interested/DND. The frontend
        # renders every field row read-only and hides Save/Remove/+Add Field
        # when this is set; update_booking_field() enforces it server-side too.
        "locked": _is_locked(is_booking, lead.get("status")),
        "non_convert_reason": lead.get("non_convert_reason"),
        "non_convert_reason_other": lead.get("non_convert_reason_other"),
        "lead_status_options": LEAD_STATUS_OPTIONS,
        "non_convert_reason_options": NON_CONVERT_REASON_OPTIONS,
        "created_on_ist": _to_ist_str(lead.get("created_on")),
        "invoice_number": lead.get("invoice_number"),
        "invoice_sent_at_ist": _to_ist_str(lead.get("invoice_sent_at")) if lead.get("invoice_sent_at") else None,
        # Whether the booking emails actually went out (migration 033) — a Gmail
        # failure used to be visible only in the Railway log.
        "email_status": {
            kind: {
                "status": lead.get(f"{kind}_email_status"),
                "error": lead.get(f"{kind}_email_error"),
                "at_ist": _to_ist_str(lead.get(f"{kind}_email_at")) if lead.get(f"{kind}_email_at") else None,
            } for kind in ("customer", "team")
        },
        "advance_confirmed": advance_confirmed,
        "pricing": ({"subtotal": pricing["subtotal"], "checkout_total": pricing["checkout_total"], "discount_amt": pricing["discount_amt"],
                     "adjustments": pricing["adjustments"], "unpriced": pricing["unpriced"]} if pricing else None),
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


# 2026-09-22, per Shruti — "add a new sheet in the google sheet with serial
# no., event name (child's name, gender, age, location), theme, list of
# services (comma separated), date, venue and the photos link. One event
# can have multiple photos link as well." Pushed to a new "Event Photos" tab
# via the same Apps Script webhook the rest of the site already posts to
# (see google_sheet_webhook.js's "update_event_photos" action) — upserts by
# Lead ID (carried as a trailing internal column on that tab, past the
# requested columns, so it doesn't disturb the layout Shruti asked for) so
# re-saving this field updates the same row instead of piling up duplicates.
async def _push_event_photos_to_sheet(lead_id: int, lead: dict, snap: dict, photos_value: str) -> None:
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping Event Photos sheet update")
        return

    def _first(csv_val) -> str:
        return str(csv_val or "").split(",")[0].strip()

    # "Event Name (Child's name, Gender, Age, Location)" — location = City,
    # same field admin.html's own summary card uses for "Address". Only the
    # first child is used for multi-child bookings (this is a quick-ID
    # column, not the full record — admin.html itself has the rest).
    event_name = ", ".join(filter(None, [
        _first(lead.get("child_names")),
        _first(lead.get("child_genders")),
        _first(lead.get("child_ages")),
        (lead.get("city") or "").strip(),
    ]))

    cols = _sheet_service_columns(snap)
    services = ", ".join(label for key, label in [
        ("decor", "Decor"), ("pinata", "Pinata"), ("return_gifts", "Return Gifts"),
        ("music", "Music"), ("host", "Host"), ("activities", "Activities"),
        ("photography", "Photography"), ("einvite", "E-Invite"),
    ] if cols.get(key))

    event_date = lead.get("event_date")
    payload = {
        "action":      "update_event_photos",
        "lead_id":     lead_id,
        "event_name":  event_name,
        "theme":       lead.get("theme") or "",
        "services":    services,
        "event_date":  event_date.isoformat() if event_date else "",
        "venue":       lead.get("venue") or "",
        "photos_link": photos_value or "",
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Lead #{lead_id}: Event Photos sheet update → {r.status_code}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: Event Photos sheet update failed — {exc}")


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

    # 2026-08-19, per Shruti follow-up: "if a booking is marked as cancelled,
    # no further updates can be done on the values of the booking. same for
    # leads that are marked as not converted." Enforced here (not just in the
    # frontend) since this is the one endpoint that actually writes field
    # values — status changes (which can un-lock a lead) go through a
    # separate endpoint and are deliberately NOT gated by this check.
    if _is_locked(bool(lead.get("is_booking")), lead.get("status")):
        raise HTTPException(status_code=400, detail="This record is locked — cancelled bookings and non-converted leads can no longer be edited.")

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

    # 2026-09-21, per Shruti (Image 5): a freebie unlocked through the discount
    # slabs (the Tattoo Station) is not editable — it can't be dropped from the
    # activities list or have the whole field removed.
    if key == "svc_activities":
        locked = freebie_activity_names(snap)
        if locked:
            kept = {n for n, _q in _parse_csv_names(new_customer_choice)}
            if body.removed or (new_customer_choice and any(n not in kept for n in locked)):
                raise HTTPException(
                    status_code=400,
                    detail=f"{', '.join(locked)} is a free booking unlocked through the discount slabs and can't be removed or changed here.",
                )

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

    # 2026-09-22, per Shruti — the one field on this page that DOES push to
    # the Google Sheet (see _push_event_photos_to_sheet above). Skipped on
    # a clear/remove — no point creating an "Event Photos" row for an event
    # that doesn't have a link yet.
    if key == "event_photos_link" and not body.removed and new_customer_choice:
        await _push_event_photos_to_sheet(lead_id, lead, snap, new_customer_choice)

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
# 2026-08-19, per Shruti follow-up — shared by both the dedicated /convert
# endpoint AND update_lead_status() below when "Converted" is picked from
# the status dropdown ("add converted to the status dropdown for leads ...
# if a lead is converted, move it to the bookings tab. maintain edit history
# ... converted marked by whom"). Single source of truth for the actual
# is_booking flip so both entry points log identically.
async def _do_convert_lead(lead_id: int, who: str) -> None:
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


@router.post("/bookings/{lead_id}/status")
async def update_lead_status(lead_id: int, body: StatusUpdateRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    who = body.changed_by.strip()

    new_status = (body.status or "").strip()

    # "Converted" never touches the leads.status column (see
    # LEAD_STATUS_DROPDOWN_VALUES above) — picking it and saving runs the
    # exact same is_booking flip as the old dedicated Convert button, so the
    # row moves to the Bookings tab and the change log records who converted it.
    if new_status == "Converted":
        await _do_convert_lead(lead_id, who)
        return {"success": True, "status": "Converted", "is_booking": True}

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
# Kept as its own endpoint for any caller that wants a direct "convert" verb
# without going through the status dropdown; update_lead_status() above
# calls the same _do_convert_lead() helper when "Converted" is picked there.
@router.post("/bookings/{lead_id}/convert")
async def convert_lead_to_booking(lead_id: int, body: ChangedByRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")
    await _do_convert_lead(lead_id, body.changed_by.strip())
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
    if lead_row["status"] == "Cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled.")

    now = datetime.utcnow()
    await database.execute("UPDATE leads SET status = 'Cancelled' WHERE lead_id = :id", values={"id": lead_id})
    await _log_status_change(lead_id, lead_row["status"], "Cancelled", who, now)
    return {"success": True, "status": "Cancelled"}


# ─── INVOICE — SEND / RESEND ────────────────────────────────────────────────
# 2026-09-11, per Shruti: "had a manual trigger to send the update invoice
# from admin" — the original invoice already goes out automatically as an
# email attachment the moment a booking is confirmed (see routers/leads.py's
# _send_user_ack). This is the follow-up: whenever an admin has changed
# Discount % / Advance Paid / other billing fields after the fact (via the
# Billing & Rewards overrides above), this rebuilds the invoice from the
# CURRENT live-recalculated figures (the same ones get_booking_detail()
# already computes for this page) and re-sends it — reusing the same
# invoice number every time so the customer never gets two different
# numbers for one booking.
def _money(s):
    if s in (None, ""):
        return None
    try:
        return float(str(s).replace(",", "").replace("₹", "").replace("Rs.", "").strip())
    except ValueError:
        return None


@router.post("/bookings/{lead_id}/invoice/send")
async def send_booking_invoice(lead_id: int, body: ChangedByRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    lead = dict(lead_row)
    if not lead.get("is_booking"):
        raise HTTPException(status_code=400, detail="This is a lead, not a confirmed booking — nothing to invoice yet.")
    if not lead.get("email"):
        raise HTTPException(status_code=400, detail="This booking has no email on file — nothing to send the invoice to.")

    # Reuse get_booking_detail()'s own live billing recalculation (Discount
    # %-driven Grand Total, Balance Due = Grand Total − Advance Paid, with
    # every admin override already folded in) instead of duplicating that
    # delicate math here.
    detail = await get_booking_detail(lead_id, x_admin_password)
    pricing = detail.get("pricing")
    billing = {f["field_key"]: f for s in detail["sections"] if s["section"] == "Billing & Rewards" for f in s["fields"]}

    def _choice(key):
        f = billing.get(key)
        return f.get("customer_choice") if f else None

    snap = _parse_snapshot(lead.get("builder_snapshot"))
    fake_req = SimpleNamespace(builder_snapshot=snap, child_names=lead.get("child_names"), child_ages=lead.get("child_ages"), payment_method=lead.get("payment_method"))

    invoice_number = await _get_or_create_invoice_number(lead_id)
    data = assemble_invoice_data(
        lead_id=lead_id,
        invoice_number=invoice_number,
        invoice_date_str=_fmt_date_long(date_cls.today()),
        parent_name=lead.get("parent_name"),
        phone=lead.get("phone"),
        email=lead.get("email"),
        event_title=_party_title(fake_req) or "Birthday Party",
        event_date_str=_fmt_date_long(lead.get("event_date")),
        event_time=lead.get("event_time"),
        venue=lead.get("venue"),
        city=lead.get("city"),
        services_detail=_services_detail_list(fake_req),
        subtotal=(pricing["subtotal"] if pricing else _money(lead.get("order_grand_total"))),
        discount_pct=_money(_choice("bill_discount_pct")),
        grand_total=_money(_choice("bill_grand_total")),
        advance_paid=_money(_choice("bill_advance")),
        balance_due=_money(_choice("bill_balance")),
        total_savings=_money(_choice("bill_total_savings")),
        freebies_text=_choice("bill_freebies"),
        payment_method=lead.get("payment_method"),
        # Original fee rows + one signed row per admin change (the Discount
        # % change isn't a row — the summary's Discount line already shows it),
        # so the itemised list explains why the total moved.
        extra_fee_rows=_order_addon_rows_raw(fake_req) + [
            (f"Updated — {a['label']}", a["amount"])
            for a in ((pricing or {}).get("adjustments") or []) if not a["label"].startswith("Discount")
        ],
        advance_confirmed=bool(detail.get("advance_confirmed")),
        discount_amt=(pricing.get("discount_amt") if pricing else None),
        gst_enabled=settings.GST_ENABLED,
        gstin=settings.GSTIN,
        gst_rate_pct=settings.GST_RATE_PCT,
    )
    pdf_bytes = build_invoice_pdf(data)
    filename = invoice_filename(data)

    who = body.changed_by.strip()
    subject = f"📄 Your Updated Wondershop Invoice (Order #{lead_id})"
    first_name = (lead.get("parent_name") or "there").split()[0]
    body_text = (
        f"Hi {first_name},\n\n"
        f"Here's your updated invoice for booking #{lead_id} ({invoice_number}), reflecting the "
        f"current order figures.\n\n"
        f"If anything looks off, just reply to this email or WhatsApp us at +91 90044 35362.\n\n"
        f"Warmly,\nTeam Wondershop 🎈\nwondershopexperiences.com\n"
    )
    await _gmail_send(
        to_email=lead["email"], subject=subject, body=body_text,
        attachments=[(filename, pdf_bytes, "application", "pdf")],
    )
    now = datetime.utcnow()
    await database.execute("UPDATE leads SET invoice_sent_at = :now WHERE lead_id = :id", values={"now": now, "id": lead_id})
    await database.execute(
        """
        INSERT INTO booking_change_log
            (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
        VALUES
            (:lead_id, 'invoice', 'Invoice', 'invoice_sent', NULL, :new_v, :by, :ts)
        """,
        values={"lead_id": lead_id, "new_v": f"{invoice_number} resent to {lead['email']}", "by": who, "ts": now},
    )
    logger.info(f"Lead #{lead_id}: updated invoice ({invoice_number}) sent to {lead['email']} by {who}")
    return {"success": True, "invoice_number": invoice_number, "sent_to": lead["email"]}


class SendSummaryEmailRequest(ChangedByRequest):
    attach_invoice: bool = False


# ─── SUMMARY / CONFIRMATION EMAIL — RESEND ──────────────────────────────────
# 2026-09-23, per Shruti: a manual "resend the original confirmation/enquiry
# email" button from admin, for both leads and confirmed bookings alike,
# with an optional checkbox to attach the invoice PDF. The invoice is no
# longer auto-attached at booking time (see _send_user_ack in
# routers/leads.py -- an order can still change right up to the last
# minute), so this checkbox and the "Send Invoice" button above are now the
# only two ways an invoice ever goes out, both manual, once the team
# decides the booking is actually complete.
@router.post("/bookings/{lead_id}/summary/send")
async def send_summary_email(lead_id: int, body: SendSummaryEmailRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.changed_by or not body.changed_by.strip():
        raise HTTPException(status_code=400, detail="changed_by is required.")

    lead_row = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead_row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    lead = dict(lead_row)
    if not lead.get("email"):
        raise HTTPException(status_code=400, detail="This record has no email on file — nothing to send to.")

    # Rebuild the same LeadSubmitRequest shape /submit originally built,
    # straight off the current DB row -- LeadSubmitRequest's field names
    # mirror the leads table columns 1:1 (see _append_to_sheet's payload
    # dict for the same mapping), so a resend always reflects whatever the
    # team has since edited on the booking, not the stale original submit.
    #
    # 2026-09-23, per Shruti's "didn't get the email" report on Swati's
    # booking #3: this reconstruction is NOT the same safety net
    # send_booking_invoice() above uses (a loose SimpleNamespace) -- it's a
    # real pydantic model, so a DB row whose column types/values don't line
    # up with LeadSubmitRequest's field types (e.g. something stored where
    # a field expects a clean number) raises ValidationError here, OUTSIDE
    # of _send_user_ack's own try/except (that only wraps the send itself).
    # Uncaught, that crashed the request with a bare unhelpful 503 and no
    # server-side trace of what went wrong -- wrapping it turns that into a
    # real 502 with the actual pydantic error, so the team sees why instead
    # of a silent failure, and we can fix the specific field next time.
    try:
        snap = _parse_snapshot(lead.get("builder_snapshot"))
        req_fields = {k: lead.get(k) for k in LeadSubmitRequest.model_fields if k in lead}
        req_fields["builder_snapshot"] = snap
        fake_req = LeadSubmitRequest(**req_fields)
    except Exception as build_exc:
        logger.error(f"Lead #{lead_id}: couldn't rebuild the submission from the DB row for a summary-email resend — {build_exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Couldn't rebuild this booking's data to resend the email — {build_exc}",
        )

    who = body.changed_by.strip()
    # 2026-09-23, per Shruti: "Resend Summary Email" was coming back as a
    # bare, contentless failure for EVERY booking (not just ones with odd
    # data -- confirmed on both Swati's #3 and a normal fully-formed
    # booking, #2), even after the LeadSubmitRequest-rebuild try/except
    # above. Whatever's actually failing was happening somewhere past that
    # point, fast enough that nothing ever got logged -- which is exactly
    # what an unbounded hang (Gmail/DB call that never returns, gateway
    # eventually giving up with no app-level trace at all) looks like from
    # the outside. Wrapping the rest of the endpoint two ways: a hard
    # timeout around the actual send so a hang becomes a clean, visible
    # error instead of a silent one, and a catch-all around everything
    # else so ANY exception here comes back as a real message instead of a
    # bare 503.
    try:
        reward_row = await database.fetch_one(
            "SELECT code FROM reward_codes WHERE issued_lead_id = :id ORDER BY issued_at DESC LIMIT 1", values={"id": lead_id}
        )
        referral_row = await database.fetch_one(
            "SELECT code FROM referral_codes WHERE owner_lead_id = :id ORDER BY created_at DESC LIMIT 1", values={"id": lead_id}
        )
        reward_code = reward_row["code"] if reward_row else None
        referral_code = referral_row["code"] if referral_row else None

        # 2026-09-23, per Shruti: sales can assign services (E-Invite,
        # Activities, etc.) and add remarks entirely through the admin
        # override system without ever touching builder_snapshot -- e.g.
        # Swati's booking #3, entered by sales with no builder journey at
        # all, so its snapshot has no einvite/activities in it even though
        # the admin page clearly shows "Spy x K-Pop" / "Spy Treasure Hunt"
        # as the current value for those fields. The summary email only
        # ever read builder_snapshot, so it silently dropped all of that.
        # Pull the sales panel's current values in here and fold them into
        # what _send_user_ack renders, so the email matches what's
        # actually on the admin page instead of just what came through the
        # website builder.
        overrides = await database.fetch_all(
            "SELECT field_key, field_label, customer_choice_override, assigned_value, remarks "
            "FROM booking_field_overrides WHERE lead_id = :id AND removed = FALSE",
            values={"id": lead_id},
        )
        overrides_by_key = {o["field_key"]: o for o in overrides}
        snap = dict(fake_req.builder_snapshot or {})

        act_ov = overrides_by_key.get("svc_activities")
        if not any((a or {}).get("n") for a in (snap.get("activities") or [])) and act_ov:
            act_value = (act_ov["customer_choice_override"] or act_ov["assigned_value"] or "").strip()
            if act_value:
                acts = []
                for name, _qty in _parse_csv_names(act_value):
                    match = next((a for a in cat.ACTIVITIES if a[1] == name), None)
                    acts.append({"n": name, "id": match[0] if match else None, "p": match[2] if match else None})
                if acts:
                    snap["activities"] = acts

        einv_ov = overrides_by_key.get("svc_einvite")
        if not (snap.get("einvite") or {}).get("n") and einv_ov:
            einv_value = (einv_ov["customer_choice_override"] or einv_ov["assigned_value"] or "").strip()
            if einv_value and einv_value != "No selection":
                match = next((i for i in cat.INVITES if i[1] == einv_value), None)
                snap["einvite"] = {"n": einv_value, "id": match[0] if match else None}

        # 2026-09-23, per Shruti — "decor is chosen in admin but is not
        # showing up in the email": same gap as activities/einvite above,
        # just for Decor. _resolve_decor_override best-effort reconstructs
        # the {"n","id","p"} shape _services_detail_list expects from the
        # override's plain display string.
        decor_ov = overrides_by_key.get("svc_decor")
        if not (snap.get("decor") or {}).get("n") and decor_ov:
            decor_value = (decor_ov["customer_choice_override"] or decor_ov["assigned_value"] or "").strip()
            decor_entry = _resolve_decor_override(decor_value)
            if decor_entry:
                snap["decor"] = decor_entry

        if snap != (fake_req.builder_snapshot or {}):
            fake_req.builder_snapshot = snap

        extra_remarks = [
            f"{o['field_label']}: {o['remarks'].strip()}"
            for o in overrides if o["remarks"] and o["remarks"].strip()
        ]
        # 2026-09-23, per Shruti — "there were some T&C/comments put in the
        # sales panel for this lead like we promised neon lights, a fake
        # dead body - that should also be mentioned in the email": these
        # live on lead_sales_playbook (the separate Sales Leads module),
        # not booking_field_overrides, so they need their own fetch.
        playbook = await database.fetch_one(
            "SELECT notes_special_instructions, notes_changes_updates FROM lead_sales_playbook WHERE lead_id = :id",
            values={"id": lead_id},
        )
        if playbook:
            if playbook["notes_special_instructions"] and playbook["notes_special_instructions"].strip():
                extra_remarks.append(f"Client Special Instructions (sales): {playbook['notes_special_instructions'].strip()}")
            if playbook["notes_changes_updates"] and playbook["notes_changes_updates"].strip():
                extra_remarks.append(f"Changes / Last-Minute Updates (sales): {playbook['notes_changes_updates'].strip()}")
        if extra_remarks:
            combined = "\n".join(extra_remarks)
            fake_req.remarks = f"{fake_req.remarks}\n{combined}" if fake_req.remarks else combined

        # _send_user_ack never raises on its own (by design, for the
        # original fire-and-forget /submit flow) -- it always records the
        # outcome on the lead row instead. asyncio.wait_for is the backstop
        # for the failure mode that isn't a raised exception at all: the
        # Gmail token/send calls each carry their own httpx timeout
        # (10s/15s), but if either one hangs at the connection level below
        # httpx's own timeout handling, this still bounds it instead of
        # tying up the request indefinitely.
        await asyncio.wait_for(
            _send_user_ack(lead_id, fake_req, reward_code, referral_code, attach_invoice=body.attach_invoice),
            timeout=45,
        )

        status_row = await database.fetch_one(
            "SELECT customer_email_status, customer_email_error FROM leads WHERE lead_id = :id", values={"id": lead_id}
        )
        if status_row and status_row["customer_email_status"] == "failed":
            raise HTTPException(
                status_code=502,
                detail=f"Something went wrong sending the email — {status_row['customer_email_error'] or 'unknown error'}",
            )

        now = datetime.utcnow()
        # 2026-09-23, per Shruti: the dedicated "Send Invoice" button is
        # gone from the admin UI -- this checkbox is now the only way an
        # invoice goes out, so this has to persist invoice_sent_at itself
        # (the same column the old dedicated endpoint set) or admin.html's
        # "Invoice last sent" field would silently stop updating forever.
        invoice_number = None
        if body.attach_invoice and lead.get("is_booking"):
            invoice_number = await _get_or_create_invoice_number(lead_id)
            await database.execute(
                "UPDATE leads SET invoice_sent_at = :now WHERE lead_id = :id", values={"now": now, "id": lead_id}
            )
        await database.execute(
            """
            INSERT INTO booking_change_log
                (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
            VALUES
                (:lead_id, 'summary_email', 'Summary Email', 'email_sent', NULL, :new_v, :by, :ts)
            """,
            values={
                "lead_id": lead_id,
                "new_v": f"resent to {lead['email']}" + (f" (with invoice {invoice_number})" if invoice_number else ""),
                "by": who, "ts": now,
            },
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.error(f"Lead #{lead_id}: summary-email resend timed out after 45s (by {who})")
        raise HTTPException(
            status_code=502,
            detail="Sending the email took too long and timed out. It may or may not have gone out — please check the Gmail sent folder before resending again.",
        )
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: summary-email resend crashed unexpectedly — {exc}")
        raise HTTPException(status_code=502, detail=f"Something unexpected went wrong resending this email — {exc}")

    logger.info(f"Lead #{lead_id}: summary email resent to {lead['email']} by {who} (attach_invoice={body.attach_invoice})")
    return {"success": True, "sent_to": lead["email"], "invoice_number": invoice_number}


# ─── EMAIL CHECK ────────────────────────────────────────────────────────────
# 2026-09-21, per Shruti: "mail didn't go for the booking that we just did".
# One button on the admin page that answers "can this server send email right
# now?" without needing the Railway logs: it checks the three GMAIL_* settings
# exist, that Google still accepts the stored refresh token, then sends a real
# test message to the team address. The reply carries Google's own reason when
# something is wrong. Nothing secret is ever returned.
@router.post("/email-check")
async def email_check(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    missing = [n for n in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN") if not getattr(settings, n, "")]
    if missing:
        return {"ok": False, "stage": "settings",
                "message": f"Not set on the server (Railway → Variables): {', '.join(missing)}."}
    try:
        await _get_gmail_access_token()
    except Exception as exc:
        return {"ok": False, "stage": "sign-in", "message": str(exc)}
    try:
        await _gmail_send(
            to_email=settings.EMAIL_TEAM,
            subject="Wondershop email check — this server can send email",
            body="This is a test message from the admin panel's email check. If you can read it, booking emails can be sent.",
        )
    except Exception as exc:
        return {"ok": False, "stage": "send", "message": str(exc)[:500]}
    return {"ok": True, "stage": "sent", "message": f"Test email sent to {settings.EMAIL_TEAM}. Check that inbox (and Spam)."}
