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
from pydantic import BaseModel

from database import database
from config import settings
from routers.admin import _require_admin, _to_ist_str

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


def _clean_time(v: Optional[str]) -> Optional[str]:
    """Validates + normalises a 'HH:MM' 24h time string, same convention
    as leads.event_time. Blank/None -> None (nothing on file). Anything
    else that doesn't parse raises a 400 rather than silently storing
    garbage, since these times feed a parent-facing display."""
    v = (v or "").strip()
    if not v:
        return None
    try:
        hh, mm = (int(x) for x in v.split(":")[:2])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
        return f"{hh:02d}:{mm:02d}"
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Time must be in HH:MM 24-hour format.")


def _mission_label(lead) -> str:
    """Used both as the public page's title and as the worksheet tab name
    in the dedicated Spy sheet. Deliberately just child name + event date
    — always available and accurate, unlike an invented ordinal/quest
    name that would need typing in by hand somewhere."""
    child = _clean(lead.get("child_names")) or "Guest"
    date_str = _format_date(lead.get("event_date"))
    return f"{child} — {date_str}" if date_str else child


def _ordinal(n_str: Optional[str]) -> str:
    """'10' -> '10th'. child_ages/child_genders are comma-joined per-child
    (builder.html supports multiple kids on one booking) — the public
    Spy mission page is framed around a single agent, so this and
    _pronoun() below both just take the first child (2026-09-23, per
    Shruti — restoring the "On Her 10th Birthday Quest" style line the
    old hardcoded page had, now driven by the booking's real data instead
    of a value someone had to type in by hand per party)."""
    first = (n_str or "").split(",")[0].strip()
    if not first.isdigit():
        return ""
    n = int(first)
    if 10 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _pronoun(genders_str: Optional[str]) -> str:
    first = (genders_str or "").split(",")[0].strip().lower()
    if first == "boy":
        return "his"
    if first == "girl":
        return "her"
    return "their"


# ─── ADMIN: upload/replace the invite, check current status ───────────────
# Mirrors admin.html's existing X-Admin-Password pattern (see
# routers/admin.py's _require_admin, reused here rather than duplicated).

