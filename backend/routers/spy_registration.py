"""
Spy Agent i-card registration — one page per Spy-theme booking.

Architecture (2026-09-22, per Shruti follow-up — "This form will be
unique to a party. How will I trigger the form for every party? ...
I'll suggest give an option for bookings with spy on it to upload the
invite and then generate this page."):

- spy_registration_pages (migration 034) holds one row per BOOKING that
  has this turned on: lead_id, a random share_token (same trust model as
  packaging_lists.share_token — the long token IS the access control, no
  login for parents), and the uploaded invite image, stored as BYTEA in
  Postgres (same pattern as vendor_master.cancelled_cheque_file) and
  served back by GET /invite-image/{token} below — no external image
  host to manage.

- Admin (admin.html, gated by the existing X-Admin-Password) uploads an
  invite for any Spy-theme booking via POST /admin/{lead_id}/invite.
  That single call is the trigger Shruti asked for: it creates the
  spy_registration_pages row + share_token the FIRST time it's called
  for a booking, and just replaces the image (keeping the same link)
  every time after. GET /admin/{lead_id} tells admin.html whether one
  already exists, so it can show "Replace Invite" + the live link vs.
  a first-time "Upload Invite" prompt.

- The public page (spy-agent-registration.html?t=<share_token>) calls
  GET /party/{token} to get the child's name / mission label / invite
  image URL / event date & venue — all derived server-side from the
  `leads` row via the token, never supplied by the browser — and POSTs
  to /register with just that token; the sheet's tab name (mission_label)
  is looked up server-side too, which closes the old gap where event_id
  was free text the browser could send unvalidated.

Submissions are relayed to their OWN dedicated Google Apps Script webhook
(SPY_SHEET_WEBHOOK_URL — deliberately separate from GOOGLE_SHEET_WEBHOOK_URL,
which stays scoped to the Leads & Bookings sheet) with
action="spy_agent_registration" — see spy_sheet_webhook.js's
_appendSpyRegistration(), which creates (or reuses) one worksheet tab per
party inside that dedicated sheet, and (if a photo was uploaded) saves it
to a Drive folder and puts a link to it in the row, since a Sheet cell
can't hold an image directly.
"""
import base64
import logging
import secrets
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Form, File, Header, UploadFile, HTTPException, Response

from database import database
from config import settings
from routers.admin import _require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB — comfortably fits a phone photo
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _sniff_file_type(raw: bytes) -> Optional[str]:
    """What the file REALLY is, judged from its first bytes — the browser-
    supplied Content-Type is just a claim and can say anything (same check
    as vendor_onboarding.py's, image-only subset)."""
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def _clean(v: Optional[str]) -> str:
    return (v or "").strip()


def _format_date(d) -> str:
    if not d:
        return ""
    try:
        return d.strftime("%d %B %Y")
    except AttributeError:
        return str(d)


def _format_time(t: Optional[str]) -> str:
    """'16:00' -> '4:00 PM'. Falls back to whatever was stored if it isn't
    HH:MM (free text has crept into this field before)."""
    t = (t or "").strip()
    if not t:
        return ""
    try:
        hh, mm = (int(x) for x in t.split(":")[:2])
        suffix = "AM" if hh < 12 else "PM"
        hh12 = hh % 12 or 12
        return f"{hh12}:{mm:02d} {suffix}"
    except (ValueError, TypeError):
        return t


def _mission_label(lead) -> str:
    """Used both as the public page's title and as the worksheet tab name
    in the dedicated Spy sheet. Deliberately just child name + event date
    — always available and accurate, unlike an invented ordinal/quest
    name that would need typing in by hand somewhere."""
    child = _clean(lead.get("child_names")) or "Guest"
    date_str = _format_date(lead.get("event_date"))
    return f"{child} — {date_str}" if date_str else child


