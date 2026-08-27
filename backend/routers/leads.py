"""
Leads endpoint — captures inbound enquiries before they become orders.
Source of truth: WS_DataDictionary_v1.docx (leads table)

On every new lead submission, four things fire in parallel (fire-and-forget):
  1. User acknowledgement email  → req.email
  2. Team notification email     → settings.EMAIL_TEAM
  3. Google Sheet row append     → settings.GOOGLE_SHEET_WEBHOOK_URL
  4. WhatsApp alert              → WS_PHONE_1 + WS_PHONE_2 via AiSensy

req.is_booking distinguishes a CONFIRMED BOOKING (from builder.html's
checkout step, doCo()) from an unconfirmed LEAD (custom-request form,
doLead()) — this drives email tone/content, the Sheet Status column, and
the DB status value (2026-08-11, per Shruti).
"""
import json
import random
import re
import string
import asyncio
import logging
import httpx
import urllib.parse
from datetime import datetime, date, timedelta, time as dt_time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from database import database
from config import settings
from order_form_builder import (
    assemble_order_form_data, fetch_order_form_images, build_order_form_xlsx,
    build_order_form_pdf, order_form_filename,
)
import catalogue_data as cat

router = APIRouter()
logger = logging.getLogger(__name__)

# Live site — used to build absolute links (T&C) and inline email images.
SITE_BASE_URL = "https://wondershop-exp.github.io/wondershop-website"
MASCOT_URL    = f"{SITE_BASE_URL}/img/icons/icon-mascot.png"
LOGO_URL      = f"{SITE_BASE_URL}/logo-horizontal.png"
TERMS_URL     = f"{SITE_BASE_URL}/terms.html"

BRAND_PINK   = "#E65A96"
BRAND_PURPLE = "#8A67BE"
BRAND_DARK   = "#2D2140"
BRAND_LIGHT  = "#FBF6FF"


# ─── SCHEMA ──────────────────────────────────────────────────────────────────

class LeadSubmitRequest(BaseModel):
    parent_name:        str
    phone:              str         # 10 digits
    child_names:        Optional[str]   = None
    email:              Optional[str]   = None
    event_date:         Optional[date]  = None
    event_time:         Optional[str]   = None
    kids_count:         Optional[int]   = None
    child_ages:         Optional[str]   = None
    child_genders:      Optional[str]   = None
    # 2026-08-14, per Shruti — persisted both to the Google Sheet
    # (_append_to_sheet) and the `leads` DB table (see migration 013).
    child_dobs:         Optional[str]   = None
    venue:              Optional[str]   = None
    # Venue Google Maps share link + on-site contact person (2026-08-11).
    venue_maps_link:    Optional[str]   = None
    venue_contact_name: Optional[str]   = None
    venue_contact_phone:Optional[str]   = None
    location_type:      Optional[str]   = None
    theme:              Optional[str]   = None
    city:               Optional[str]   = None
    pincode:            Optional[str]   = None
    client_budget:      Optional[float] = None
    builder_snapshot:   Optional[dict]  = None
    remarks:            Optional[str]   = None
    lead_source:        Optional[str]   = "Website"
    lead_source_detail: Optional[str]   = None
    referred_by:        Optional[str]   = None
    # True only for a confirmed checkout submission (doCo()) — False/omitted
    # for an unconfirmed enquiry (doLead()). Drives email tone, Sheet Status
    # column ("Confirmed" vs "Lead"), and the DB is_booking flag (which
    # table — Leads or Bookings — the row shows up in, in admin.html).
    is_booking:         Optional[bool]  = False
    # Order summary — sent from the checkout step so the confirmation email
    # can show a full bill, not just the payable total (client_budget).
    order_grand_total:  Optional[float] = None
    order_discount_pct: Optional[float] = None
    order_advance:      Optional[float] = None
    order_balance:      Optional[float] = None
    # 2026-08-24, per Shruti (Image 3c) — "the same [freebies/discounts]
    # should be visible on the admin page and the emails that goes to the
    # customers and the operations team." order_discount_pct alone is a
    # percentage of the grand total and doesn't capture freebie item value
    # (see builder.html's trueMRP()) — order_total_savings is the full ₹
    # savings figure (auto/flat discount + unlocked freebie items, same
    # basis as the bottom bar / checkout Order Summary / Review page), and
    # order_freebies_text is a human-readable list of which freebies were
    # unlocked (e.g. "Free E-Invite, Free Tattoo Artist"). See migrations/
    # 019_add_order_savings_freebies_to_leads.sql.
    order_total_savings: Optional[float] = None
    order_freebies_text: Optional[str]   = None
    # We don't process any payment automatically on the website — every
    # method is self-reported by the customer and manually reconciled by
    # the team (2026-08-12, per Shruti). payment_status is always a
    # "pending" value at submit time; nothing is ever auto-marked Paid.
    payment_method:     Optional[str]   = None
    payment_status:     Optional[str]   = None
    # Post-booking scratch-card reward — only set when the customer won
    # something (reward_type is None/omitted for "better luck next time").
    reward_type:        Optional[str]   = None
    reward_label:       Optional[str]   = None
    reward_value:       Optional[float] = None
    reward_terms:       Optional[str]   = None
    reward_expiry:      Optional[date]  = None
    # A previously-issued reward coupon code being redeemed on THIS booking
    # (entered in the checkout "Coupon / Referral Code" box). Only honoured
    # if it matches the mobile number it was issued to, isn't expired, and
    # hasn't been used before.
    redeemed_coupon_code: Optional[str] = None
    # Return-gift delivery details — captured on the builder's Return Gifts
    # step (Delivery Details block); only meaningful when gifts were added.
    gift_delivery_address:      Optional[str]  = None
    gift_delivery_maps_link:    Optional[str]  = None
    gift_delivery_address_type: Optional[str]  = None
    gift_delivery_contact:      Optional[str]  = None   # contact person's name
    gift_delivery_contact_phone:Optional[str]  = None   # contact person's phone (2026-08-11)
    gift_required_by_date:      Optional[date] = None
    # Music add-ons (internal field names still say "dj" — see builder.html
    # for the same convention) — Music Lights (Rs.1,500) / Smoke Machine
    # (Rs.2,000). Replaces the old "Signature DJ" tier, which bundled both
    # at a fixed higher price.
    dj_lights_addon:            Optional[bool] = False
    dj_smoke_machine_addon:     Optional[bool] = False
    # Personal attribution code for a team member (see _check_sales_lead_code)
    # — no discount, just credits them as Event Sales Lead on the order form.
    sales_lead_code:            Optional[str]  = None
    # Birthday child's interests, picked on Step 0 (2026-08-17, per Shruti)
    # — comma-joined category labels (e.g. "Science & Experiments, Sports &
    # Games"), plus free text when "Something Else" was picked. Not used for
    # any pricing/logic server-side — purely so the team can see what drove
    # the recommendations shown, and spot patterns worth adding as real
    # categories later. See migrations/015_add_interests_to_leads.sql.
    interests:                   Optional[str]  = None
    interest_other:              Optional[str]  = None


class CouponValidateRequest(BaseModel):
    code:  str
    phone: str    # normalised +91XXXXXXXXXX, matching how it was issued


# Fired from builder.html after 10 minutes of zero interaction in the
# cart/checkout with no submission yet — see wsReportAbandonedCart() there.
# Deliberately minimal: whatever's been filled in so far, keyed on phone
# (the one thing the team actually needs to place a call).
class AbandonedCartRequest(BaseModel):
    phone:              str
    parent_name:        Optional[str]  = None
    email:              Optional[str]  = None
    child_names:        Optional[str]  = None
    event_date:         Optional[date] = None
    kids_count:         Optional[int]  = None
    theme:              Optional[str]  = None
    venue:              Optional[str]  = None
    pincode:            Optional[str]  = None
    # Which builder step they stalled on, and for how long — helps the
    # team spot patterns (e.g. everyone stalling on the same step).
    last_screen:        Optional[str]  = None
    idle_minutes:       Optional[int]  = None
    builder_snapshot:   Optional[dict] = None
    lead_source:        Optional[str]  = "Website - Cart Abandoned"
    lead_source_detail: Optional[str]  = None
    page_url:           Optional[str]  = None


# ─── FORMAT HELPERS ──────────────────────────────────────────────────────────

# S.payMethod values from builder.html's checkout -> human-readable labels
# for the order-summary email/order-form (2026-08-12, per Shruti).
_PAYMENT_METHOD_LABELS = {
    "online":  "UPI / Bank Transfer",
    "branch":  "Cash Deposit at Branch",
    "collect": "Cash Collection at Venue",
}

# "Cash Collection at Venue" means nothing has been paid yet at all — the
# generic "Pending Verification" wording (written for online/branch, where
# something HAS actually been paid and just needs the team to check it) is
# misleading there. Cash-collection orders get their own plain "Pending"
# status instead (2026-08-12, per Shruti).
def _payment_status_text(req: LeadSubmitRequest) -> str:
    if req.payment_method == "collect":
        return "⏳ Pending — to be collected at your event venue"
    return "⏳ Pending Verification — team will confirm once payment is checked"


def _fmt_rupees(amount: Optional[float]) -> str:
    return f"Rs.{amount:,.0f}" if amount is not None else "—"

def _fmt_date_long(d: Optional[date]) -> str:
    """'11 August 2026' — no leading zero on the day."""
    if not d:
        return "—"
    return f"{d.day} {d.strftime('%B %Y')}"

def _fmt_date_short(d: Optional[date]) -> str:
    """'3 Oct 2026' — no leading zero, abbreviated month. Used in the
    internal team email subject lines (2026-08-16, per Shruti)."""
    if not d:
        return "—"
    return f"{d.day} {d.strftime('%b %Y')}"

_VENUE_TBD_SUFFIX_RE = re.compile(r"\s*\(exact venue address to be confirmed\)\s*$", re.IGNORECASE)

def _clean_location(text: Optional[str]) -> str:
    """Strips the "(exact venue address to be confirmed)" placeholder
    suffix — added client-side onto the venue/address text whenever Venue
    Type is "Not Decided Yet" (see builder.html's doCo()) — so subject
    lines show just the locality, e.g. "Vikhroli" instead of "Vikhroli
    (exact venue address to be confirmed)" (2026-08-16, per Shruti)."""
    if not text:
        return "—"
    cleaned = _VENUE_TBD_SUFFIX_RE.sub("", text).strip()
    return cleaned or "—"

def _phone_local(phone: Optional[str]) -> str:
    """Strips the leading "+91" country code for a compact subject-line
    display (e.g. "9742240477" instead of "+919742240477")."""
    p = (phone or "").strip()
    if p.startswith("+91"):
        p = p[3:]
    return p or "—"

def _cap_first(s: Optional[str]) -> str:
    """Capitalises only the first letter, leaving the rest of the name's
    casing untouched (so 'test' -> 'Test', 'McDonald' stays 'McDonald')."""
    s = (s or "").strip()
    return (s[:1].upper() + s[1:]) if s else "there"

def _html_escape(s) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ordinal(n: int) -> str:
    """5 -> '5th', 1 -> '1st', 22 -> '22nd', 11 -> '11th' (the 11-13 teens
    are always 'th', not 'st'/'nd'/'rd')."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _party_title(req: "LeadSubmitRequest") -> Optional[str]:
    """"IDHIKA's 5th Birthday Party" — first child's name (all caps, per
    Shruti 2026-08-14 follow-up) + turning age, shown above the email
    heading and on the order confirmation page (2026-08-14, per Shruti).
    None if the name itself is missing — nothing sensible to show without a
    name. The age suffix is optional though (2026-08-16, per Shruti bug
    report — the name was being suppressed whenever age couldn't be
    resolved, even though the name alone was perfectly valid to show)."""
    first_name = (req.child_names or "").split(",")[0].strip()
    if not first_name:
        return None
    first_age_str = (req.child_ages or "").split(",")[0].strip()
    first_age: Optional[int] = None
    if first_age_str:
        try:
            first_age = int(first_age_str)
        except ValueError:
            first_age = None
    if first_age is not None:
        return f"{first_name.upper()}'s {_ordinal(first_age)} Birthday Party"
    return f"{first_name.upper()}'s Birthday Party"


def _booking_subject_line(lead_id: int, req: "LeadSubmitRequest") -> str:
    """Internal team subject line for a CONFIRMED booking. Pipe-delimited
    format requested by Shruti (2026-08-16, superseding the 2026-08-12
    dash-delimited version): "Order #85 | Shruti | 9742240477 | 3 Oct 2026 |
    Vikhroli | 20 Kids". Degrades to '—' for any missing piece rather than
    dropping the whole subject."""
    parent_bit = req.parent_name or "—"
    phone_bit = _phone_local(req.phone)
    date_bit = _fmt_date_short(req.event_date)
    location_bit = _clean_location(req.city or req.venue)
    kids_bit = f"{req.kids_count} Kids" if req.kids_count else "—"
    return f"Order #{lead_id} | {parent_bit} | {phone_bit} | {date_bit} | {location_bit} | {kids_bit}"

def _lead_subject_line(lead_id: int, req: "LeadSubmitRequest") -> str:
    """Internal team subject line for a new (unconfirmed) LEAD/enquiry —
    same pipe-delimited shape as _booking_subject_line() but "Lead #" in
    place of "Order #" (2026-08-16, per Shruti): "Lead #1 | Shruti |
    9742240477 | 3 Oct 2026 | Vikhroli | 20 Kids"."""
    parent_bit = req.parent_name or "—"
    phone_bit = _phone_local(req.phone)
    date_bit = _fmt_date_short(req.event_date)
    location_bit = _clean_location(req.city or req.venue)
    kids_bit = f"{req.kids_count} Kids" if req.kids_count else "—"
    return f"Lead #{lead_id} | {parent_bit} | {phone_bit} | {date_bit} | {location_bit} | {kids_bit}"


