"""
Leads endpoint — captures inbound enquiries before they become orders.
Source of truth: WS_DataDictionary_v1.docx (leads table)

On every new lead submission, four things fire in parallel (fire-and-forget):
  1. User acknowledgement email  → req.email
  2. Team notification email     → settings.EMAIL_TEAM
  3. Google Sheet row append     → settings.GOOGLE_SHEET_WEBHOOK_URL
  4. WhatsApp alert              → WS_PHONE_1 + WS_PHONE_2 via Meta Cloud API
"""
import json
import asyncio
import logging
import httpx
from datetime import datetime, date

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from database import database
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── SCHEMA ──────────────────────────────────────────────────────────────────

class LeadSubmitRequest(BaseModel):
    parent_name:        str
    phone:              str         # 10 digits
    child_names:        Optional[str]   = None
    email:              Optional[str]   = None
    event_date:         Optional[date]  = None
    kids_count:         Optional[int]   = None
    child_ages:         Optional[str]   = None
    child_genders:      Optional[str]   = None
    venue:              Optional[str]   = None
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
    # Order summary — sent from the checkout step so the confirmation email
    # can show a full bill, not just the payable total (client_budget).
    order_grand_total:  Optional[float] = None
    order_discount_pct: Optional[float] = None
    order_advance:      Optional[float] = None
    order_balance:      Optional[float] = None
    # Post-booking scratch-card reward — only set when the customer won
    # something (reward_type is None/omitted for "better luck next time").
    reward_type:        Optional[str]   = None
    reward_label:       Optional[str]   = None
    reward_value:       Optional[float] = None
    reward_terms:       Optional[str]   = None
    reward_expiry:      Optional[date]  = None


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

async def _gmail_send(to_email: str, subject: str, body: str) -> None:
    """Send email via Gmail API (HTTPS — no SMTP port issues)."""
    import base64
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = f"Wondershop Experiences <{settings.EMAIL_FROM}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
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


# ─── ORDER SUMMARY / REWARD EMAIL BLOCKS ─────────────────────────────────────
# Shared by the user ack email and (for the reward) the internal team email,
# so the customer's "bill" and the ops team's alert always agree.

def _fmt_rupees(amount: Optional[float]) -> str:
    return f"Rs.{amount:,.0f}" if amount is not None else "—"

def _format_order_summary_block(req: LeadSubmitRequest) -> str:
    """Itemised order summary — acts as the customer's on-email bill."""
    if req.order_grand_total is None and req.client_budget is None:
        return ""
    lines = ["\nYOUR ORDER SUMMARY"]
    if req.order_grand_total is not None:
        lines.append(f"  Grand Total     : {_fmt_rupees(req.order_grand_total)}")
    if req.order_discount_pct:
        lines.append(f"  Discount        : {req.order_discount_pct:.0f}%")
    lines.append(f"  Payable Total   : {_fmt_rupees(req.client_budget)}")
    if req.order_advance is not None:
        lines.append(f"  Advance Paid    : {_fmt_rupees(req.order_advance)}")
    if req.order_balance is not None:
        lines.append(f"  Balance Due     : {_fmt_rupees(req.order_balance)} (before event)")
    lines.append("")
    return "\n".join(lines) + "\n"

def _format_reward_block(req: LeadSubmitRequest) -> str:
    """Scratch-card reward + full terms & conditions — only present if won."""
    if not req.reward_type:
        return ""
    lines = ["\nYOUR REWARD 🎁", f"  {req.reward_label or req.reward_type}"]
    if req.reward_value:
        lines.append(f"  Value: Rs.{req.reward_value:,.0f}")
    if req.reward_expiry:
        lines.append(f"  Valid until: {req.reward_expiry.isoformat()}")
    if req.reward_terms:
        lines.append("  Terms & Conditions:")
        for clause in req.reward_terms.split(" | "):
            clause = clause.strip()
            if clause:
                lines.append(f"    • {clause}")
    lines.append("  Your Account Manager will confirm redemption details with you.")
    lines.append("")
    return "\n".join(lines) + "\n"


# ─── 1. USER ACK EMAIL ───────────────────────────────────────────────────────