# ─── ADMIN: upload/replace the invite, check current status ───────────────
# Mirrors admin.html's existing X-Admin-Password pattern (see
# routers/admin.py's _require_admin, reused here rather than duplicated).

@router.get("/admin/{lead_id}")
async def admin_get_status(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one(
        """SELECT share_token, (invite_image IS NOT NULL) AS has_invite,
                  invite_image_name, updated_on
           FROM spy_registration_pages WHERE lead_id = :lead_id""",
        values={"lead_id": lead_id},
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "share_token": row["share_token"],
        "share_url": f"/spy-agent-registration.html?t={row['share_token']}",
        "has_invite": bool(row["has_invite"]),
        "invite_image_name": row["invite_image_name"],
    }


@router.post("/admin/{lead_id}/invite")
async def admin_upload_invite(
    lead_id: int,
    invite_image: UploadFile = File(...),
    x_admin_password: Optional[str] = Header(None),
):
    _require_admin(x_admin_password)

    lead = await database.fetch_one("SELECT lead_id FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="No booking found with that lead ID.")

    raw = await invite_image.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="That image is too large — please keep it under 5MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="No image was received — please choose a file and try again.")
    sniffed = _sniff_file_type(raw)
    if sniffed is None:
        raise HTTPException(status_code=400, detail="The invite must be a JPG, PNG, or WEBP image.")

    existing = await database.fetch_one(
        "SELECT share_token FROM spy_registration_pages WHERE lead_id = :lead_id",
        values={"lead_id": lead_id},
    )
    if existing:
        token = existing["share_token"]
        await database.execute(
            """UPDATE spy_registration_pages
               SET invite_image = :img, invite_image_name = :name, invite_image_type = :type
               WHERE lead_id = :lead_id""",
            values={"img": raw, "name": invite_image.filename, "type": sniffed, "lead_id": lead_id},
        )
    else:
        token = secrets.token_urlsafe(18)
        await database.execute(
            """INSERT INTO spy_registration_pages (lead_id, share_token, invite_image, invite_image_name, invite_image_type)
               VALUES (:lead_id, :token, :img, :name, :type)""",
            values={"lead_id": lead_id, "token": token, "img": raw, "name": invite_image.filename, "type": sniffed},
        )

    return {
        "success": True,
        "share_token": token,
        "share_url": f"/spy-agent-registration.html?t={token}",
    }


# ─── PUBLIC: party info, invite image, and the registration form itself ───

@router.get("/party/{token}")
async def get_party_info(token: str):
    row = await database.fetch_one(
        """SELECT (srp.invite_image IS NOT NULL) AS has_invite,
                  l.child_names, l.event_date, l.event_time, l.venue,
                  l.venue_contact_name, l.venue_contact_phone
           FROM spy_registration_pages srp
           JOIN leads l ON l.lead_id = srp.lead_id
           WHERE srp.share_token = :token""",
        values={"token": token},
    )
    if not row:
        raise HTTPException(status_code=404, detail="This registration link isn't valid — please check the link your host shared.")

    return {
        "child_name": _clean(row.get("child_names")) or "Agent",
        "mission_label": _mission_label(row),
        "event_date_display": _format_date(row.get("event_date")),
        "event_time_display": _format_time(row.get("event_time")),
        "venue": _clean(row.get("venue")),
        "contact_name": _clean(row.get("venue_contact_name")),
        "contact_phone": _clean(row.get("venue_contact_phone")),
        "has_invite": bool(row.get("has_invite")),
        "invite_image_url": f"/api/spy-registration/invite-image/{token}" if row.get("has_invite") else None,
    }


@router.get("/invite-image/{token}")
async def get_invite_image(token: str):
    row = await database.fetch_one(
        "SELECT invite_image, invite_image_type FROM spy_registration_pages WHERE share_token = :token",
        values={"token": token},
    )
    if not row or not row["invite_image"]:
        raise HTTPException(status_code=404, detail="No invite image uploaded yet.")
    return Response(content=bytes(row["invite_image"]), media_type=row["invite_image_type"] or "image/jpeg")


@router.post("/register")
async def register_spy_agent(
    token: str = Form(...),
    agent_name: str = Form(...),
    agent_dob: str = Form(...),
    parent_name: str = Form(...),
    parent_phone: str = Form(""),
    # 2026-09-23, per Shruti — "add a checkbox asking parents to receive
    # information for birthdays, latest theme launches and discounts."
    # Sent by spy-agent-registration.html as the literal string 'true'/
    # 'false' (always present — see that page's submit handler), not a
    # real HTML form checkbox post (which omits the field entirely when
    # unchecked), so it's read as a string and compared rather than typed
    # as bool.
    marketing_opt_in: str = Form("false"),
    agent_photo: Optional[UploadFile] = File(None),
):
    token = _clean(token)
    agent_name = _clean(agent_name)
    agent_dob = _clean(agent_dob)
    parent_name = _clean(parent_name)
    parent_phone = _clean(parent_phone)

    if not token:
        raise HTTPException(status_code=400, detail="Missing registration link reference — please use the link exactly as shared.")
    if not agent_name:
        raise HTTPException(status_code=400, detail="Agent Name is required.")
    if not agent_dob:
        raise HTTPException(status_code=400, detail="Agent DOB is required.")
    if not parent_name:
        raise HTTPException(status_code=400, detail="Parent Name is required.")

    row = await database.fetch_one(
        """SELECT l.child_names, l.event_date FROM spy_registration_pages srp
           JOIN leads l ON l.lead_id = srp.lead_id
           WHERE srp.share_token = :token""",
        values={"token": token},
    )
    if not row:
        raise HTTPException(status_code=404, detail="This registration link isn't valid — please check the link your host shared.")
    mission_label = _mission_label(row)

    photo_b64 = None
    photo_filename = None
    if agent_photo is not None and agent_photo.filename:
        # Read at most one byte past the limit so an oversized upload is
        # refused without ever being loaded into memory in full.
        raw = await agent_photo.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="That photo is too large — please keep it under 5MB.")
        if raw:
            sniffed = _sniff_file_type(raw)
            if sniffed is None:
                raise HTTPException(status_code=400, detail="The agent photo must be a JPG, PNG, or WEBP image.")
            photo_b64 = base64.b64encode(raw).decode("ascii")
            photo_filename = f"{agent_name or 'agent'}.{_EXT_BY_TYPE[sniffed]}"

    if not settings.SPY_SHEET_WEBHOOK_URL:
        logger.warning("SPY_SHEET_WEBHOOK_URL not set — spy agent registration not saved anywhere")
        raise HTTPException(status_code=503, detail="Registration isn't accepting submissions right now — please try again later.")

    payload = {
        "action": "spy_agent_registration",
        "event_id": token,
        "mission_label": mission_label,
        "submitted_at": datetime.utcnow().isoformat(),
        "agent_name": agent_name,
        "agent_dob": agent_dob,
        "parent_name": parent_name,
        "parent_phone": parent_phone,
        "marketing_opt_in": marketing_opt_in.strip().lower() == "true",
        "agent_photo_b64": photo_b64 or "",
        "agent_photo_filename": photo_filename or "",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(settings.SPY_SHEET_WEBHOOK_URL, json=payload)
        logger.info(f"Spy agent registration ({token}, {agent_name}): sheet append -> {r.status_code}")
        ok = False
        try:
            ok = bool(r.json().get("success"))
        except Exception:
            pass
        if not ok:
            logger.error(f"Spy agent registration ({token}, {agent_name}): sheet reported failure — {r.text[:500]}")
            raise HTTPException(status_code=502, detail="Something went wrong saving the registration — please try again.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Spy agent registration ({token}, {agent_name}): sheet append failed — {exc}")
        raise HTTPException(status_code=502, detail="Something went wrong saving the registration — please try again.")

    return {"success": True}