@router.get("/admin/{lead_id}")
async def admin_get_status(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one(
        """SELECT share_token, (invite_image IS NOT NULL) AS has_invite,
                  invite_image_name, updated_on,
                  drop_off_time, pick_up_time, show_pickup_drop,
                  pickup_drop_source, pickup_drop_updated_at
           FROM spy_registration_pages WHERE lead_id = :lead_id""",
        values={"lead_id": lead_id},
    )
    if not row:
        return {"exists": False, "show_pickup_drop": True}
    return {
        "exists": True,
        "share_token": row["share_token"],
        "share_url": f"/spy-agent-registration.html?t={row['share_token']}",
        "has_invite": bool(row["has_invite"]),
        "invite_image_name": row["invite_image_name"],
        "drop_off_time": row["drop_off_time"],
        "pick_up_time": row["pick_up_time"],
        "show_pickup_drop": row["show_pickup_drop"] if row["show_pickup_drop"] is not None else True,
        "pickup_drop_source": row["pickup_drop_source"],
        "pickup_drop_updated_at": _to_ist_str(row["pickup_drop_updated_at"]),
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


class PickupDropUpdate(BaseModel):
    drop_off_time: Optional[str] = None   # 'HH:MM' 24h, or '' / None to clear
    pick_up_time: Optional[str] = None
    show_pickup_drop: bool = True


@router.post("/admin/{lead_id}/pickup-drop")
async def admin_set_pickup_drop(
    lead_id: int,
    body: PickupDropUpdate,
    x_admin_password: Optional[str] = Header(None),
):
    """Admin sets (or clears) the official drop-off/pick-up time for a
    party, and whether to show that block on the public registration page
    at all. Creates the spy_registration_pages row if this booking hasn't
    had an invite uploaded yet -- admin shouldn't have to upload an invite
    first just to set pickup/drop times."""
    _require_admin(x_admin_password)

    lead = await database.fetch_one("SELECT lead_id FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="No booking found with that lead ID.")

    drop_off = _clean_time(body.drop_off_time)
    pick_up = _clean_time(body.pick_up_time)
    now = datetime.utcnow()

    existing = await database.fetch_one(
        "SELECT share_token FROM spy_registration_pages WHERE lead_id = :lead_id",
        values={"lead_id": lead_id},
    )
    if existing:
        token = existing["share_token"]
        await database.execute(
            """UPDATE spy_registration_pages
               SET drop_off_time = :drop_off, pick_up_time = :pick_up,
                   show_pickup_drop = :show, pickup_drop_source = 'admin',
                   pickup_drop_updated_at = :now
               WHERE lead_id = :lead_id""",
            values={"drop_off": drop_off, "pick_up": pick_up, "show": body.show_pickup_drop, "now": now, "lead_id": lead_id},
        )
    else:
        token = secrets.token_urlsafe(18)
        await database.execute(
            """INSERT INTO spy_registration_pages
                   (lead_id, share_token, drop_off_time, pick_up_time, show_pickup_drop,
                    pickup_drop_source, pickup_drop_updated_at)
               VALUES (:lead_id, :token, :drop_off, :pick_up, :show, 'admin', :now)""",
            values={
                "lead_id": lead_id, "token": token, "drop_off": drop_off, "pick_up": pick_up,
                "show": body.show_pickup_drop, "now": now,
            },
        )

    return {
        "success": True,
        "share_token": token,
        "share_url": f"/spy-agent-registration.html?t={token}",
        "drop_off_time": drop_off,
        "pick_up_time": pick_up,
        "show_pickup_drop": body.show_pickup_drop,
    }


# ─── PUBLIC: party info, invite image, and the registration form itself ───

@router.get("/party/{token}")
async def get_party_info(token: str):
    row = await database.fetch_one(
        """SELECT (srp.invite_image IS NOT NULL) AS has_invite,
                  srp.drop_off_time, srp.pick_up_time, srp.show_pickup_drop,
                  l.child_names, l.child_ages, l.child_genders,
                  l.event_date, l.event_time, l.venue,
                  l.venue_contact_name, l.venue_contact_phone
           FROM spy_registration_pages srp
           JOIN leads l ON l.lead_id = srp.lead_id
           WHERE srp.share_token = :token""",
        values={"token": token},
    )
    if not row:
        raise HTTPException(status_code=404, detail="This registration link isn't valid — please check the link your host shared.")
    # 2026-09-23, per Shruti ("link is not working") — databases' Record
    # type (backend/routers/admin.py already works around this the same
    # way, via dict(lead_row)) is a Sequence, not a Mapping, so it has no
    # .get() — every .get() call below was raising AttributeError and
    # turning into a 500/503 on every single request, which is why this
    # endpoint (never actually exercised until the frontend was wired up
    # to call it) silently never worked. Bracket access (row["x"]) already
    # worked fine elsewhere in this file; converting to a plain dict here
    # makes .get() (with its "or default" fallback pattern) safe too.
    row = dict(row)

    return {
        "child_name": _clean(row.get("child_names")) or "Agent",
        "mission_label": _mission_label(row),
        # 2026-09-23, per Shruti — "on her 10th birthday quest" style
        # phrasing, restored from the booking's own real data (age/gender)
        # rather than a value someone had to hand-type per party. Blank
        # when the age isn't on file — the frontend falls back to a
        # generic "on their birthday quest" line in that case.
        "age_ordinal": _ordinal(row.get("child_ages")),
        "child_pronoun": _pronoun(row.get("child_genders")),
        "event_date_display": _format_date(row.get("event_date")),
        "event_time_display": _format_time(row.get("event_time")),
        "venue": _clean(row.get("venue")),
        "contact_name": _clean(row.get("venue_contact_name")),
        "contact_phone": _clean(row.get("venue_contact_phone")),
        "has_invite": bool(row.get("has_invite")),
        "invite_image_url": f"/api/spy-registration/invite-image/{token}" if row.get("has_invite") else None,
        # 2026-09-23, per Shruti — drop-off/pick-up times, shown only if
        # admin hasn't hidden the block; when admin hasn't set them yet,
        # the page itself asks the parent to confirm what they were told
        # (see /confirm-pickup-drop below), which becomes the official
        # time -- needs_confirmation covers "neither set" as well as
        # "only one of the two set" so the prompt always collects both.
        "show_pickup_drop": row.get("show_pickup_drop") if row.get("show_pickup_drop") is not None else True,
        # Raw 'HH:MM' alongside the display string so the frontend can
        # prefill an <input type="time"> in the confirm prompt when only
        # ONE of the two is set -- _display alone (e.g. "4:00 PM") can't
        # be fed back into a time input.
        "drop_off_time": row.get("drop_off_time"),
        "pick_up_time": row.get("pick_up_time"),
        "drop_off_time_display": _format_time(row.get("drop_off_time")) or None,
        "pick_up_time_display": _format_time(row.get("pick_up_time")) or None,
        "pickup_drop_needs_confirmation": not (row.get("drop_off_time") and row.get("pick_up_time")),
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
    # See get_party_info's comment above — _mission_label() calls .get() on
    # this row, which the raw databases Record doesn't support.
    mission_label = _mission_label(dict(row))

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
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
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


class ConfirmPickupDropRequest(BaseModel):
    token: str
    drop_off_time: str
    pick_up_time: str


@router.post("/confirm-pickup-drop")
async def confirm_pickup_drop(body: ConfirmPickupDropRequest):
    """A parent confirming the drop-off/pick-up time on the public page,
    shown whenever admin hasn't set one yet (get_party_info's
    pickup_drop_needs_confirmation). Their answer BECOMES the official
    time (2026-09-23, per Shruti — "ask the user to confirm the actual
    drop and pickup time and update admin") and is logged to
    booking_change_log so admin.html's Modification Trail shows it came
    from the parent, not the team."""
    token = _clean(body.token)
    if not token:
        raise HTTPException(status_code=400, detail="Missing registration link reference — please use the link exactly as shared.")
    drop_off = _clean_time(body.drop_off_time)
    pick_up = _clean_time(body.pick_up_time)
    if not drop_off or not pick_up:
        raise HTTPException(status_code=400, detail="Please provide both the drop-off and pick-up time.")

    row = await database.fetch_one(
        "SELECT lead_id, drop_off_time, pick_up_time FROM spy_registration_pages WHERE share_token = :token",
        values={"token": token},
    )
    if not row:
        raise HTTPException(status_code=404, detail="This registration link isn't valid — please check the link your host shared.")

    now = datetime.utcnow()
    await database.execute(
        """UPDATE spy_registration_pages
           SET drop_off_time = :drop_off, pick_up_time = :pick_up,
               pickup_drop_source = 'parent', pickup_drop_updated_at = :now
           WHERE share_token = :token""",
        values={"drop_off": drop_off, "pick_up": pick_up, "now": now, "token": token},
    )

    old_display = (
        f"Drop off {_format_time(row['drop_off_time'])} / Pick up {_format_time(row['pick_up_time'])}"
        if row["drop_off_time"] or row["pick_up_time"] else None
    )
    await database.execute(
        """INSERT INTO booking_change_log
               (lead_id, field_key, field_label, change_type, old_value, new_value, changed_by, changed_at)
           VALUES (:lead_id, 'spy_pickup_drop', 'Drop-off / Pick-up Time', 'confirmed_by_parent', :old_v, :new_v, 'Parent (registration page)', :now)""",
        values={
            "lead_id": row["lead_id"],
            "old_v": old_display,
            "new_v": f"Drop off {_format_time(drop_off)} / Pick up {_format_time(pick_up)}",
            "now": now,
        },
    )

    logger.info(f"Spy pickup/drop confirmed by parent for lead #{row['lead_id']} ({token}): drop {drop_off}, pickup {pick_up}")
    return {
        "success": True,
        "drop_off_time_display": _format_time(drop_off),
        "pick_up_time_display": _format_time(pick_up),
    }