async def _send_user_ack(lead_id: int, req: LeadSubmitRequest) -> None:
    """Confirmation email to the parent who submitted the form."""
    if not req.email or "@" not in req.email or "." not in req.email.split("@")[-1]:
        return   # skip if no email or obviously invalid (e.g. test placeholder "string")
    if not settings.GMAIL_CLIENT_ID:
        return

    try:
        remarks_block = f"\nYour special requests / remarks:\n  {req.remarks}\n" if req.remarks else ""
        order_block = _format_order_summary_block(req)
        reward_block = _format_reward_block(req)
        body = f"""Hi {req.parent_name.split()[0]}! 🎉

Thank you for reaching out to Wondershop Experiences.

We've received your enquiry (Ref #{lead_id}) and our team will call you within a few hours to discuss your child's birthday party.

Your details:
  Event Date  : {req.event_date.isoformat() if req.event_date else '—'}
  Theme       : {req.theme or '—'}
  City        : {req.city or '—'}
{remarks_block}{order_block}{reward_block}
If you have any questions in the meantime, WhatsApp us at +91 90044 35362.

Warmly,
Team Wondershop 🎈
wondershopexperiences.com
"""
        await _gmail_send(
            to_email=req.email,
            subject=f"We got your enquiry, {req.parent_name.split()[0]}! 🎈",
            body=body,
        )
        logger.info(f"Lead #{lead_id}: user ACK sent to {req.email}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: user ACK email failed — {exc}")


# ─── 2. TEAM NOTIFICATION EMAIL ──────────────────────────────────────────────

async def _send_team_email(lead_id: int, req: LeadSubmitRequest) -> None:
    """Alert email to the Wondershop team."""
    if not settings.GMAIL_CLIENT_ID:
        logger.warning("GMAIL credentials not configured — skipping team email")
        return

    try:
        budget_str = f"Rs.{req.client_budget:,.0f}" if req.client_budget else "—"
        remarks_block = f"\nSPECIAL REQUESTS / REMARKS\n  {req.remarks}\n" if req.remarks else ""
        order_block = _format_order_summary_block(req)
        reward_block = ""
        if req.reward_type:
            reward_block = _format_reward_block(req).replace(
                "YOUR REWARD 🎁",
                "SCRATCH-CARD REWARD WON — please action this on the account ⚠️",
            )
        body = f"""New lead #{lead_id} received on Wondershop website.

PARENT
  Name   : {req.parent_name}
  Mobile : {req.phone}
  Email  : {req.email or '—'}

CHILDREN
  Names    : {req.child_names or '—'}
  Ages     : {req.child_ages or '—'}
  Gender(s): {req.child_genders or '—'}

EVENT
  Date       : {req.event_date or '—'}
  Kids Count : {req.kids_count or '—'}
  Theme      : {req.theme or '—'}
  Venue      : {req.venue or '—'} ({req.location_type or '—'})
  City       : {req.city or '—'}   Pincode: {req.pincode or '—'}
  Budget     : {budget_str}
{remarks_block}{order_block}{reward_block}
SOURCE
  {req.lead_source or '—'} / {req.lead_source_detail or '—'}
  Referred by: {req.referred_by or '—'}

— Wondershop Lead System
"""
        await _gmail_send(
            to_email=settings.EMAIL_TEAM,
            subject=f"New Lead #{lead_id} — {req.parent_name} ({req.phone})",
            body=body,
        )
        logger.info(f"Lead #{lead_id}: team email sent to {settings.EMAIL_TEAM}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: team email failed — {exc}")


# ─── 3. GOOGLE SHEET ─────────────────────────────────────────────────────────

async def _append_to_sheet(lead_id: int, req: LeadSubmitRequest) -> None:
    """
    POST to the Google Apps Script webhook.
    The Apps Script appends one row to the sheet.
    """
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL not set — skipping sheet append")
        return

    try:
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
            "theme":        req.theme or "",
            "venue":        req.venue or "",
            "location_type":req.location_type or "",
            "city":         req.city or "",
            "pincode":      req.pincode or "",
            "client_budget":req.client_budget or "",
            "lead_source":  req.lead_source or "",
            "referred_by":  req.referred_by or "",
            "status":       "New",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Lead #{lead_id}: sheet append → {r.status_code}")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: sheet append failed — {exc}")


# ─── 4. WHATSAPP ─────────────────────────────────────────────────────────────

