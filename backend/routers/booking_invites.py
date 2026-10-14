"""
Final e-invite on a booking (2026-10-14, per Shruti).

"we'll upload the final invite on the bookings page for our record keeping.
if it's a new invite, we'll add it to our website as well. ... For spy, we
don't need to ask to reupload. we upload the same invite, just add the
checkbox so that this design can be updated on the website as well."

  * Any booking: upload / replace the final invite image (admin or sales).
  * Spy booking: no separate upload — the Spy Agent Registration invite
    (spy_registration_pages.invite_image) IS the final invite.
  * Admin only: "New design — show on the website" + a name and theme tag.
    Ticked invites appear on Build-a-Birthday's E-Invite step straight away
    (builder.html loadSiteInvites), like decor reference photos do.

  GET  /api/admin/bookings/{id}/invite           status
  GET  /api/admin/bookings/{id}/invite/image     the image (admin view)
  POST /api/admin/bookings/{id}/invite           upload (multipart: invite_image)
  POST /api/admin/bookings/{id}/invite/website   {show, name, theme}  (admin only)
  GET  /api/booking-invites/website              list for the website
  GET  /api/booking-invites/website/{id}/image   image, only while it's on the website
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str
from routers.spy_registration import MAX_FILE_BYTES, _sniff_file_type

logger = logging.getLogger(__name__)
router = APIRouter()


async def _row(lead_id: int):
    r = await database.fetch_one(
        """SELECT lead_id, (invite_image IS NOT NULL) AS has_img, invite_image_name, uploaded_by, uploaded_at,
                  show_on_website, website_name, website_theme, website_by, website_at
           FROM booking_invites WHERE lead_id = :id""", values={"id": lead_id})
    return dict(r) if r else None


async def _spy_image(lead_id: int):
    return await database.fetch_one(
        "SELECT invite_image, invite_image_type, invite_image_name FROM spy_registration_pages "
        "WHERE lead_id = :id AND invite_image IS NOT NULL", values={"id": lead_id})


async def _image(lead_id: int):
    """(bytes, type, name, source) — the booking's own upload first, else the Spy invite."""
    r = await database.fetch_one(
        "SELECT invite_image, invite_image_type, invite_image_name FROM booking_invites "
        "WHERE lead_id = :id AND invite_image IS NOT NULL", values={"id": lead_id})
    if r:
        return bytes(r["invite_image"]), r["invite_image_type"], r["invite_image_name"], "booking"
    s = await _spy_image(lead_id)
    if s:
        return bytes(s["invite_image"]), s["invite_image_type"], s["invite_image_name"], "spy"
    return None


@router.get("/admin/bookings/{lead_id}/invite")
async def invite_status(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    r = await _row(lead_id) or {}
    spy = await database.fetch_one(
        "SELECT invite_image_name FROM spy_registration_pages WHERE lead_id = :id AND invite_image IS NOT NULL",
        values={"id": lead_id})
    has_own = bool(r.get("has_img"))
    return {
        "has_invite": has_own or bool(spy),
        "source": "booking" if has_own else ("spy" if spy else None),
        "name": r.get("invite_image_name") if has_own else (spy["invite_image_name"] if spy else None),
        "uploaded_by": r.get("uploaded_by") if has_own else None,
        "uploaded_at": _to_ist_str(r.get("uploaded_at")) if has_own else None,
        "show_on_website": bool(r.get("show_on_website")),
        "website_name": r.get("website_name"),
        "website_theme": r.get("website_theme"),
        "website_by": r.get("website_by"),
        "website_at": _to_ist_str(r.get("website_at")),
    }


@router.get("/admin/bookings/{lead_id}/invite/image")
async def invite_image_admin(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    img = await _image(lead_id)
    if not img:
        raise HTTPException(status_code=404, detail="No invite uploaded yet.")
    return Response(content=img[0], media_type=img[1] or "image/jpeg")


@router.post("/admin/bookings/{lead_id}/invite")
async def upload_invite(lead_id: int, invite_image: UploadFile = File(...), changed_by: str = Form(""),
                        x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not await database.fetch_one("SELECT 1 FROM leads WHERE lead_id = :id", values={"id": lead_id}):
        raise HTTPException(status_code=404, detail="No booking found with that ID.")
    raw = await invite_image.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="That image is too large — please keep it under 5MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="No image was received — please choose a file and try again.")
    kind = _sniff_file_type(raw)
    if not kind:
        raise HTTPException(status_code=400, detail="The invite must be a JPG, PNG or WEBP image.")
    await database.execute(
        """INSERT INTO booking_invites (lead_id, invite_image, invite_image_type, invite_image_name, uploaded_by, uploaded_at)
           VALUES (:id, :img, :type, :name, :by, :at)
           ON CONFLICT (lead_id) DO UPDATE SET invite_image = EXCLUDED.invite_image,
               invite_image_type = EXCLUDED.invite_image_type, invite_image_name = EXCLUDED.invite_image_name,
               uploaded_by = EXCLUDED.uploaded_by, uploaded_at = EXCLUDED.uploaded_at""",
        values={"id": lead_id, "img": raw, "type": kind, "name": (invite_image.filename or "")[:200] or None,
                "by": (changed_by or "").strip()[:100] or None, "at": datetime.utcnow()})
    logger.info(f"Lead #{lead_id}: final invite uploaded")
    return {"success": True}


class WebsiteBody(BaseModel):
    show: bool = False
    name: Optional[str] = None
    theme: Optional[str] = None
    changed_by: Optional[str] = None


@router.post("/admin/bookings/{lead_id}/invite/website")
async def set_website(lead_id: int, body: WebsiteBody, x_admin_password: Optional[str] = Header(None)):
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Only the admin can put an invite on the website.")
    name = (body.name or "").strip()[:120]
    theme = (body.theme or "").strip().lower()[:60]
    if body.show:
        if not await _image(lead_id):
            raise HTTPException(status_code=400, detail="Upload the invite first.")
        if not name:
            raise HTTPException(status_code=400, detail="Give the design a name for the website (e.g. \"Unicorn Pastel\").")
    await database.execute(
        """INSERT INTO booking_invites (lead_id, show_on_website, website_name, website_theme, website_by, website_at)
           VALUES (:id, :show, :name, :theme, :by, :at)
           ON CONFLICT (lead_id) DO UPDATE SET show_on_website = EXCLUDED.show_on_website,
               website_name = EXCLUDED.website_name, website_theme = EXCLUDED.website_theme,
               website_by = EXCLUDED.website_by, website_at = EXCLUDED.website_at""",
        values={"id": lead_id, "show": body.show, "name": name or None, "theme": theme or None,
                "by": (body.changed_by or "").strip()[:100] or None, "at": datetime.utcnow()})
    return {"success": True}


@router.get("/booking-invites/website")
async def website_invites():
    rows = await database.fetch_all(
        "SELECT lead_id, website_name, website_theme FROM booking_invites WHERE show_on_website "
        "ORDER BY website_at DESC NULLS LAST")
    return {"items": [{"id": r["lead_id"], "name": r["website_name"], "theme": r["website_theme"] or "",
                       "image_url": f"/api/booking-invites/website/{r['lead_id']}/image"} for r in rows]}


@router.get("/booking-invites/website/{lead_id}/image")
async def website_invite_image(lead_id: int):
    r = await database.fetch_one("SELECT show_on_website FROM booking_invites WHERE lead_id = :id",
                                 values={"id": lead_id})
    img = await _image(lead_id) if r and r["show_on_website"] else None
    if not img:
        raise HTTPException(status_code=404, detail="Not on the website.")
    return Response(content=img[0], media_type=img[1] or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})
