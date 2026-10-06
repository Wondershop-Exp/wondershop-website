"""
Decor reference images — 2026-10-06, per Shruti:
"give an option to upload a reference image for the decor in the sales &
booking panels for a booking. during upload, ask if this reference image can
be displayed on the website as well. if the user checks that box, then ask
for more inputs like the theme, category (classic/premium/signature/luxury),
cost, age, gender. Use this image in the pdf and email that goes for this
lead/booking."

Storage: decor_reference_images (migration 041), image as BYTEA like the spy
invite. One image per lead is "current" (is_current) — that's the one the
quotation PDF and the booking emails show for the decor. A photo marked
show_on_website appears on Build-a-Birthday's decor step straight away
(Shruti: live immediately, no approval step), priced at its own cost.

Admin/sales (X-Admin-Password; sales allowed via security.SALES_ALLOWED):
  GET    /api/admin/decor-refs/{lead_id}            current image's details
  POST   /api/admin/decor-refs/{lead_id}            upload (multipart)
  POST   /api/admin/decor-refs/item/{id}            edit website details (JSON)
  POST   /api/admin/decor-refs/item/{id}/remove     drop from lead + website
Public (no password):
  GET    /api/decor-refs/public/img/{token}         the image (emails, website)
  GET    /api/decor-refs/public/website             items for Build-a-Birthday
"""
import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_BYTES = 8 * 1024 * 1024 - 64 * 1024   # just under security.MAX_BODY_BYTES
TIERS = ("Classic", "Premium", "Luxury", "Signature")
GENDERS = ("Girl", "Boy", "Both")
AGE_GROUPS = ("1-3", "3-5", "3-8", "6-8", "6-12", "8-12", "1-12")
# Where this API is served from — image URLs in emails / on the website
# point here (the site itself is static on GitHub Pages).
PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE", "https://wondershop-website-production.up.railway.app").rstrip("/")


def public_image_url(token: str) -> str:
    return f"{PUBLIC_API_BASE}/api/decor-refs/public/img/{token}"