async def _send_whatsapp(to_number: str, text: dict) -> None:
    """
    Sends a text message via Meta Cloud API to a single number.
    Requires an approved message template in production.
    During development, add numbers as test recipients in Meta Business Manager.
    """
    if not settings.WHATSAPP_API_URL or not settings.WHATSAPP_ACCESS_TOKEN:
        return

    url = f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    # Strip leading + for Meta API
    phone = to_number.lstrip("+")
    # WhatsApp Business API requires approved templates for outbound messages.
    # Using wondershop_new_lead template (custom). Falls back to hello_world
    # if the custom template isn't approved yet.
    payload = {
        "messaging_product": "whatsapp",
        "to":                phone,
        "type":              "template",
        "template": {
            "name":     "hello_world",   # TODO: switch to wondershop_new_lead once approved
            "language": {"code": "en_US"},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.status_code == 200:
        logger.info(f"WhatsApp sent to +{phone} ✅")
    else:
        logger.error(f"WhatsApp failed to +{phone}: {r.status_code} — {r.text}")
    return r


async def _send_whatsapp_alerts(lead_id: int, req: LeadSubmitRequest) -> None:
    """Sends the same lead alert to both team numbers."""
    if not settings.WHATSAPP_API_URL or not settings.WHATSAPP_ACCESS_TOKEN:
        logger.warning("WhatsApp not configured — skipping")
        return

    try:
        budget_str = f"Rs.{req.client_budget:,.0f}" if req.client_budget else "—"
        msg = {
            "name":   req.parent_name,
            "phone":  req.phone,
            "theme":  req.theme or "—",
            "city":   req.city or "—",
            "budget": budget_str,
        }
        await asyncio.gather(
            _send_whatsapp(settings.WS_PHONE_1, msg),
            _send_whatsapp(settings.WS_PHONE_2, msg),
            return_exceptions=True,
        )
        logger.info(f"Lead #{lead_id}: WhatsApp alerts sent")
    except Exception as exc:
        logger.error(f"Lead #{lead_id}: WhatsApp failed — {exc}")


# ─── FIRE ALL FOUR IN PARALLEL ───────────────────────────────────────────────

async def _notify_all(lead_id: int, req: LeadSubmitRequest) -> None:
    """Runs all four notifications concurrently. Never raises."""
    await asyncio.gather(
        _send_user_ack(lead_id, req),
        _send_team_email(lead_id, req),
        _append_to_sheet(lead_id, req),
        _send_whatsapp_alerts(lead_id, req),
        return_exceptions=True,   # one failure must never cancel the others
    )


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/submit")
async def submit_lead(req: LeadSubmitRequest):
    """
    1. Saves lead to DB (status = New).
    2. Fires all four notifications in parallel (fire-and-forget).
    """
    lead_id = await database.execute(
        """
        INSERT INTO leads (
            parent_name, phone, child_names, email,
            event_date, kids_count, child_ages, child_genders,
            venue, location_type, theme, city, pincode,
            client_budget, builder_snapshot, remarks,
            lead_source, lead_source_detail, referred_by,
            status
        ) VALUES (
            :parent_name, :phone, :child_names, :email,
            :event_date, :kids_count, :child_ages, :child_genders,
            :venue, :location_type, :theme, :city, :pincode,
            :client_budget, :builder_snapshot, :remarks,
            :lead_source, :lead_source_detail, :referred_by,
            'New'
        )
        RETURNING lead_id
        """,
        values={
            "parent_name":        req.parent_name,
            "phone":              req.phone,
            "child_names":        req.child_names,
            "email":              req.email,
            "event_date":         req.event_date,
            "kids_count":         req.kids_count,
            "child_ages":         req.child_ages,
            "child_genders":      req.child_genders,
            "venue":              req.venue,
            "location_type":      req.location_type,
            "theme":              req.theme,
            "city":               req.city,
            "pincode":            req.pincode,
            "client_budget":      req.client_budget,
            "builder_snapshot":   json.dumps(req.builder_snapshot) if req.builder_snapshot else None,
            "remarks":            req.remarks,
            "lead_source":        req.lead_source,
            "lead_source_detail": req.lead_source_detail,
            "referred_by":        req.referred_by,
        },
    )

    # Fire-and-forget — DB save already succeeded before this runs
    await _notify_all(lead_id, req)

    return {
        "success": True,
        "lead_id": lead_id,
        "message": "We'll be in touch within a few hours!",
    }


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