def _ics_escape(text: Optional[str]) -> str:
    """Escapes text for use inside an .ics field (RFC 5545 §3.3.11)."""
    return (text or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _build_ics_bytes(req: "LeadSubmitRequest", lead_id: int) -> Optional[bytes]:
    """Builds a minimal .ics calendar invite for the event, attached to both
    the customer confirmation email and the team notification email
    (2026-08-14, per Shruti — the confirmation page/email have always
    promised "Calendar invite sent to your email & Wondershop team — your
    date is blocked!" but nothing ever actually generated or sent one).
    Returns None if there's no event date to build an invite around.
    Party duration defaults to 4 hours from the given/default start time —
    there's no separate "end time" field collected anywhere upstream.
    Times are converted from IST (a fixed UTC+5:30 offset, no DST) to UTC
    so the invite displays correctly in whatever timezone the recipient's
    calendar app is set to."""
    if not req.event_date:
        return None
    try:
        hh, mm = (int(x) for x in (req.event_time or "11:00").split(":")[:2])
    except Exception:
        hh, mm = 11, 0
    start_ist = datetime.combine(req.event_date, dt_time(hour=hh, minute=mm))
    ist_offset = timedelta(hours=5, minutes=30)
    start_utc = start_ist - ist_offset
    end_utc = start_utc + timedelta(hours=4)

    def _fmt(d: datetime) -> str:
        return d.strftime("%Y%m%dT%H%M%SZ")

    summary = _party_title(req) or (f"{req.parent_name}'s Wondershop Booking" if req.parent_name else "Wondershop Birthday Party")
    location = req.venue_maps_link or req.venue or req.city or ""
    description = (f"Wondershop Experiences booking — Order #{lead_id}. "
                   f"Questions? +91 90044 35362 / contact@wondershopexperiences.com")
    uid = f"wondershop-lead-{lead_id}@wondershopexperiences.com"
    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wondershop Experiences//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART:{_fmt(start_utc)}",
        f"DTEND:{_fmt(end_utc)}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"LOCATION:{_ics_escape(location)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    return ics.encode("utf-8")


# ─── GMAIL API EMAIL HELPER ──────────────────────────────────────────────────

async def _get_gmail_access_token() -> str:
    """Exchange refresh token for a short-lived access token."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "refresh_token": settings.GMAIL_REFRESH_TOKEN,
                "grant_type":    "refresh_token",
            },
        )
    r.raise_for_status()
    return r.json()["access_token"]

async def _gmail_send(to_email: str, subject: str, body: str, html_body: Optional[str] = None,
                       attachments: Optional[list] = None) -> None:
    """Send email via Gmail API (HTTPS — no SMTP port issues).
    Sends a plain-text + HTML multipart/alternative message when html_body
    is given, so clients that render HTML get the formatted version and
    everything else still gets a readable plain-text fallback.
    `attachments` is an optional list of (filename, bytes, mime_maintype,
    mime_subtype) tuples — e.g. the order form Excel/PDF."""
    import base64
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = f"Wondershop Experiences <{settings.EMAIL_FROM}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for filename, file_bytes, maintype, subtype in (attachments or []):
        msg.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=filename)
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    token = await _get_gmail_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": encoded},
        )
    if r.status_code not in (200, 201):
        raise Exception(f"Gmail API error {r.status_code}: {r.text}")


# ─── REWARD CODE ISSUE / REDEMPTION ──────────────────────────────────────────
# Only "discount" rewards (10% off next booking) get an actual redeemable
# code — the other reward types (tattoo/bubble/refund) are honoured manually
# by the Party Experience Lead against the booking itself, no code needed.

def _generate_reward_code() -> str:
    # No 0/O/1/I/L — avoids characters that are easy to misread.
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "WS" + "".join(random.choices(chars, k=6))

async def _issue_reward_code(lead_id: int, phone: str, expiry: Optional[date]) -> Optional[str]:
    for _ in range(5):
        code = _generate_reward_code()
        try:
            await database.execute(
                """
                INSERT INTO reward_codes (code, phone, discount_pct, min_spend, issued_lead_id, expiry_date)
                VALUES (:code, :phone, 10, 15000, :lead_id, :expiry)
                """,
                values={"code": code, "phone": phone, "lead_id": lead_id, "expiry": expiry},
            )
            return code
        except Exception:
            continue  # extremely rare collision — try again with a fresh code
    logger.error(f"Lead #{lead_id}: could not issue a unique reward code after 5 attempts")
    return None

async def _redeem_coupon_code(code: str, phone: str, lead_id: int) -> bool:
    """Marks a reward code as redeemed. Only succeeds if it exists, is
    unused, isn't expired, and the phone number matches the one it was
    issued to (this is the enforcement of the 'same mobile number' rule)."""
    row = await database.fetch_one(
        "SELECT * FROM reward_codes WHERE code = :code", values={"code": code},
    )
    if not row:
        logger.warning(f"Lead #{lead_id}: coupon redemption failed — code {code} not found")
        return False
    if row["redeemed"]:
        logger.warning(f"Lead #{lead_id}: coupon redemption failed — code {code} already redeemed")
        return False
    if row["phone"] != phone:
        logger.warning(f"Lead #{lead_id}: coupon redemption failed — code {code} phone mismatch")
        return False
    if row["expiry_date"] and row["expiry_date"] < date.today():
        logger.warning(f"Lead #{lead_id}: coupon redemption failed — code {code} expired")
        return False
    await database.execute(
        "UPDATE reward_codes SET redeemed = TRUE, redeemed_lead_id = :lead_id, redeemed_at = NOW() WHERE code = :code",
        values={"lead_id": lead_id, "code": code},
    )
    logger.info(f"Lead #{lead_id}: coupon {code} redeemed successfully")
    return True


@router.post("/validate-coupon")
async def validate_coupon(req: CouponValidateRequest):
    """Live-validated Apply button check. Tries a scratch-card reward code
    (WS-prefixed) first, then a Refer & Earn referral code. Static promo
    codes (WONDER10 etc.) are still validated client-side only — this
    endpoint is only hit for codes not in that hardcoded list."""
    code = req.code.strip().upper()
    phone = req.phone.strip()

    row = await database.fetch_one("SELECT * FROM reward_codes WHERE code = :code", values={"code": code})
    if row:
        if row["redeemed"]:
            return {"valid": False, "message": "This code has already been used."}
        if row["phone"] != phone:
            return {"valid": False, "message": "This code can only be used with the mobile number it was issued to."}
        if row["expiry_date"] and row["expiry_date"] < date.today():
            return {"valid": False, "message": "This code has expired."}
        pct = float(row["discount_pct"])
        min_spend = float(row["min_spend"] or 0)
        return {
            "valid": True,
            "discount_pct": pct,
            "min_spend": min_spend,
            "message": f"🎉 {code} applied — {pct:.0f}% off! (min. spend {_fmt_rupees(min_spend)})",
        }

    referral_result = await _check_referral_code(code, phone)
    if referral_result["valid"]:
        return referral_result

    return await _check_sales_lead_code(code)


# ─── SALES LEAD ATTRIBUTION CODES ──────────────────────────────────────────────
# Personal codes given to each team member to share with prospects — entered
# in the same "Coupon / Referral Code" box. Give the customer NO discount;
# they only attribute the booking to that person for the order form's
# "Event Sales Lead" field (2026-08-12, per Shruti).

async def _check_sales_lead_code(code: str) -> dict:
    row = await database.fetch_one(
        "SELECT lead_name FROM sales_lead_codes WHERE code = :code AND active = TRUE",
        values={"code": code},
    )
    if not row:
        return {"valid": False, "message": "Invalid code."}
    return {
        "valid": True,
        "is_sales_lead": True,
        "discount_pct": 0,
        "message": f"Code applied — {row['lead_name']} will be your Party Experience Lead!",
    }

async def _resolve_sales_lead_name(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    row = await database.fetch_one(
        "SELECT lead_name FROM sales_lead_codes WHERE code = :code AND active = TRUE",
        values={"code": code.strip().upper()},
    )
    return row["lead_name"] if row else None


# ─── REFER & EARN ─────────────────────────────────────────────────────────────
# Every confirmed booking gets a personal, easy-to-remember referral code
# (first name + last 4 digits of their mobile — reused across every booking
# they make). Friends apply it at checkout for 10% off (min spend ₹15,000),
# same as the scratch-card discount. Rules (2026-08-11, per Shruti):
#   - A code can be used by many different friends (not single-use overall).
#   - Each phone number can redeem a referral code only once, ever.
#   - You cannot redeem your own code.
#   - The referrer earns ₹500 credit (applied manually by the Party
#     Experience Lead against their next booking) every time their code is
#     successfully used — tracked in referral_redemptions for ops to action.

REFERRAL_REWARD_AMOUNT = 500

def _generate_referral_base(name: str, phone: str) -> str:
    first = re.sub(r"[^A-Za-z]", "", (name or "FRIEND").split()[0] if name else "FRIEND").upper()[:10] or "FRIEND"
    digits = re.sub(r"\D", "", phone or "")
    suffix = digits[-4:] if len(digits) >= 4 else digits.zfill(4)
    return first + suffix

async def _get_or_create_referral_code(lead_id: int, name: str, phone: str) -> Optional[str]:
    existing = await database.fetch_one(
        "SELECT code FROM referral_codes WHERE owner_phone = :phone ORDER BY created_at LIMIT 1",
        values={"phone": phone},
    )
    if existing:
        return existing["code"]
    base = _generate_referral_base(name, phone)
    code = base
    for n in range(2, 8):
        try:
            await database.execute(
                "INSERT INTO referral_codes (code, owner_lead_id, owner_name, owner_phone) VALUES (:code, :lead_id, :name, :phone)",
                values={"code": code, "lead_id": lead_id, "name": name, "phone": phone},
            )
            return code
        except Exception:
            code = f"{base}{n}"  # collision (two people with the same first name + last-4) — retry with a suffix
    logger.error(f"Lead #{lead_id}: could not issue a unique referral code after several attempts")
    return None

async def _check_referral_code(code: str, phone: str) -> dict:
    row = await database.fetch_one("SELECT * FROM referral_codes WHERE code = :code", values={"code": code})
    if not row:
        return {"valid": False, "message": "Invalid code."}
    if row["owner_phone"] == phone:
        return {"valid": False, "message": "You can't use your own referral code."}
    already = await database.fetch_one(
        "SELECT 1 FROM referral_redemptions WHERE redeemed_by_phone = :phone", values={"phone": phone},
    )
    if already:
        return {"valid": False, "message": "You've already used a referral code before — this offer is for first-time referrals only."}
    return {
        "valid": True,
        "discount_pct": 10,
        "min_spend": 15000,
        "message": f"🎉 {code} applied — 10% off! (min. spend {_fmt_rupees(15000)})",
    }

async def _redeem_referral_code(code: str, phone: str, lead_id: int) -> bool:
    """Marks a referral code as used by this phone number and credits the
    referrer's reward. Enforces: not self-referral, not already used by
    this phone before. Never blocks the booking on failure."""
    row = await database.fetch_one("SELECT * FROM referral_codes WHERE code = :code", values={"code": code})
    if not row:
        return False
    if row["owner_phone"] == phone:
        logger.warning(f"Lead #{lead_id}: referral redemption blocked — self-referral attempt on {code}")
        return False
    already = await database.fetch_one(
        "SELECT 1 FROM referral_redemptions WHERE redeemed_by_phone = :phone", values={"phone": phone},
    )
    if already:
        logger.warning(f"Lead #{lead_id}: referral redemption blocked — {phone} already used a referral code")
        return False
    await database.execute(
        """
        INSERT INTO referral_redemptions (code, redeemed_by_phone, redeemed_lead_id, referrer_reward_amount)
        VALUES (:code, :phone, :lead_id, :amount)
        """,
        values={"code": code, "phone": phone, "lead_id": lead_id, "amount": REFERRAL_REWARD_AMOUNT},
    )
    logger.info(f"Lead #{lead_id}: referral code {code} redeemed — referrer earns Rs.{REFERRAL_REWARD_AMOUNT}")
    # Best-effort nudge to the referrer that they earned a reward.
    try:
        owner = await database.fetch_one(
            "SELECT parent_name, email FROM leads WHERE lead_id = :lid", values={"lid": row["owner_lead_id"]},
        )
        if owner and owner["email"] and "@" in owner["email"] and settings.GMAIL_CLIENT_ID:
            first = _cap_first(owner["parent_name"].split()[0] if owner["parent_name"] else None)
            body = (
                f"Hi {first}! 🎉\n\nGreat news — someone just booked with Wondershop using your referral code "
                f"{code}. You've earned Rs.{REFERRAL_REWARD_AMOUNT} credit, which your Party Experience Lead "
                f"will apply against your next Wondershop booking.\n\n"
                f"Keep sharing your code with friends — there's no limit to how many times you can earn!\n\n"
                f"Warmly,\nTeam Wondershop 🎈"
            )
            await _gmail_send(to_email=owner["email"], subject=f"You just earned Rs.{REFERRAL_REWARD_AMOUNT}! 🎉", body=body)
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: referral-earned notification failed — {exc}")
    return True

async def _redeem_any_code(code: str, phone: str, lead_id: int) -> None:
    """Tries the code against reward_codes first, then referral_codes.
    Best-effort — a failed/invalid code never blocks the booking, since the
    price was already computed client-side at Apply time."""
    if await _redeem_coupon_code(code, phone, lead_id):
        return
    await _redeem_referral_code(code, phone, lead_id)


# ─── ORDER SUMMARY / REWARD / DETAIL BLOCKS (plain-text, used as email fallback) ──

def _format_order_summary_block(req: LeadSubmitRequest) -> str:
    """Itemised order summary — acts as the customer's on-email bill."""
    if req.order_grand_total is None and req.client_budget is None:
        return ""
    lines = ["\nYOUR ORDER SUMMARY"]
    if req.order_grand_total is not None:
        lines.append(f"  Grand Total     : {_fmt_rupees(req.order_grand_total)}")
    if req.order_discount_pct:
        lines.append(f"  Discount        : {req.order_discount_pct:.0f}%")
    # 2026-08-24, per Shruti (Image 3c) — total savings (₹, incl. freebie
    # item values) + which freebies were unlocked, same figures shown on the
    # website's bottom bar / checkout Order Summary / Review page.
    if req.order_total_savings:
        lines.append(f"  Total Savings   : {_fmt_rupees(req.order_total_savings)}")
    if req.order_freebies_text:
        lines.append(f"  Free Perks      : {req.order_freebies_text}")
    lines.append(f"  Payable Total   : {_fmt_rupees(req.client_budget)}")
    pay_method_label = _PAYMENT_METHOD_LABELS.get(req.payment_method or "", req.payment_method)
    if pay_method_label:
        lines.append(f"  Payment Method  : {pay_method_label}")
    # No payment method is auto-verified — never claim an advance was
    # "Paid" here (2026-08-12, per Shruti). Advance/Pending shown to the
    # customer as of 2026-08-14 (per Shruti), both clearly qualified as
    # pending verification.
    cashback_amt = 0.0
    if req.reward_type == "refund" and req.reward_value:
        cashback_amt = req.reward_value
        lines.append(f"  Cashback (Scratch Card) : -{_fmt_rupees(req.reward_value)}")
    if req.order_advance is not None:
        lines.append(f"  Advance Paid (Pending Verification) : {_fmt_rupees(req.order_advance)}")
    if req.order_balance is not None:
        pending = max(0.0, req.order_balance - cashback_amt)
        lines.append(f"  Pending Amount  : {_fmt_rupees(pending)}")
    lines.append(f"  Payment Status  : {_payment_status_text(req)}")
    lines.append("")
    return "\n".join(lines) + "\n"

def _format_dj_addons_block(req: LeadSubmitRequest) -> str:
    lines = []
    if req.dj_lights_addon:
        lines.append("  Music Lights   : Yes (Rs.1,500)")
    if req.dj_smoke_machine_addon:
        lines.append("  Smoke Machine  : Yes (Rs.2,000)")
    if not lines:
        return ""
    return "\nMUSIC ADD-ONS\n" + "\n".join(lines) + "\n"

def _format_venue_block(req: LeadSubmitRequest) -> str:
    if not any([req.venue_maps_link, req.venue_contact_name, req.venue_contact_phone]):
        return ""
    lines = ["\nVENUE DETAILS"]
    if req.venue_maps_link:
        lines.append(f"  Maps Link      : {req.venue_maps_link}")
    if req.venue_contact_name or req.venue_contact_phone:
        contact = " ".join(filter(None, [
            req.venue_contact_name,
            f"({req.venue_contact_phone})" if req.venue_contact_phone else None,
        ]))
        lines.append(f"  Contact Person : {contact}")
    lines.append("")
    return "\n".join(lines) + "\n"

def _format_gift_delivery_block(req: LeadSubmitRequest) -> str:
    # Same gating as the HTML email — the Required By / Address Type inputs
    # carry defaults even with no return gift selected, so check the actual
    # cart snapshot rather than these fields' presence (2026-08-14, per
    # Shruti).
    snap_gifts = (req.builder_snapshot or {}).get("gifts") or []
    if not any(g.get("n") for g in snap_gifts):
        return ""
    lines = ["\nRETURN GIFT DELIVERY DETAILS"]
    if req.gift_delivery_address:
        lines.append(f"  Address        : {req.gift_delivery_address}")
    if req.gift_delivery_address_type:
        lines.append(f"  Address Type   : {req.gift_delivery_address_type}")
    if req.gift_delivery_maps_link:
        lines.append(f"  Maps Link      : {req.gift_delivery_maps_link}")
    if req.gift_delivery_contact or req.gift_delivery_contact_phone:
        contact = " ".join(filter(None, [
            req.gift_delivery_contact,
            f"({req.gift_delivery_contact_phone})" if req.gift_delivery_contact_phone else None,
        ]))
        lines.append(f"  Contact Person : {contact}")
    if req.gift_required_by_date:
        lines.append(f"  Required By    : {req.gift_required_by_date.isoformat()}")
    lines.append("  Note: delivery timing may shift a few days due to weather/logistics.")
    lines.append("")
    return "\n".join(lines) + "\n"

def _format_reward_block(req: LeadSubmitRequest, reward_code: Optional[str], added_service_label: Optional[str] = None) -> str:
    """Scratch-card reward + full terms & conditions — only present if won.
    added_service_label is set when the customer chose, right from the
    scratch-card reveal, to add a won Tattoo/Bubble Artist reward onto THIS
    booking — combined into this same block rather than a separate email."""
    if not req.reward_type:
        return ""
    lines = ["\nYOUR REWARD 🎁", f"  {req.reward_label or req.reward_type}"]
    if added_service_label:
        lines.append(f"  ✅ Added to THIS booking, no extra charge — your Party Experience Lead will confirm the details.")
    if req.reward_value:
        lines.append(f"  Value: Rs.{req.reward_value:,.0f}")
    if reward_code:
        lines.append(f"  Your Code: {reward_code}")
        lines.append(f"  Redeemable only on a future booking made from mobile number {req.phone}.")
    if req.reward_expiry:
        lines.append(f"  Valid until: {req.reward_expiry.isoformat()}")
    if req.reward_terms:
        lines.append("  Terms & Conditions:")
        for clause in req.reward_terms.split(" | "):
            clause = clause.strip()
            if clause:
                lines.append(f"    • {clause}")
    if not added_service_label:
        lines.append("  Your Party Experience Lead will confirm redemption details with you.")
    lines.append("")
    return "\n".join(lines) + "\n"


# ─── FULL SERVICES SUMMARY (all chosen services, w/ decor + photography
#     inclusions) ────────────────────────────────────────────────────────────
# Built from req.builder_snapshot (captured client-side by buildSnapshot()
# in builder.html) + the catalogue_data resolvers already used for the order
# form, so the customer/team emails and the order form always agree on what
# was actually chosen. A booking made before builder_snapshot existed, or
# via a flow that doesn't populate it, simply shows no services block rather
# than guessing (2026-08-12, per Shruti — "include the complete list of
# chosen services with images; for decor and photography specifically list
# inclusions").

def _music_label(tier: Optional[str]) -> str:
    """Customer-facing Music tier name (2026-08-19, per Shruti: renamed to
    "Music Essential"/"Music Plus"). Mirrors builder.html's musicLabel() —
    the underlying tier value stays the bare internal word ('Classic'/
    'Premium') everywhere else; this is just the display mapping."""
    if tier == "Classic":
        return "Music Essential"
    if tier == "Premium":
        return "Music Plus"
    return f"{tier} Music" if tier else ""


def _services_detail_list(req: LeadSubmitRequest, added_service_label: Optional[str] = None) -> list:
    """Always returns one entry per builder step (Decor, Activities, Host,
    Music, Pinata, E-Invite, Photographer, Return Gifts), in that order, even
    when the customer didn't opt into a given step — those come back as
    {"label": ..., "not_selected": True} so the confirmation email shows an
    explicit "Not selected" row instead of silently dropping the category
    (2026-08-12, per Shruti — team couldn't tell what was and wasn't chosen
    from the email alone). Only skipped entirely when there's no builder
    snapshot at all (a plain enquiry/callback lead that never went through
    the package builder) — nothing was "not selected" there, there's simply
    no order to itemise."""
    snap = req.builder_snapshot or {}
    if not snap:
        return []
    out = []

    decor = snap.get("decor") or {}
    if decor.get("n"):
        decor_ref = cat.resolve_decor(decor.get("id"), decor.get("p"))
        out.append({
            "label": "Decor", "name": decor.get("n"), "price": decor.get("p"),
            "image_path": decor_ref["image_path"] if decor_ref else None,
            "inclusions": [(l, v) for l, v, na in (decor_ref["spec"] if decor_ref else []) if not na],
        })
    else:
        out.append({"label": "Decor", "not_selected": True})

    activities = snap.get("activities") or []
    acts_named = [a for a in activities if a.get("n")]
    if acts_named:
        out.append({
            "label": "Activities",
            "items": [{"name": a["n"], "price": a.get("p")} for a in acts_named],
        })
    else:
        out.append({"label": "Activities", "not_selected": True})

    host = snap.get("host") or {}
    if host.get("tier"):
        out.append({"label": "Host", "name": f"{host['tier']} Host", "price": host.get("p")})
    else:
        out.append({"label": "Host", "not_selected": True})

    dj = snap.get("dj") or {}
    if dj.get("tier"):
        addons = snap.get("dj_addons") or {}
        addon_bits = []
        if addons.get("lights"):
            addon_bits.append("Music Lights")
        if addons.get("smoke"):
            addon_bits.append("Smoke Machine")
        out.append({
            "label": "Music", "name": _music_label(dj['tier']), "price": dj.get("p"),
            "inclusions": [("Add-ons", ", ".join(addon_bits))] if addon_bits else [],
        })
    else:
        out.append({"label": "Music", "not_selected": True})

    pinata = snap.get("pinata") or {}
    if pinata.get("n"):
        out.append({
            "label": "Pinata", "name": pinata.get("n"), "price": pinata.get("p"),
            "image_path": cat.resolve_pinata_image(pinata.get("id")),
        })
    else:
        out.append({"label": "Pinata", "not_selected": True})

    einvite = snap.get("einvite") or {}
    if einvite.get("n"):
        out.append({
            "label": "E-Invite", "name": einvite.get("n"),
            "image_path": cat.resolve_einvite_image(einvite.get("id")),
        })
    else:
        out.append({"label": "E-Invite", "not_selected": True})

    photo = snap.get("photo") or {}
    if photo.get("tier"):
        out.append({
            "label": "Photographer", "name": f"{photo['tier']} Photography", "price": photo.get("p"),
            "inclusions": [(f, "") for f in cat.PHOTO_TIER_FEATURES.get(photo["tier"], [])],
        })
    else:
        out.append({"label": "Photographer", "not_selected": True})

    gifts = snap.get("gifts") or []
    gifts_named = [g for g in gifts if g.get("n")]
    if gifts_named:
        packaging = cat.PACKAGING_LABELS.get(snap.get("gift_packaging"), None)
        # 2026-08-18, per Shruti — "thankyou tags are not getting added":
        # buildSnapshot() in builder.html has always sent gift_thank_you_note
        # (true when the customer picked the ₹10/item Thank You Note add-on
        # on the Return Gifts step), but nothing on the backend ever read it
        # back out — it landed in builder_snapshot and was never surfaced in
        # the team email or Google Sheet, so the team never saw it even
        # though the customer paid for it and it was included in their total.
        thank_you_note = bool(snap.get("gift_thank_you_note"))
        note_parts = []
        if packaging:
            note_parts.append(f"Packaging: {packaging}")
        if thank_you_note:
            note_parts.append("Thank You Note requested")
        gift_items = []
        for g in gifts_named:
            ref = cat.resolve_gift(g.get("id"))
            unit = g.get("unit")
            if unit is None and ref:
                unit = ref["catalogue_unit"]
            qty = g.get("qty") or 0
            gift_items.append({
                "name": g["n"], "qty": qty, "unit": unit,
                "total": (unit * qty) if (unit is not None and qty) else None,
                "image_path": ref["image_path"] if ref else None,
            })
        out.append({
            "label": "Return Gifts", "items": gift_items,
            "note": " · ".join(note_parts) if note_parts else None,
        })
    else:
        out.append({"label": "Return Gifts", "not_selected": True})

    # 2026-08-14, per Shruti: if the customer won a Tattoo/Bubble Artist
    # scratch-card reward and chose to add it to THIS booking, show it as
    # its own line in Services Booked (not just buried in the reward
    # callout further down the email) — "free" price so it's obviously a
    # complimentary win, not a paid add-on.
    if added_service_label:
        out.append({"label": "Bonus Service", "name": added_service_label, "price": None, "free": True})

    return out


def _format_services_block(req: LeadSubmitRequest, added_service_label: Optional[str] = None) -> str:
    """Plain-text itemised list of every chosen service — decor & photography
    show their inclusions so there's no ambiguity later about what was
    promised. added_service_label appends a won Tattoo/Bubble Artist reward
    (if redeemed onto this booking) as its own "Bonus Service" line."""
    services = _services_detail_list(req, added_service_label)
    if not services:
        return ""
    lines = ["\nSERVICES BOOKED"]
    for svc in services:
        if svc.get("not_selected"):
            lines.append(f"  {svc['label']}: Not selected")
            continue
        if svc.get("items"):
            lines.append(f"  {svc['label']}:")
            for it in svc["items"]:
                if "qty" in it:
                    price_bit = f" — {_fmt_rupees(it['total'])} ({it['qty']} x {_fmt_rupees(it['unit'])})" if it.get("total") is not None else ""
                else:
                    price_bit = f" — {_fmt_rupees(it['price'])}" if it.get("price") else ""
                lines.append(f"    • {it['name']}{price_bit}")
            if svc.get("note"):
                lines.append(f"    ({svc['note']})")
            continue
        price_bit = " — FREE 🎁 (scratch-card reward)" if svc.get("free") else (f" — {_fmt_rupees(svc['price'])}" if svc.get("price") else "")
        lines.append(f"  {svc['label']}: {svc['name']}{price_bit}")
        for label, val in svc.get("inclusions", []):
            lines.append(f"      - {label}{': ' + val if val else ''}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _html_services_section(req: LeadSubmitRequest, added_service_label: Optional[str] = None) -> str:
    """HTML version of _format_services_block, with reference images pulled
    from the live site (hotlinked, not attached, per the file's existing
    image-hosting convention) for decor/pinata/e-invite/gifts.
    added_service_label appends a won Tattoo/Bubble Artist reward (if
    redeemed onto this booking) as its own "Bonus Service" card."""
    services = _services_detail_list(req, added_service_label)
    if not services:
        return ""
    cards = []
    for svc in services:
        if svc.get("not_selected"):
            cards.append(
                f'<div style="padding:12px 0;border-bottom:1px solid #F0E9FA">'
                f'<div style="font-size:14px;font-weight:700;color:{BRAND_PURPLE}">{_html_escape(svc["label"])}</div>'
                f'<div style="font-size:13.5px;color:#9CA3AF">Not selected</div>'
                f'</div>'
            )
            continue
        img_html = ""
        img_path = svc.get("image_path")
        if img_path:
            # image_path is already relative to SITE_BASE_URL (resolvers in
            # catalogue_data.py include their own "img/" prefix where
            # needed; e-invite paths point at the root-level einvites/
            # folder instead) — do NOT prepend "/img/" here (2026-08-14,
            # per Shruti, fixes e-invite thumbnails 404ing in emails).
            img_url = f"{SITE_BASE_URL}/{urllib.parse.quote(img_path)}"
            img_html = (
                f'<img src="{img_url}" width="72" height="72" alt="{_html_escape(svc["label"])}" '
                f'style="width:72px;height:72px;object-fit:cover;border-radius:8px;flex-shrink:0;margin-right:12px">'
            )
        if svc.get("items"):
            item_lines = []
            for it in svc["items"]:
                it_img = ""
                if it.get("image_path"):
                    it_url = f"{SITE_BASE_URL}/{urllib.parse.quote(it['image_path'])}"  # see note above — no "/img/" prefix
                    it_img = f'<img src="{it_url}" width="40" height="40" alt="" style="width:40px;height:40px;object-fit:cover;border-radius:6px;margin-right:8px;vertical-align:middle">'
                if "qty" in it:
                    price_bit = f" — {_html_escape(_fmt_rupees(it['total']))} ({it['qty']} × {_html_escape(_fmt_rupees(it['unit']))})" if it.get("total") is not None else ""
                else:
                    price_bit = f" — {_html_escape(_fmt_rupees(it['price']))}" if it.get("price") else ""
                item_lines.append(
                    f'<div style="display:flex;align-items:center;padding:5px 0;font-size:13px;color:#2D2140">'
                    f'{it_img}<span>{_html_escape(it["name"])}{price_bit}</span></div>'
                )
            note_html = f'<div style="font-size:12px;color:#8B7FA0;margin-top:4px">{_html_escape(svc["note"])}</div>' if svc.get("note") else ""
            body = (
                f'<div style="font-size:14px;font-weight:700;color:{BRAND_PURPLE};margin-bottom:4px">{_html_escape(svc["label"])}</div>'
                f'{"".join(item_lines)}{note_html}'
            )
            cards.append(f'<div style="padding:12px 0;border-bottom:1px solid #F0E9FA">{body}</div>')
            continue
        price_bit = ' — <span style="color:#2E9E52;font-weight:700">FREE 🎁 (scratch-card reward)</span>' if svc.get("free") else (f" — {_html_escape(_fmt_rupees(svc['price']))}" if svc.get("price") else "")
        incl_html = ""
        incl = svc.get("inclusions") or []
        if incl:
            incl_items = "".join(
                f'<li style="margin-bottom:2px">{_html_escape(label)}{": " + _html_escape(val) if val else ""}</li>'
                for label, val in incl
            )
            incl_html = f'<ul style="margin:6px 0 0;padding-left:16px;font-size:12px;color:#5B5169;line-height:1.5">{incl_items}</ul>'
        text_html = (
            f'<div style="font-size:14px;font-weight:700;color:{BRAND_PURPLE}">{_html_escape(svc["label"])}</div>'
            f'<div style="font-size:13.5px;color:#2D2140">{_html_escape(svc["name"])}{price_bit}</div>'
            f'{incl_html}'
        )
        cards.append(
            f'<div style="display:flex;align-items:flex-start;padding:12px 0;border-bottom:1px solid #F0E9FA">'
            f'{img_html}<div style="flex:1">{text_html}</div></div>'
        )
    return (
        _html_section_title("Services Booked")
        + f'<div style="background:#fff;border:1px solid #F0E9FA;border-radius:10px;padding:4px 14px;margin:14px 0">'
        + "".join(cards) + '</div>'
    )


# ─── HTML EMAIL TEMPLATE ─────────────────────────────────────────────────────
# Table-based layout with inline styles throughout (required for consistent
# rendering across Gmail/Outlook/Apple Mail). Images are hosted on the live
# site rather than attached, so the email stays small and simple.

def _html_details_table(rows) -> str:
    """rows: list of (label, value) tuples. Skips rows with an empty value."""
    trs = []
    for label, value in rows:
        if not value:
            continue
        trs.append(
            f'<tr>'
            f'<td style="padding:8px 14px;border-bottom:1px solid #F0E9FA;color:#8B7FA0;'
            f'font-size:13px;font-weight:600;white-space:nowrap;vertical-align:top">{_html_escape(label)}</td>'
            f'<td style="padding:8px 14px;border-bottom:1px solid #F0E9FA;color:#2D2140;font-size:13.5px">{_html_escape(value)}</td>'
            f'</tr>'
        )
    if not trs:
        return ""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;'
        f'border:1px solid #F0E9FA;margin:14px 0">{"".join(trs)}</table>'
    )

def _html_section_title(text: str) -> str:
    return (
        f'<div style="font-size:13px;font-weight:700;letter-spacing:.4px;color:{BRAND_PURPLE};'
        f'text-transform:uppercase;margin:22px 0 8px">{_html_escape(text)}</div>'
    )

def _html_reward_card(req: LeadSubmitRequest, reward_code: Optional[str], added_service_label: Optional[str] = None) -> str:
    if not req.reward_type:
        return ""
    parts = [
        f'<div style="font-family:Georgia,serif;font-size:17px;font-weight:700;margin-bottom:4px">'
        f'🎁 {_html_escape(req.reward_label or req.reward_type)}</div>'
    ]
    if added_service_label:
        parts.append(
            f'<div style="margin:6px 0 10px;padding:8px 12px;background:rgba(255,255,255,.18);'
            f'border-radius:8px;font-size:12.5px;font-weight:700">✅ Added to THIS booking, no extra charge</div>'
        )
    if req.reward_value:
        parts.append(f'<div style="font-size:13.5px;opacity:.95;margin-bottom:8px">Value: Rs.{req.reward_value:,.0f}</div>')
    if reward_code:
        parts.append(
            f'<div style="margin:10px 0;padding:10px 16px;background:rgba(255,255,255,.18);'
            f'border:1.5px dashed rgba(255,255,255,.65);border-radius:8px;display:inline-block;'
            f'font-family:monospace;font-size:19px;font-weight:700;letter-spacing:2px">{_html_escape(reward_code)}</div>'
            f'<div style="font-size:12px;opacity:.9;margin-bottom:4px">Valid only when your next booking is made from mobile number {_html_escape(req.phone)}.</div>'
        )
    if req.reward_expiry:
        parts.append(f'<div style="font-size:12px;opacity:.9">Valid until {_html_escape(_fmt_date_long(req.reward_expiry))}</div>')
    if req.reward_terms:
        clauses = "".join(f'<li style="margin-bottom:4px">{_html_escape(c.strip())}</li>' for c in req.reward_terms.split(" | ") if c.strip())
        parts.append(f'<ul style="margin:10px 0 0;padding-left:18px;font-size:11.5px;line-height:1.6;opacity:.9">{clauses}</ul>')
    body = "".join(parts)
    return (
        f'<div style="margin:18px 0;padding:18px 20px;border-radius:12px;color:#fff;'
        f'background:linear-gradient(135deg,{BRAND_PINK} 0%,{BRAND_PURPLE} 100%)">{body}</div>'
    )

def _html_referral_card(req: LeadSubmitRequest, referral_code: Optional[str]) -> str:
    if not referral_code:
        return ""
    return (
        f'<div style="margin:18px 0;padding:18px 20px;border-radius:12px;color:#fff;'
        f'background:linear-gradient(135deg,#52C470 0%,#2E9E52 100%)">'
        f'<div style="font-family:Georgia,serif;font-size:17px;font-weight:700;margin-bottom:4px">🎁 Refer &amp; Earn</div>'
        f'<div style="font-size:13.5px;line-height:1.6;opacity:.95;margin-bottom:10px">'
        f'Share your code with friends — they get 10% off their booking (min. spend ₹15,000), '
        f'and you earn ₹{REFERRAL_REWARD_AMOUNT} credit towards your next Wondershop booking, every single time it\'s used.</div>'
        f'<div style="padding:10px 16px;background:rgba(255,255,255,.18);border:1.5px dashed rgba(255,255,255,.65);'
        f'border-radius:8px;display:inline-block;font-family:monospace;font-size:19px;font-weight:700;letter-spacing:2px">'
        f'{_html_escape(referral_code)}</div>'
        f'</div>'
    )

def _build_html_email(*, is_booking: bool, lead_id: int, req: LeadSubmitRequest,
                       reward_code: Optional[str], referral_code: Optional[str] = None,
                       recipient_kind: str, event_sales_lead: Optional[str] = None,
                       added_service_label: Optional[str] = None) -> str:
    """recipient_kind: 'customer' or 'team' — team version skips the welcome
    fluff and T&C footer link but keeps the same details table + styling."""
    first_name = _cap_first(req.parent_name.split()[0] if req.parent_name else None)
    party_title = _party_title(req)
    # 2026-08-14, per Shruti: merge the party title directly into the main
    # heading for the customer's booking-confirmation email — "Booking
    # Confirmed for IDHIKA's 5th Birthday! 🎉" — instead of a separate small
    # line above it (mirrors the same merge on the order confirmation page).
    # party_title is "...'s Nth Birthday Party"; drop the trailing "Party"
    # since it reads better folded into "Booking Confirmed for ... !".
    party_phrase = party_title[:-len(" Party")] if party_title and party_title.endswith(" Party") else party_title
    merge_party_into_heading = False

    if recipient_kind == "customer":
        if is_booking:
            if party_phrase:
                heading = f"Booking Confirmed for {_html_escape(party_phrase)}! 🎉"
                merge_party_into_heading = True
            else:
                heading = "Thank You For Your Booking! 🎉"
            intro = (
                f"Hi {_html_escape(first_name)}, thank you for your query — we've received your booking. Our team will "
                f"check the payment details and confirm your booking shortly. Your Party Experience Lead will be in "
                f"touch soon to walk through every detail."
            )
        else:
            heading = f"We Got Your Enquiry, {_html_escape(first_name)}! 🎈"
            intro = (
                "Thank you for reaching out to Wondershop Experiences. Our team will call you within a few hours "
                "to help plan your child's perfect birthday."
            )
    else:
        heading = ("New Booking Request — Payment Pending Verification 🎉" if is_booking else "New Lead Received")
        intro = f"Reference #{lead_id} — {'a booking request has come in and needs payment verification before it is confirmed' if is_booking else 'a new enquiry has come in'} on the website."

    detail_rows = [
        ("Parent Name", req.parent_name),
        ("Mobile", req.phone),
        ("Email", req.email),
        ("Child(ren)", req.child_names),
        ("Turning Age", req.child_ages),  # age being celebrated, not calendar age as of event date — see builder.html's ageForEvent()
        ("Event Date", _fmt_date_long(req.event_date) if req.event_date else None),
        ("Kids Count", req.kids_count),
        ("Theme", req.theme),
        ("Interests", req.interests),
        ("Other Interest", req.interest_other),
        ("Venue", req.venue),
        ("City / Pincode", " / ".join(filter(None, [req.city, req.pincode])) or None),
    ]
    details_html = _html_details_table(detail_rows)

    order_rows = []
    if req.order_grand_total is not None:
        order_rows.append(("Grand Total", _fmt_rupees(req.order_grand_total)))
    if req.order_discount_pct:
        order_rows.append(("Discount", f"{req.order_discount_pct:.0f}%"))
    # 2026-08-24, per Shruti (Image 3c) — same total-savings/freebie figures
    # as the website (see order_total_savings/order_freebies_text docstring
    # on LeadSubmitRequest above), shown to both customer and team.
    if req.order_total_savings:
        order_rows.append(("🎉 Total Savings", _fmt_rupees(req.order_total_savings)))
    if req.order_freebies_text:
        order_rows.append(("🎁 Free Perks Unlocked", req.order_freebies_text))
    if req.client_budget is not None:
        order_rows.append(("Payable Total", _fmt_rupees(req.client_budget)))
    pay_method_label = _PAYMENT_METHOD_LABELS.get(req.payment_method or "", req.payment_method)
    if pay_method_label:
        order_rows.append(("Payment Method", pay_method_label))
    # Scratch-card "refund" reward (a cashback amount knocked off the
    # balance due) — shown before Advance/Pending below so those figures
    # already reflect it (2026-08-14, per Shruti — the Rs.180 refund shown
    # on the Booking Confirmed screen wasn't reflected in the confirmation
    # email).
    cashback_amt = 0.0
    if req.reward_type == "refund" and req.reward_value:
        cashback_amt = req.reward_value
        order_rows.append(("🎁 Cashback (Scratch Card)", f"-{_fmt_rupees(req.reward_value)}"))
    # We don't auto-verify any payment method — nothing is ever shown as
    # "Paid" here, just what the customer self-reported at checkout, clearly
    # qualified as pending verification either way. Shown to BOTH customer
    # and team as of 2026-08-14 (per Shruti — "order summary: mention total,
    # advance paid (to be verified based on the payment method), discount,
    # cashbacks if any and pending amount"); previously the advance/balance
    # figures were team-only.
    verify_note = (
        "(Pledged, Pending Verification)" if recipient_kind == "team"
        else "(Pending Verification — based on your payment method)"
    )
    if req.order_advance is not None:
        order_rows.append((f"Advance Paid {verify_note}", _fmt_rupees(req.order_advance)))
    if req.order_balance is not None:
        pending = max(0.0, req.order_balance - cashback_amt)
        order_rows.append(("Pending Amount", _fmt_rupees(pending)))
    order_rows.append(("Payment Status", _payment_status_text(req)))
    if recipient_kind == "team":
        if req.redeemed_coupon_code:
            order_rows.append(("Coupon Redeemed", req.redeemed_coupon_code))
        if event_sales_lead:
            order_rows.append(("Event Sales Lead", event_sales_lead))
    order_html = _html_details_table(order_rows)

    dj_rows = []
    if req.dj_lights_addon:
        dj_rows.append(("Music Lights", "Yes (Rs.1,500)"))
    if req.dj_smoke_machine_addon:
        dj_rows.append(("Smoke Machine", "Yes (Rs.2,000)"))
    dj_html = _html_details_table(dj_rows)

    venue_rows = [
        ("Maps Link", req.venue_maps_link),
        ("Contact Person", " ".join(filter(None, [req.venue_contact_name, f"({req.venue_contact_phone})" if req.venue_contact_phone else None])) or None),
    ]
    venue_html = _html_details_table(venue_rows)

    # The Required By date / Address Type inputs on the Return Gifts step
    # carry defaults (event date, "Venue") even when NO return gift was
    # actually added to the cart — so gift_rows must be gated on whether any
    # gift was picked, not just on whether those fields happen to be
    # non-empty (2026-08-14, per Shruti — was showing a "Return Gift
    # Delivery" block with a Required By date on bookings with no return
    # gifts at all).
    _snap_gifts = (req.builder_snapshot or {}).get("gifts") or []
    _any_gift_selected = any(g.get("n") for g in _snap_gifts)
    gift_rows = [
        ("Address", req.gift_delivery_address),
        ("Address Type", req.gift_delivery_address_type),
        ("Maps Link", req.gift_delivery_maps_link),
        ("Contact Person", " ".join(filter(None, [req.gift_delivery_contact, f"({req.gift_delivery_contact_phone})" if req.gift_delivery_contact_phone else None])) or None),
        ("Required By", _fmt_date_long(req.gift_required_by_date) if req.gift_required_by_date else None),
    ] if _any_gift_selected else []
    gift_html = _html_details_table(gift_rows)

    services_html = _html_services_section(req, added_service_label)

    remarks_html = ""
    if req.remarks:
        remarks_html = (
            _html_section_title("Special Requests / Remarks")
            + f'<div style="background:#fff;border:1px solid #F0E9FA;border-radius:10px;padding:12px 14px;'
              f'font-size:13.5px;color:#2D2140;white-space:pre-wrap">{_html_escape(req.remarks)}</div>'
        )

    reward_html = _html_reward_card(req, reward_code, added_service_label)
    referral_html = _html_referral_card(req, referral_code) if recipient_kind == "customer" else ""

    tnc_html = ""
    if is_booking:
        tnc_text = (
            "By confirming this booking you agree to our" if recipient_kind == "customer"
            else "Full Terms &amp; Conditions for this booking"
        )
        tnc_html = (
            f'<div style="margin:20px 0;font-size:12.5px;color:#8B7FA0">'
            f'{tnc_text} '
            f'<a href="{TERMS_URL}" style="color:{BRAND_PURPLE};font-weight:700">Terms &amp; Conditions</a>.</div>'
        )

    sections = "".join(filter(None, [
        _html_section_title("Booking Details" if is_booking else "Enquiry Details") + details_html,
        (_html_section_title("Order Summary") + order_html) if order_rows else "",
        services_html,
        (_html_section_title("Music Add-ons") + dj_html) if dj_rows else "",
        (_html_section_title("Venue Details") + venue_html) if any(r[1] for r in venue_rows) else "",
        (_html_section_title("Return Gift Delivery") + gift_html) if any(r[1] for r in gift_rows) else "",
        remarks_html,
        reward_html,
        referral_html,
        tnc_html,
    ]))

    footer = (
        '<div style="margin-top:26px;padding-top:18px;border-top:1px solid #F0E9FA;font-size:12.5px;color:#8B7FA0;text-align:center">'
        'Need anything? We\'re here: <b style="color:#2D2140">+91 90044 35362 · +91 97422 40477</b><br>'
        '<a href="mailto:contact@wondershopexperiences.com" style="color:' + BRAND_PURPLE + '">contact@wondershopexperiences.com</a>'
        '</div>'
    ) if recipient_kind == "customer" else ""

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:{BRAND_LIGHT};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BRAND_LIGHT};padding:28px 12px">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(45,33,64,.08)">
<tr><td style="background:linear-gradient(135deg,{BRAND_PINK} 0%,{BRAND_PURPLE} 100%);padding:28px 26px;text-align:center">
<img src="{MASCOT_URL}" width="56" height="56" alt="Wondershop mascot" style="display:block;margin:0 auto 10px;border-radius:50%;background:#fff;padding:4px">
{f'<div style="font-family:Georgia,serif;font-size:14px;font-weight:600;color:rgba(255,255,255,.85);margin-bottom:4px">{_html_escape(party_title)}</div>' if party_title and not merge_party_into_heading else ''}
<div style="font-family:Georgia,serif;font-size:21px;font-weight:700;color:#fff">{heading}</div>
</td></tr>
<tr><td style="padding:24px 26px 8px">
<div style="font-size:14.5px;line-height:1.6;color:#2D2140">{intro}</div>
{sections}
</td></tr>
<tr><td style="padding:0 26px 26px">{footer}</td></tr>
</table>
<div style="font-size:11px;color:#B3A7C4;margin-top:14px">Wondershop Experiences · Godrej Platinum, Vikhroli East, Mumbai</div>
</td></tr>
</table>
</body></html>"""


# ─── 1. USER ACK EMAIL ───────────────────────────────────────────────────────

async def _send_user_ack(lead_id: int, req: LeadSubmitRequest, reward_code: Optional[str], referral_code: Optional[str] = None,
                          added_service_label: Optional[str] = None, is_upgrade: bool = False) -> None:
    """Confirmation email to the parent who submitted the form. Content and
    subject vary depending on whether this was a confirmed booking or an
    unconfirmed enquiry (2026-08-11, per Shruti). is_upgrade=True is the
    "order upgrade" resend triggered by /redeem-service when the customer
    adds a won Tattoo/Bubble Artist reward to THIS booking from the
    scratch-card reveal — same full content as the original confirmation
    (every block below is unchanged), just a different subject/intro so it
    reads as an update rather than a duplicate booking email (2026-08-12,
    per Shruti: "send an order upgrade email to the customer... should have
    all contents from the earlier mail + additional service")."""
    if not req.email or "@" not in req.email or "." not in req.email.split("@")[-1]:
        return   # skip if no email or obviously invalid (e.g. test placeholder "string")
    if not settings.GMAIL_CLIENT_ID:
        return

    try:
        first_name = _cap_first(req.parent_name.split()[0] if req.parent_name else None)
        is_booking = bool(req.is_booking)

        if is_upgrade:
            subject = f"🎁 Your Booking is Updated, {first_name}! {added_service_label or 'New addon'} added (Order #{lead_id})"
            intro_line = (f"Great news — we've added your {added_service_label or 'complimentary reward'} to this booking at no "
                          f"extra cost. Here's your full, updated booking confirmation:")
        elif is_booking:
            subject = f"🎉 Your Wondershop Booking is Confirmed, {first_name}! (Order #{lead_id})"
            intro_line = "Welcome to the Wondershop family! Your party is officially booked — we can't wait to celebrate with you."
        else:
            subject = f"We got your enquiry, {first_name}! 🎈 (Ref #{lead_id})"
            intro_line = "We've received your enquiry and our team will call you within a few hours to discuss your child's birthday party."

        remarks_block = f"\nYour special requests / remarks:\n  {req.remarks}\n" if req.remarks else ""
        order_block = _format_order_summary_block(req)
        services_block = _format_services_block(req, added_service_label)
        dj_addons_block = _format_dj_addons_block(req)
        venue_block = _format_venue_block(req)
        gift_delivery_block = _format_gift_delivery_block(req)
        reward_block = _format_reward_block(req, reward_code, added_service_label)
        referral_block = ""
        if referral_code:
            referral_block = (
                f"\nREFER & EARN 🎁\n"
                f"  Your code: {referral_code}\n"
                f"  Share it with friends — they get 10% off (min. spend Rs.15,000), and you earn "
                f"Rs.{REFERRAL_REWARD_AMOUNT} credit towards your next booking every time it's used.\n"
            )
        tnc_line = f"\nPlease review our Terms & Conditions: {TERMS_URL}\n" if is_booking else ""
        body = f"""Hi {first_name}! 🎉

{intro_line} (Ref #{lead_id})

Your details:
  Event Date  : {req.event_date.isoformat() if req.event_date else '—'}
  Theme       : {req.theme or '—'}
  City        : {req.city or '—'}
{remarks_block}{order_block}{services_block}{dj_addons_block}{venue_block}{gift_delivery_block}{reward_block}{referral_block}{tnc_line}
If you have any questions in the meantime, WhatsApp us at +91 90044 35362.

Warmly,
Team Wondershop 🎈
wondershopexperiences.com
"""
        html_body = _build_html_email(
            is_booking=is_booking, lead_id=lead_id, req=req,
            reward_code=reward_code, referral_code=referral_code, recipient_kind="customer",
            added_service_label=added_service_label,
        )
        # 2026-08-14, per Shruti: attach the actual .ics calendar invite the
        # confirmation page/email already promise ("your date is blocked!").
        ics_attachments = []
        if is_booking:
            ics_bytes = _build_ics_bytes(req, lead_id)
            if ics_bytes:
                ics_attachments = [(f"wondershop-booking-{lead_id}.ics", ics_bytes, "text", "calendar")]
        await _gmail_send(to_email=req.email, subject=subject, body=body, html_body=html_body, attachments=ics_attachments)
        logger.info(f"Lead #{lead_id}: user ACK sent to {req.email}"
                    f"{' with calendar invite' if ics_attachments else ''}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: user ACK email failed — {exc}")


# ─── 2. TEAM NOTIFICATION EMAIL ──────────────────────────────────────────────

async def _send_team_email(lead_id: int, req: LeadSubmitRequest, reward_code: Optional[str], referral_code: Optional[str] = None,
                            event_sales_lead: Optional[str] = None, added_service_label: Optional[str] = None) -> None:
    """Alert email to the Wondershop team."""
    if not settings.GMAIL_CLIENT_ID:
        logger.warning("GMAIL credentials not configured — skipping team email")
        return

    try:
        is_booking = bool(req.is_booking)
        budget_str = f"Rs.{req.client_budget:,.0f}" if req.client_budget else "—"
        remarks_block = f"\nSPECIAL REQUESTS / REMARKS\n  {req.remarks}\n" if req.remarks else ""
        order_block = _format_order_summary_block(req)
        services_block = _format_services_block(req, added_service_label)
        dj_addons_block = _format_dj_addons_block(req)
        venue_block = _format_venue_block(req)
        gift_delivery_block = _format_gift_delivery_block(req)
        reward_block = ""
        if req.reward_type:
            reward_block = _format_reward_block(req, reward_code, added_service_label).replace(
                "YOUR REWARD 🎁",
                "SCRATCH-CARD REWARD WON — please action this on the account ⚠️",
            )
        redeemed_line = f"\nCoupon Redeemed: {req.redeemed_coupon_code}\n" if req.redeemed_coupon_code else ""
        referral_line = f"\nReferral Code Issued: {referral_code}\n" if referral_code else ""
        sales_lead_line = f"\nEvent Sales Lead: {event_sales_lead}\n" if event_sales_lead else ""
        tnc_line = f"\nTerms & Conditions: {TERMS_URL}\n" if is_booking else ""
        kind = "BOOKING" if is_booking else "LEAD"
        body = f"""New {kind.lower()} #{lead_id} received on Wondershop website.

PARENT
  Name   : {req.parent_name}
  Mobile : {req.phone}
  Email  : {req.email or '—'}

CHILDREN
  Names    : {req.child_names or '—'}
  Turning Age : {req.child_ages or '—'}
  Gender(s): {req.child_genders or '—'}

EVENT
  Date       : {req.event_date or '—'}
  Kids Count : {req.kids_count or '—'}
  Theme      : {req.theme or '—'}
  Venue      : {req.venue or '—'} ({req.location_type or '—'})
  City       : {req.city or '—'}   Pincode: {req.pincode or '—'}
  Budget     : {budget_str}
{remarks_block}{order_block}{services_block}{dj_addons_block}{venue_block}{gift_delivery_block}{reward_block}{redeemed_line}{referral_line}{sales_lead_line}{tnc_line}
SOURCE
  {req.lead_source or '—'} / {req.lead_source_detail or '—'}
  Referred by: {req.referred_by or '—'}

— Wondershop Lead System
"""
        html_body = _build_html_email(
            is_booking=is_booking, lead_id=lead_id, req=req,
            reward_code=reward_code, referral_code=referral_code, recipient_kind="team",
            event_sales_lead=event_sales_lead, added_service_label=added_service_label,
        )
        team_subject = _booking_subject_line(lead_id, req) if is_booking else _lead_subject_line(lead_id, req)

        attachments = []
        if is_booking:
            try:
                form_data = assemble_order_form_data(req, lead_id, event_sales_lead, reward_code, added_service_label)
                form_data = await fetch_order_form_images(form_data)
                xlsx_bytes = build_order_form_xlsx(form_data)
                pdf_bytes = build_order_form_pdf(form_data)
                attachments = [
                    (order_form_filename(form_data, "xlsx"), xlsx_bytes,
                     "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    (order_form_filename(form_data, "pdf"), pdf_bytes, "application", "pdf"),
                ]
            except Exception as exc:
                logger.error(f"Lead #{lead_id}: order form generation failed — {exc}")

            # 2026-08-14, per Shruti: same .ics calendar invite sent to the
            # customer also goes to the team, so their date is blocked too.
            ics_bytes = _build_ics_bytes(req, lead_id)
            if ics_bytes:
                attachments.append((f"wondershop-booking-{lead_id}.ics", ics_bytes, "text", "calendar"))

        await _gmail_send(
            to_email=settings.EMAIL_TEAM,
            subject=team_subject,
            body=body,
            html_body=html_body,
            attachments=attachments,
        )
        logger.info(f"Lead #{lead_id}: team email sent to {settings.EMAIL_TEAM}"
                    f"{' with order form attached' if attachments else ''}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: team email failed — {exc}")


# ─── 3. GOOGLE SHEET ─────────────────────────────────────────────────────────

# 2026-08-14, per Shruti — "google sheet - add all services. Add column for
# decor, pinnata, return gifts (mention all return gifts as comma separated
# with packaging), music, host, activities (comma separated), photography
# (tier with addons), einvite." All of this already lives in
# req.builder_snapshot (builder.html's buildSnapshot()) — just wasn't broken
# out into its own sheet columns before. Photography has no separate
# "addons" concept in the data yet (S.photo is just {tier, p}) — so that
# column shows the tier alone until addons are added as a real feature.
def _sheet_service_columns(snapshot: Optional[dict]) -> dict:
    snap = snapshot or {}

    def _name(key: str) -> str:
        v = snap.get(key)
        return (v.get("n") or "") if isinstance(v, dict) else ""

    decor = _name("decor")

    pinata = _name("pinata")

    einvite = _name("einvite")

    host = (snap.get("host") or {}).get("tier") or "" if isinstance(snap.get("host"), dict) else ""

    dj = snap.get("dj") or {}
    dj_tier = dj.get("tier") if isinstance(dj, dict) else None
    dj_addons = snap.get("dj_addons") or {}
    addon_labels = []
    if dj_addons.get("lights"):
        addon_labels.append("Music Lights")
    if dj_addons.get("smoke"):
        addon_labels.append("Smoke Machine")
    music = ", ".join(filter(None, [_music_label(dj_tier) if dj_tier else None] + addon_labels))

    activities = ", ".join(
        a.get("n", "") for a in (snap.get("activities") or []) if isinstance(a, dict) and a.get("n")
    )

    photo = (snap.get("photo") or {}).get("tier") or "" if isinstance(snap.get("photo"), dict) else ""

    gifts_list = snap.get("gifts") or []
    gift_parts = [
        f"{g.get('n', '')} x{g.get('qty', '')}"
        for g in gifts_list if isinstance(g, dict) and g.get("n")
    ]
    packaging = snap.get("gift_packaging")
    if packaging:
        gift_parts.append(f"Packaging: {packaging}")
    # 2026-08-18, per Shruti — "thankyou tags are not getting added": same
    # gap as _services_detail_list above — the sheet's Return Gifts column
    # never included this even though buildSnapshot() always sent it.
    if snap.get("gift_thank_you_note"):
        gift_parts.append("Thank You Note requested")
    return_gifts = ", ".join(gift_parts)

    return {
        "decor": decor,
        "pinata": pinata,
        "return_gifts": return_gifts,
        "music": music,
        "host": host,
        "activities": activities,
        "photography": photo,
        "einvite": einvite,
    }


async def _append_to_sheet(lead_id: int, req: LeadSubmitRequest, reward_code: Optional[str], referral_code: Optional[str] = None) -> None:
    """
    POST to the Google Apps Script webhook.
    The Apps Script appends one row to the sheet.
    """
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping sheet append")
        return

    try:
        service_cols = _sheet_service_columns(req.builder_snapshot)
        payload = {
            "lead_id":      lead_id,
            "submitted_at": datetime.utcnow().isoformat(),
            "parent_name":  req.parent_name,
            "phone":        req.phone,
            "email":        req.email or "",
            "event_date":   req.event_date.isoformat() if req.event_date else "",
            "kids_count":   req.kids_count or "",
            "child_names":  req.child_names or "",
            "child_ages":   req.child_ages or "",
            "child_genders":req.child_genders or "",
            # 2026-08-14, per Shruti — DOB captured in the Sheet for
            # reference, and also persisted to the `leads` DB table (see
            # migration 013 + the INSERT in submit_lead() above).
            "child_dobs":   req.child_dobs or "",
            "decor":        service_cols["decor"],
            "pinata":       service_cols["pinata"],
            "return_gifts": service_cols["return_gifts"],
            "music":        service_cols["music"],
            "host":         service_cols["host"],
            "activities":   service_cols["activities"],
            "photography":  service_cols["photography"],
            "einvite":      service_cols["einvite"],
            "theme":        req.theme or "",
            "interests":    req.interests or "",
            "interest_other": req.interest_other or "",
            "venue":        req.venue or "",
            "venue_maps_link":    req.venue_maps_link or "",
            "venue_contact_name": req.venue_contact_name or "",
            "venue_contact_phone":req.venue_contact_phone or "",
            "location_type":req.location_type or "",
            "city":         req.city or "",
            "pincode":      req.pincode or "",
            "client_budget":req.client_budget or "",
            "lead_source":  req.lead_source or "",
            "referred_by":  req.referred_by or "",
            "order_grand_total":  req.order_grand_total or "",
            "order_discount_pct": req.order_discount_pct or "",
            "order_advance":      req.order_advance or "",
            "order_balance":      req.order_balance or "",
            "order_total_savings": req.order_total_savings or "",
            "order_freebies_text": req.order_freebies_text or "",
            "reward_type":        req.reward_type or "",
            "reward_label":       req.reward_label or "",
            "reward_value":       req.reward_value or "",
            "reward_terms":       req.reward_terms or "",
            "reward_expiry":      req.reward_expiry.isoformat() if req.reward_expiry else "",
            "reward_code":        reward_code or "",
            "redeemed_coupon_code": req.redeemed_coupon_code or "",
            "referral_code":      referral_code or "",
            "remarks":            req.remarks or "",
            "lead_source_detail": req.lead_source_detail or "",
            "gift_delivery_address":      req.gift_delivery_address or "",
            "gift_delivery_maps_link":    req.gift_delivery_maps_link or "",
            "gift_delivery_address_type": req.gift_delivery_address_type or "",
            "gift_delivery_contact":      req.gift_delivery_contact or "",
            "gift_delivery_contact_phone":req.gift_delivery_contact_phone or "",
            "gift_required_by_date":      req.gift_required_by_date.isoformat() if req.gift_required_by_date else "",
            "dj_lights_addon":            "Yes" if req.dj_lights_addon else "No",
            "dj_smoke_machine_addon":     "Yes" if req.dj_smoke_machine_addon else "No",
            "cart_snapshot":      json.dumps(req.builder_snapshot) if req.builder_snapshot else "",
            "status":       "Confirmed" if req.is_booking else "Lead",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Lead #{lead_id}: sheet append → {r.status_code}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: sheet append failed — {exc}")


async def _append_abandoned_cart_to_sheet(req: AbandonedCartRequest) -> None:
    """
    POST to the same Google Apps Script webhook as _append_to_sheet, but
    flagged action='abandoned_cart' — the script routes that to its own
    'Abandoned Carts' tab instead of 'Leads & Bookings', so half-filled
    carts never mix with real leads/bookings (2026-08-27, per Shruti).
    """
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping abandoned-cart sheet append")
        return

    try:
        service_cols = _sheet_service_columns(req.builder_snapshot)
        snapshot = req.builder_snapshot or {}
        payload = {
            "action":            "abandoned_cart",
            "submitted_at":      datetime.utcnow().isoformat(),
            "phone":             req.phone,
            "parent_name":       req.parent_name or "",
            "email":             req.email or "",
            "child_names":       req.child_names or "",
            "event_date":        req.event_date.isoformat() if req.event_date else "",
            "kids_count":        req.kids_count or "",
            "theme":             req.theme or "",
            "venue":             req.venue or "",
            "pincode":           req.pincode or "",
            "decor":             service_cols["decor"],
            "pinata":            service_cols["pinata"],
            "return_gifts":      service_cols["return_gifts"],
            "music":             service_cols["music"],
            "host":              service_cols["host"],
            "activities":        service_cols["activities"],
            "photography":       service_cols["photography"],
            "einvite":           service_cols["einvite"],
            "estimated_total":   snapshot.get("estimated_total") or "",
            "last_screen":       req.last_screen or "",
            "idle_minutes":      req.idle_minutes or "",
            "lead_source":       req.lead_source or "",
            "lead_source_detail":req.lead_source_detail or "",
            "page_url":          req.page_url or "",
            "cart_snapshot":     json.dumps(req.builder_snapshot) if req.builder_snapshot else "",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Abandoned cart ({req.phone}): sheet append → {r.status_code}")
    except Exception as exc:
        logger.error(f"Abandoned cart ({req.phone}): sheet append failed — {exc}")


# ─── 4. WHATSAPP (via AiSensy) ───────────────────────────────────────────────
#
# AiSensy is a WhatsApp BSP (Business Solution Provider) — it sits on top of
# Meta's WhatsApp Business API but replaces the raw Graph API call with a
# simple API-key-authenticated POST, and gives a dashboard for managing/
# approving templates instead of Meta Business Manager directly.
#
# Prereqs on the AiSensy side (one-time setup, in the AiSensy dashboard), one
# template + campaign PER message type below — AiSensy validates templateParams
# against whichever template the campaign is linked to, so mixing content from
# one template into another campaign's send fails with a 400 (2026-08-14, per
# Shruti — this is what was silently breaking WhatsApp: AISENSY_CAMPAIGN_NAME
# turned out to be a CUSTOMER-facing "Booking Confirmed" template, not the
# internal team-alert draft the code below originally assumed):
#   1. Get the API key: Manage → API Key.
#   2. Create the template (Templates → Create), submit for Meta approval.
#   3. Once approved: Campaigns → Launch campaign → API Campaign → link it to
#      that template → set the campaign live. Note its exact campaign name.
#   4. Put the API key + the relevant campaign name(s) in Railway env vars —
#      AISENSY_API_KEY plus AISENSY_CAMPAIGN_NAME (customer confirmation) and/or
#      AISENSY_TEAM_CAMPAIGN_NAME (internal team alert, see config.py).

AISENSY_SEND_URL = "https://backend.aisensy.com/campaign/t1/api/v2"


async def _send_whatsapp(to_number: str, user_name: str, params: list, campaign_name: str) -> Optional[httpx.Response]:
    """Low-level AiSensy send: posts `params` as templateParams, IN THE EXACT
    ORDER the target template's placeholders expect, to one WhatsApp number
    under `campaign_name`. Every caller must pass params matching that
    specific campaign's approved template — AiSensy 400s otherwise."""
    if not settings.AISENSY_API_KEY or not campaign_name:
        return None

    # AiSensy wants the number WITH country code, no leading +/00.
    phone = to_number.lstrip("+")
    payload = {
        "apiKey":          settings.AISENSY_API_KEY,
        "campaignName":    campaign_name,
        "destination":     phone,
        "userName":        user_name or "Wondershop",
        "templateParams":  params,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(AISENSY_SEND_URL, json=payload)
    if r.status_code == 200:
        logger.info(f"WhatsApp (AiSensy) sent to +{phone} ✅")
    else:
        logger.error(f"WhatsApp (AiSensy) failed to +{phone}: {r.status_code} — {r.text}")
    return r


async def _send_whatsapp_booking_confirmation(lead_id: int, req: LeadSubmitRequest) -> None:
    """Sends the AiSensy-approved "Booking Confirmed" template to the
    CUSTOMER's own WhatsApp number (2026-08-14, per Shruti — confirmed via
    the actual approved template text, which reads "Hi {{1}}! Your booking
    for {{2}}'s birthday on {{3}} is officially confirmed! ... Booking ID:
    {{4}}"). Fires only for confirmed bookings, immediately (same timing as
    the customer's confirmation email in _notify_customer — no need to wait
    on the scratch card, this is just confirming the booking itself)."""
    if not req.is_booking or not req.phone:
        return
    if not settings.AISENSY_API_KEY or not settings.AISENSY_CAMPAIGN_NAME:
        return
    try:
        first_name = _cap_first(req.parent_name.split()[0] if req.parent_name else None)
        params = [
            first_name,
            req.child_names or "your little one",
            _fmt_date_long(req.event_date) if req.event_date else "your event date",
            f"#{lead_id}",
        ]
        await _send_whatsapp(req.phone, first_name, params, settings.AISENSY_CAMPAIGN_NAME)
        logger.info(f"Lead #{lead_id}: WhatsApp booking confirmation sent to customer")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: WhatsApp booking confirmation failed — {exc}")


async def _send_whatsapp_alerts(lead_id: int, req: LeadSubmitRequest) -> None:
    """Sends a new-lead alert (name/phone/theme/city/budget) to both internal
    team numbers — needs its OWN AiSensy template + campaign, separate from
    the customer-facing "Booking Confirmed" one on AISENSY_CAMPAIGN_NAME
    (2026-08-14, per Shruti — see module docstring above). Until that second
    template is created in AiSensy and its campaign name is set as
    AISENSY_TEAM_CAMPAIGN_NAME on Railway, this is a harmless no-op — the
    team still gets the full email with the order form either way."""
    if not settings.AISENSY_API_KEY or not settings.AISENSY_TEAM_CAMPAIGN_NAME:
        logger.info(f"Lead #{lead_id}: AISENSY_TEAM_CAMPAIGN_NAME not set — skipping team WhatsApp alert (team email still sent)")
        return

    try:
        budget_str = f"Rs.{req.client_budget:,.0f}" if req.client_budget else "—"
        params = [
            req.parent_name or "—",
            req.phone or "—",
            req.theme or "—",
            req.city or "—",
            budget_str,
        ]
        await asyncio.gather(
            _send_whatsapp(settings.WS_PHONE_1, req.parent_name, params, settings.AISENSY_TEAM_CAMPAIGN_NAME),
            _send_whatsapp(settings.WS_PHONE_2, req.parent_name, params, settings.AISENSY_TEAM_CAMPAIGN_NAME),
            return_exceptions=True,
        )
        logger.info(f"Lead #{lead_id}: WhatsApp alerts sent")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: WhatsApp failed — {exc}")


# ─── FIRE ALL FOUR IN PARALLEL ───────────────────────────────────────────────

async def _notify_customer(lead_id: int, req: LeadSubmitRequest, reward_code: Optional[str], referral_code: Optional[str]) -> None:
    """Fired synchronously from /submit, always: the ops-facing Google Sheet
    row (so the live tracker updates instantly), the customer's own
    confirmation email, and (for confirmed bookings) the "Booking Confirmed"
    WhatsApp message to the customer — all go out right away, not held for
    the scratch-card interaction. Only the team-facing notification waits on
    that (2026-08-12, per Shruti — see _notify_team() below)."""
    await asyncio.gather(
        _append_to_sheet(lead_id, req, reward_code, referral_code),
        _send_user_ack(lead_id, req, reward_code, referral_code),
        _send_whatsapp_booking_confirmation(lead_id, req),
        return_exceptions=True,
    )


async def _notify_team(lead_id: int, req: LeadSubmitRequest, reward_code: Optional[str], referral_code: Optional[str],
                        event_sales_lead: Optional[str] = None, added_service_label: Optional[str] = None) -> None:
    """The ops-facing "order booking" notification — team email (with the
    order execution form attached). Team WhatsApp alerts are deliberately
    OFF for now (2026-08-14, per Shruti: "let's skip whatsapp alert for the
    team for now, let's do whatsapp for only the customer") — see
    _send_whatsapp_alerts() above, kept ready but unused; uncomment the
    gather line below once a team-alert AiSensy template + campaign exist
    and AISENSY_TEAM_CAMPAIGN_NAME is set. For a confirmed booking this is
    deliberately held back until the scratch-card interaction is over
    (explicit close, a 5-minute idle-timeout fallback, or a tab-close beacon
    — see builder.html's finalizeAndNotify()) so it can say whether a
    Tattoo/Bubble Artist reward was added to the booking (2026-08-12, per
    Shruti: "send the order booking to wondershop with order form after the
    scratch card"). Plain enquiries have no scratch card to wait on —
    /submit fires this immediately for those instead."""
    await asyncio.gather(
        _send_team_email(lead_id, req, reward_code, referral_code, event_sales_lead, added_service_label),
        # _send_whatsapp_alerts(lead_id, req),  # re-enable once AISENSY_TEAM_CAMPAIGN_NAME is set
        return_exceptions=True,   # one failure must never cancel the other
    )


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/submit")
async def submit_lead(req: LeadSubmitRequest):
    """
    1. Saves lead to DB (is_booking = True for confirmed bookings, False for leads; status = New either way).
    2. Issues a reward code if the customer won the "discount" scratch-card
       reward, and/or redeems one if they applied a previously-issued code.
    3. Notifies the customer (sheet row + confirmation email) immediately.
       Notifies the team (email + WhatsApp) immediately too, but only for
       plain enquiries — confirmed bookings hold that until /finalize-notify.
    """
    # 2026-08-19, per Shruti's admin panel status-workflow request (see
    # migrations/017_lead_status_workflow.sql, then 018_booking_flag_and_
    # status_simplify.sql). is_booking is now the real table-membership flag
    # (Leads table vs. Bookings table in admin.html) — a direct checkout
    # submission is a booking from the moment it's created, so it skips the
    # lead pipeline entirely. `status` itself only ever needs to distinguish
    # "New"(not cancelled) from "Cancelled" for booking rows — Upcoming/
    # Complete are computed live from event_date, never stored (see
    # _booking_display_status() in routers/admin.py).
    status = "New"
    is_booking_flag = bool(req.is_booking)
    event_sales_lead = await _resolve_sales_lead_name(req.sales_lead_code)
    lead_id = await database.execute(
        """
        INSERT INTO leads (
            parent_name, phone, child_names, email,
            event_date, event_time, kids_count, child_ages, child_genders, child_dobs,
            venue, venue_maps_link, venue_contact_name, venue_contact_phone,
            location_type, theme, city, pincode,
            client_budget, payment_method, builder_snapshot, remarks,
            order_grand_total, order_discount_pct, order_advance, order_balance,
            order_total_savings, order_freebies_text,
            lead_source, lead_source_detail, referred_by,
            gift_delivery_address, gift_delivery_maps_link,
            gift_delivery_address_type, gift_delivery_contact,
            gift_delivery_contact_phone,
            gift_required_by_date,
            dj_lights_addon, dj_smoke_machine_addon,
            redeemed_coupon_code, event_sales_lead,
            reward_type, reward_label, reward_value, reward_expiry,
            interests, interest_other,
            status, is_booking
        ) VALUES (
            :parent_name, :phone, :child_names, :email,
            :event_date, :event_time, :kids_count, :child_ages, :child_genders, :child_dobs,
            :venue, :venue_maps_link, :venue_contact_name, :venue_contact_phone,
            :location_type, :theme, :city, :pincode,
            :client_budget, :payment_method, :builder_snapshot, :remarks,
            :order_grand_total, :order_discount_pct, :order_advance, :order_balance,
            :order_total_savings, :order_freebies_text,
            :lead_source, :lead_source_detail, :referred_by,
            :gift_delivery_address, :gift_delivery_maps_link,
            :gift_delivery_address_type, :gift_delivery_contact,
            :gift_delivery_contact_phone,
            :gift_required_by_date,
            :dj_lights_addon, :dj_smoke_machine_addon,
            :redeemed_coupon_code, :event_sales_lead,
            :reward_type, :reward_label, :reward_value, :reward_expiry,
            :interests, :interest_other,
            :status, :is_booking
        )
        RETURNING lead_id
        """,
        values={
            "parent_name":        req.parent_name,
            "phone":              req.phone,
            "child_names":        req.child_names,
            "email":              req.email,
            "event_date":         req.event_date,
            "event_time":         req.event_time,
            "kids_count":         req.kids_count,
            "child_ages":         req.child_ages,
            "child_genders":      req.child_genders,
            "child_dobs":         req.child_dobs,
            "venue":              req.venue,
            "venue_maps_link":    req.venue_maps_link,
            "venue_contact_name": req.venue_contact_name,
            "venue_contact_phone":req.venue_contact_phone,
            "location_type":      req.location_type,
            "theme":              req.theme,
            "city":               req.city,
            "pincode":            req.pincode,
            "client_budget":      req.client_budget,
            "payment_method":     req.payment_method,
            "builder_snapshot":   json.dumps(req.builder_snapshot) if req.builder_snapshot else None,
            "remarks":            req.remarks,
            "order_grand_total":  req.order_grand_total,
            "order_discount_pct": req.order_discount_pct,
            "order_advance":      req.order_advance,
            "order_balance":      req.order_balance,
            "order_total_savings": req.order_total_savings,
            "order_freebies_text": req.order_freebies_text,
            "lead_source":        req.lead_source,
            "lead_source_detail": req.lead_source_detail,
            "referred_by":        req.referred_by,
            "gift_delivery_address":      req.gift_delivery_address,
            "gift_delivery_maps_link":    req.gift_delivery_maps_link,
            "gift_delivery_address_type": req.gift_delivery_address_type,
            "gift_delivery_contact":      req.gift_delivery_contact,
            "gift_delivery_contact_phone":req.gift_delivery_contact_phone,
            "gift_required_by_date":      req.gift_required_by_date,
            "dj_lights_addon":            bool(req.dj_lights_addon),
            "dj_smoke_machine_addon":     bool(req.dj_smoke_machine_addon),
            "redeemed_coupon_code":       req.redeemed_coupon_code,
            "event_sales_lead":           event_sales_lead,
            # Persisted so /api/leads/redeem-service (the tattoo/bubble
            # "add to today's booking" button on the scratch-card reveal)
            # can verify the redemption against what was actually won —
            # see migrations/011_add_reward_type_to_leads.sql (2026-08-12
            # bugfix).
            "reward_type":                req.reward_type,
            "reward_label":               req.reward_label,
            "reward_value":               req.reward_value,
            "reward_expiry":              req.reward_expiry,
            "interests":                  req.interests,
            "interest_other":             req.interest_other,
            "status":                     status,
            "is_booking":                 is_booking_flag,
        },
    )

    # Reward code issue/redeem — best-effort, never blocks the booking itself.
    reward_code = None
    referral_code = None
    try:
        if req.reward_type == "discount":
            reward_code = await _issue_reward_code(lead_id, req.phone, req.reward_expiry)
        if req.redeemed_coupon_code:
            await _redeem_any_code(req.redeemed_coupon_code.strip().upper(), req.phone, lead_id)
        if req.is_booking:
            # Every confirmed booking gets (or reuses) their own Refer & Earn code.
            referral_code = await _get_or_create_referral_code(lead_id, req.parent_name, req.phone)
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: reward/referral code handling failed — {exc}")

    # Sheet row + customer confirmation email go out immediately either way
    # — the customer shouldn't wait on the scratch card for their own
    # confirmation (2026-08-12, per Shruti).
    await _notify_customer(lead_id, req, reward_code, referral_code)

    # The team-facing "order booking" notification (email + WhatsApp) is
    # held back for confirmed bookings until the scratch-card interaction is
    # over — see /finalize-notify and _notify_team()'s docstring. Plain
    # enquiries (is_booking=False) never show a scratch card, so there's no
    # "wait for" event to hold on — notify the team right away, as before.
    if not req.is_booking:
        await _notify_team(lead_id, req, reward_code, referral_code, event_sales_lead)

    return {
        "success": True,
        "lead_id": lead_id,
        "reward_code": reward_code,
        "referral_code": referral_code,
        "message": "We'll be in touch within a few hours!",
    }


class FinalizeNotifyRequest(LeadSubmitRequest):
    """Same shape as the original /submit payload (the frontend just resends
    it), plus the pieces only known after /submit returned."""
    lead_id:       int
    reward_code:   Optional[str] = None
    referral_code: Optional[str] = None


@router.post("/finalize-notify")
async def finalize_notify(req: FinalizeNotifyRequest):
    """
    Sends the team-facing "order booking" notification (email with the order
    execution form attached + WhatsApp alert to the Wondershop team numbers)
    for a booking /submit already saved and confirmed to the customer. The
    customer's own email already went out immediately at /submit — this is
    just the ops side, deliberately held until the scratch-card interaction
    is over so it can say whether a Tattoo/Bubble Artist reward was added
    (2026-08-12, per Shruti). Called from builder.html's finalizeAndNotify():
    explicit modal close ("Awesome, got it!" / ✕), a 5-minute idle-timeout
    fallback, or a tab-close/navigate-away beacon — whichever fires first.

    Whether a Tattoo/Bubble Artist reward was added to THIS booking is read
    straight from the DB (redeemed_reward_service, set by /redeem-service)
    rather than trusted from the request — so this always matches what's
    actually on the booking, even if the client's local state is stale.
    """
    event_sales_lead = await _resolve_sales_lead_name(req.sales_lead_code)

    added_service_label = None
    row = await database.fetch_one(
        "SELECT redeemed_reward_service FROM leads WHERE lead_id = :id",
        values={"id": req.lead_id},
    )
    if row and row["redeemed_reward_service"]:
        service = row["redeemed_reward_service"]
        added_service_label = req.reward_label or f"Free {REWARD_SERVICE_LABELS.get(service, service)}"

    await _notify_team(req.lead_id, req, req.reward_code, req.referral_code, event_sales_lead, added_service_label)
    return {"success": True}


# ─── ADD SCRATCH-CARD SERVICE REWARD TO CURRENT BOOKING ──────────────────────
# Some rewards (Free Tattoo Artist, Free Bubble Artist) are services that can
# be tacked onto the booking that just won them, right from the scratch-card
# reveal screen — instead of only being usable later. Everything else
# (refund, discount-code) is handled elsewhere and doesn't go through here.

REWARD_SERVICE_LABELS = {
    "tattoo": "Tattoo Artist",
    "bubble": "Bubble Artist",
}


class RedeemServiceRequest(LeadSubmitRequest):
    """Same shape as /submit's payload (the frontend resends it, held in
    S._pendingNotifyPayload) plus the reward-specific fields — needed so the
    "order upgrade" email below can include the full original booking
    content, not just a short note (2026-08-12, per Shruti)."""
    lead_id:       int
    service:       str            # 'tattoo' | 'bubble'
    service_label: Optional[str] = None   # e.g. "Free Tattoo Artist" — for display in the notifications
    reward_code:   Optional[str] = None
    referral_code: Optional[str] = None


async def _update_sheet_reward_service(lead_id: int, service_label: str) -> None:
    """Pushes an update to the customer's EXISTING sheet row (found by Lead
    ID) rather than appending a new one — see the matching `action` handler
    in google_sheet_webhook.js."""
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping sheet update")
        return
    try:
        payload = {
            "action": "update_reward_service",
            "lead_id": lead_id,
            "service_label": service_label,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Lead #{lead_id}: sheet reward-service update → {r.status_code}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: sheet reward-service update failed — {exc}")


@router.post("/redeem-service")
async def redeem_service_now(req: RedeemServiceRequest):
    """
    Customer opted, right from the scratch-card reveal, to add their
    complimentary service reward (Tattoo Artist / Bubble Artist) onto the
    CURRENT booking instead of saving it for a future one. Records it on the
    lead, updates the existing Sheet row in place, and sends the customer an
    "order upgrade" email — the same full booking confirmation content as
    the original, plus this service — so they have one complete, up-to-date
    email rather than a separate short follow-up (2026-08-12, per Shruti).
    The team-facing notification is NOT sent from here — it still waits for
    /finalize-notify once the scratch-card modal is done with, so it can
    reflect this addition too.
    """
    service = (req.service or "").strip().lower()
    if service not in REWARD_SERVICE_LABELS:
        return {"success": False, "message": "That reward can't be added to a booking directly."}

    row = await database.fetch_one(
        "SELECT lead_id, reward_type, redeemed_reward_service FROM leads WHERE lead_id = :id",
        values={"id": req.lead_id},
    )
    if not row:
        return {"success": False, "message": "We couldn't find that booking."}
    if row["redeemed_reward_service"]:
        # Idempotent — customer may have double-tapped the button.
        return {"success": True, "already": True, "message": "This is already on your booking."}
    if row["reward_type"] != service:
        # Safety check: don't let a stale/replayed request tack on a reward
        # that wasn't actually the one won on this booking.
        return {"success": False, "message": "This reward isn't linked to this booking."}

    label = req.service_label or f"Free {REWARD_SERVICE_LABELS[service]}"

    await database.execute(
        "UPDATE leads SET redeemed_reward_service = :service, redeemed_reward_service_at = NOW() "
        "WHERE lead_id = :id",
        values={"service": service, "id": req.lead_id},
    )
    try:
        await _update_sheet_reward_service(req.lead_id, label)
    except Exception as exc:
        logger.error(f"Lead #{req.lead_id}: sheet reward-service update failed — {exc}")

    try:
        await _send_user_ack(req.lead_id, req, req.reward_code, req.referral_code,
                              added_service_label=label, is_upgrade=True)
    except Exception as exc:
        logger.error(f"Lead #{req.lead_id}: order-upgrade email failed — {exc}")

    return {"success": True, "message": f"{label} added to your booking!"}


@router.get("/status/{lead_id}")
async def get_lead_status(lead_id: int):
    """Current lead status — for internal dashboard use."""
    row = await database.fetch_one(
        """
        SELECT lead_id, parent_name, phone, event_date, status,
               lead_source, converted_on, order_id
        FROM leads WHERE lead_id = :id
        """,
        values={"id": lead_id},
    )
    return dict(row) if row else {}


@router.post("/abandoned-cart")
async def report_abandoned_cart(req: AbandonedCartRequest):
    """
    Fired client-side (builder.html's wsReportAbandonedCart()) after 10
    minutes of zero interaction in the cart builder/checkout, once a valid
    10-digit phone has been entered somewhere on screen but no real
    submission (doCo/doLead) has gone through yet.

    Sheet-only by design (2026-08-27, per Shruti) — no DB row, no
    email/WhatsApp alert. It lands in the "Abandoned Carts" tab for the
    team to work through on their own cadence, without generating an
    alert for every idle tab.
    """
    digits = "".join(ch for ch in req.phone if ch.isdigit())
    if len(digits) != 10:
        raise HTTPException(status_code=400, detail="Valid 10-digit phone required")
    await _append_abandoned_cart_to_sheet(req)
    return {"ok": True}