def _sniff(raw: bytes) -> Optional[str]:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def _clean_meta(show: bool, theme, tier, cost, age_group, gender) -> dict:
    """Website details are required only when the photo goes on the website."""
    theme = (theme or "").strip() or None
    tier = (tier or "").strip() or None
    age_group = (age_group or "").strip() or None
    gender = (gender or "").strip() or None
    try:
        cost = None if cost in (None, "") else round(float(cost), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Cost must be a number.")
    if tier and tier not in TIERS:
        raise HTTPException(status_code=400, detail=f"Category must be one of {', '.join(TIERS)}.")
    if gender and gender not in GENDERS:
        raise HTTPException(status_code=400, detail=f"Gender must be one of {', '.join(GENDERS)}.")
    if age_group and age_group not in AGE_GROUPS:
        raise HTTPException(status_code=400, detail=f"Age must be one of {', '.join(AGE_GROUPS)}.")
    if show:
        missing = [n for n, v in (("theme", theme), ("category", tier), ("cost", cost),
                                  ("age", age_group), ("gender", gender)) if v in (None, "")]
        if missing:
            raise HTTPException(status_code=400,
                                detail="To show it on the website, please fill in: " + ", ".join(missing) + ".")
        if cost <= 0:
            raise HTTPException(status_code=400, detail="Cost must be more than ₹0.")
    return {"theme": theme, "tier": tier, "cost": cost, "age_group": age_group, "gender": gender}


def _row_out(r) -> dict:
    return {
        "id": r["id"], "lead_id": r["lead_id"], "image_url": public_image_url(r["public_token"]),
        "image_name": r["image_name"], "show_on_website": bool(r["show_on_website"]),
        "theme": r["theme"], "tier": r["tier"],
        "cost": float(r["cost"]) if r["cost"] is not None else None,
        "age_group": r["age_group"], "gender": r["gender"],
        "uploaded_by": r["uploaded_by"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


_META_COLS = ("id, lead_id, public_token, image_name, show_on_website, theme, tier, cost, "
              "age_group, gender, uploaded_by, created_at")


async def current_for_lead(lead_id: int, with_image: bool = False) -> Optional[dict]:
    """The lead's current reference image (dict incl. image_url; plus
    "image"/"image_type" bytes when with_image), or None. Never raises —
    callers are PDFs/emails, which go on without it (e.g. before migration 041)."""
    try:
        cols = _META_COLS + (", image, image_type" if with_image else "")
        r = await database.fetch_one(
            f"SELECT {cols} FROM decor_reference_images WHERE lead_id = :id AND is_current "
            "ORDER BY created_at DESC LIMIT 1", values={"id": lead_id})
    except Exception:
        logger.exception(f"Lead #{lead_id}: couldn't read the decor reference image (run migration 041?)")
        return None
    if not r:
        return None
    out = _row_out(r)
    if with_image:
        out["image"] = bytes(r["image"])
        out["image_type"] = r["image_type"]
    return out


async def item_with_image(item_id: int) -> Optional[dict]:
    """A website decor design (Build-a-Birthday id 'ref-<id>') with its image
    bytes — for the PDF of a booking that picked it on the website."""
    try:
        r = await database.fetch_one(
            f"SELECT {_META_COLS}, image, image_type FROM decor_reference_images WHERE id = :id",
            values={"id": item_id})
    except Exception:
        return None
    if not r:
        return None
    out = _row_out(r)
    out["image"] = bytes(r["image"])
    return out


@router.get("/admin/decor-refs/{lead_id}")
async def get_ref(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    from catalogue_data import THEMES, THEME_PREFERENCE_NAMES
    themes = sorted({t["n"] for t in THEMES} | set(THEME_PREFERENCE_NAMES or []))
    return {"current": await current_for_lead(lead_id), "tiers": TIERS, "genders": GENDERS,
            "age_groups": AGE_GROUPS, "themes": themes}


@router.post("/admin/decor-refs/{lead_id}")
async def upload_ref(
    lead_id: int,
    image: UploadFile = File(...),
    show_on_website: bool = Form(False),
    theme: Optional[str] = Form(None),
    tier: Optional[str] = Form(None),
    cost: Optional[str] = Form(None),
    age_group: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    uploaded_by: Optional[str] = Form(None),
    x_admin_password: Optional[str] = Header(None),
):
    _require_admin(x_admin_password)
    if not await database.fetch_one("SELECT lead_id FROM leads WHERE lead_id = :id", values={"id": lead_id}):
        raise HTTPException(status_code=404, detail="No lead/booking with that number.")
    raw = await image.read(MAX_FILE_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="No image was received — please choose a file and try again.")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="That image is too large — please keep it under 7 MB.")
    kind = _sniff(raw)
    if not kind:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WEBP image.")
    meta = _clean_meta(show_on_website, theme, tier, cost, age_group, gender)
    async with database.transaction():
        # The new photo replaces the lead's current one for its quotation /
        # emails; an older photo already on the website stays there.
        await database.execute(
            "UPDATE decor_reference_images SET is_current = FALSE, updated_at = NOW() "
            "WHERE lead_id = :id AND is_current", values={"id": lead_id})
        new_row = await database.fetch_one(
            """INSERT INTO decor_reference_images
                 (lead_id, public_token, image, image_type, image_name, show_on_website,
                  theme, tier, cost, age_group, gender, uploaded_by)
               VALUES (:lead_id, :tok, :img, :type, :name, :show,
                       :theme, :tier, :cost, :age_group, :gender, :by)
               RETURNING id""",
            values={"lead_id": lead_id, "tok": secrets.token_urlsafe(18), "img": raw, "type": kind,
                    "name": (image.filename or "")[:200] or None, "show": bool(show_on_website),
                    "by": (uploaded_by or "").strip()[:80] or None, **meta})
        new_id = new_row["id"]
    logger.info(f"Lead #{lead_id}: decor reference image #{new_id} uploaded (website={bool(show_on_website)})")
    return {"success": True, "current": await current_for_lead(lead_id)}


class RefEdit(BaseModel):
    show_on_website: bool = False
    theme: Optional[str] = None
    tier: Optional[str] = None
    cost: Optional[float] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None


@router.post("/admin/decor-refs/item/{item_id}")
async def edit_ref(item_id: int, body: RefEdit, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    meta = _clean_meta(body.show_on_website, body.theme, body.tier, body.cost, body.age_group, body.gender)
    r = await database.fetch_one(
        """UPDATE decor_reference_images
           SET show_on_website = :show, theme = :theme, tier = :tier, cost = :cost,
               age_group = :age_group, gender = :gender, updated_at = NOW()
           WHERE id = :id RETURNING lead_id""",
        values={"id": item_id, "show": body.show_on_website, **meta})
    if not r:
        raise HTTPException(status_code=404, detail="That image no longer exists.")
    return {"success": True, "current": await current_for_lead(r["lead_id"]) if r["lead_id"] else None}


@router.post("/admin/decor-refs/item/{item_id}/remove")
async def remove_ref(item_id: int, x_admin_password: Optional[str] = Header(None)):
    """Takes the photo off its lead (quotation/emails) AND off the website.
    The row is kept (not deleted) so an email already sent still shows it."""
    _require_admin(x_admin_password)
    r = await database.fetch_one(
        "UPDATE decor_reference_images SET is_current = FALSE, show_on_website = FALSE, updated_at = NOW() "
        "WHERE id = :id RETURNING lead_id", values={"id": item_id})
    if not r:
        raise HTTPException(status_code=404, detail="That image no longer exists.")
    return {"success": True}


@router.get("/decor-refs/public/img/{token}")
async def public_image(token: str):
    r = await database.fetch_one(
        "SELECT image, image_type FROM decor_reference_images WHERE public_token = :t", values={"t": token})
    if not r:
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(content=bytes(r["image"]), media_type=r["image_type"],
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/decor-refs/public/website")
async def public_website_items():
    """Photos marked 'show on website' — Build-a-Birthday adds them to its
    decor step. Empty list (not an error) before migration 041."""
    try:
        rows = await database.fetch_all(
            f"SELECT {_META_COLS} FROM decor_reference_images WHERE show_on_website "
            "AND theme IS NOT NULL AND tier IS NOT NULL AND cost IS NOT NULL ORDER BY created_at DESC")
    except Exception:
        logger.exception("decor-refs website list failed (run migration 041?)")
        return {"items": []}
    items = []
    for r in rows:
        o = _row_out(r)
        items.append({k: o[k] for k in ("id", "image_url", "theme", "tier", "cost", "age_group", "gender")})
    return {"items": items}
