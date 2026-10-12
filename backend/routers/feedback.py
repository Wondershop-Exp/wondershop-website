"""
Post-event feedback — 2026-10-12, per Shruti:
"let's also work on feedback form for our events ... overall rating, rating
for host(s), volunteers, activities, decor (if applicable), food (if
applicable), cake (if applicable), music, mascot, etc., any remarks/inputs/
feedback. also, would like a way to get google review from this page itself
... make this phone friendly, so that we can send a whatsapp and mail both."

One feedback link per booking (table party_feedback, migration 048). The
team creates it from the booking page — the categories to ask about come
pre-ticked from what was booked and can be changed — then sends it by email
(from here) and/or WhatsApp (the booking page opens WhatsApp with the
message filled in). The client fills feedback.html?t=<token> on their phone.

Google reviews can't be posted on a customer's behalf from our page (Google
only takes reviews from the reviewer's own Google account), so after they
submit, the page copies their comment and opens our Google review box for
them to paste and post — offered to every customer, whatever their rating
(Google doesn't allow asking only happy customers for reviews).

Admin (X-Admin-Password):
  GET  /api/admin/feedback/{lead_id}             link, categories, status, answers
  POST /api/admin/feedback/{lead_id}             create / update the link's categories
  POST /api/admin/feedback/{lead_id}/email       send the feedback email
  POST /api/admin/feedback/{lead_id}/whatsapp    note that it was sent on WhatsApp
Public:
  GET  /api/feedback/{token}                     what the form needs
  POST /api/feedback/{token}                     submit (re-submitting updates it)
  POST /api/feedback/{token}/google              they tapped "post on Google"
"""
import json
import logging
import re
import secrets
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import settings
from database import database
from routers.admin import _require_admin, _to_ist_str

from catalogue_data import greeting_name
logger = logging.getLogger(__name__)
router = APIRouter()

SITE_BASE_URL = "https://www.wondershopexperiences.com"

# Everything the form can ask about, in the order shown.
CATEGORIES = [
    ("host", "Host"),
    ("volunteers", "Volunteers & team"),
    ("activities", "Activities"),
    ("decor", "Decor"),
    ("food", "Food"),
    ("cake", "Cake"),
    ("music", "Music"),
    ("mascot", "Mascot"),
    ("photography", "Photography"),
    ("return_gifts", "Return gifts"),
]
CAT_KEYS = [k for k, _ in CATEGORIES]
FOOD_WORDS = ("popcorn", "cotton candy", "fondue", "food", "snack", "stall", "chaat", "pizza", "ice cream")


def _j(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def feedback_url(token: str) -> str:
    return f"{SITE_BASE_URL}/feedback.html?t={token}"


async def _defaults(lead_id: int, pw: Optional[str]) -> dict:
    """Categories pre-ticked from what the booking has, plus host name(s)."""
    from routers.admin import get_booking_detail
    d = await get_booking_detail(lead_id, pw)
    f = {x["field_key"]: x for s in d.get("sections") or [] for x in s.get("fields") or []}

    def val(k):
        x = f.get(k) or {}
        return "" if x.get("removed") else str(x.get("customer_choice") or "").strip()

    acts = val("svc_activities")
    customs = " ".join(t.get("name") or "" for t in d.get("to_be_confirmed") or [] if t.get("kind") == "custom")
    everything = " ".join([acts, customs, val("activities_notes"), val("notes_special_instructions")]).lower()
    cats = ["volunteers"]
    if val("svc_host") or "host" in everything:
        cats.append("host")
    if acts or customs:
        cats.append("activities")
    if val("svc_decor") and val("svc_decor").lower() not in ("no selection", "none"):
        cats.append("decor")
    if any(w in everything for w in FOOD_WORDS):
        cats.append("food")
    if val("svc_cake"):
        cats.append("cake")
    if val("svc_dj") and val("svc_dj").lower() not in ("no selection", "none"):
        cats.append("music")
    if "mascot" in everything:
        cats.append("mascot")
    if val("svc_photo") and val("svc_photo").lower() not in ("no selection", "none"):
        cats.append("photography")
    if val("svc_gifts"):
        cats.append("return_gifts")
    # Host name(s): the Event Team card's Host rows first, else the Host
    # row's assigned partner on the booking.
    from routers.event_team import host_names as _team_hosts
    host_names = (await _team_hosts(lead_id)) or ((f.get("svc_host") or {}).get("assigned_value") or "").strip() or None
    return {"categories": [k for k in CAT_KEYS if k in cats], "host_names": host_names}


def _row_out(r) -> dict:
    if not r:
        return {"exists": False}
    r = dict(r)
    return {
        "exists": True, "token": r["token"], "url": feedback_url(r["token"]),
        "categories": _j(r["categories"]) or [], "host_names": r["host_names"],
        "created_by": r["created_by"], "created_at": _to_ist_str(r["created_at"]),
        "emailed_at": _to_ist_str(r["emailed_at"]), "whatsapp_at": _to_ist_str(r["whatsapp_at"]),
        "opened_at": _to_ist_str(r["opened_at"]), "submitted_at": _to_ist_str(r["submitted_at"]),
        "google_clicked_at": _to_ist_str(r["google_clicked_at"]),
        "overall": r["overall"], "ratings": _j(r["ratings"]) or {},
        "remarks": r["remarks"], "respondent": r["respondent"],
        "category_remarks": _j(r.get("category_remarks")) or {},
    }


async def _lead(lead_id: int) -> dict:
    r = await database.fetch_one(
        "SELECT lead_id, is_booking, parent_name, email, phone, child_names, event_date FROM leads WHERE lead_id = :id",
        values={"id": lead_id})
    if not r:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return dict(r)


def _first(s) -> str:
    return (str(s or "").split(",")[0]).strip()


@router.get("/admin/feedback/{lead_id}")
async def admin_get_feedback(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    try:
        row = await database.fetch_one("SELECT * FROM party_feedback WHERE lead_id = :id", values={"id": lead_id})
    except Exception:
        logger.exception("party_feedback read failed (run migration 048?)")
        raise HTTPException(status_code=500, detail="Feedback isn't set up yet — the server needs a restart to add its table.")
    out = _row_out(row)
    defaults = await _defaults(lead_id, x_admin_password)
    out.update({
        "all_categories": [{"key": k, "label": l} for k, l in CATEGORIES],
        "default_categories": defaults["categories"],
        "default_host_names": defaults["host_names"],
        "client_name": lead["parent_name"], "client_first_name": greeting_name(lead["parent_name"]) if lead["parent_name"] else "", "child_name": _first(lead["child_names"]),
        "phone": lead["phone"], "email": lead["email"],
    })
    return out


class FeedbackSetup(BaseModel):
    categories: List[str] = []
    host_names: Optional[str] = None
    changed_by: str = ""


@router.post("/admin/feedback/{lead_id}")
async def admin_setup_feedback(lead_id: int, body: FeedbackSetup, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    if not lead["is_booking"]:
        raise HTTPException(status_code=400, detail="Feedback links are for confirmed bookings only.")
    cats = [k for k in CAT_KEYS if k in set(body.categories or [])]
    hosts = (body.host_names or "").strip()[:200] or None
    row = await database.fetch_one("SELECT id FROM party_feedback WHERE lead_id = :id", values={"id": lead_id})
    if row:
        await database.execute(
            "UPDATE party_feedback SET categories = CAST(:c AS JSONB), host_names = :h WHERE lead_id = :id",
            values={"c": json.dumps(cats), "h": hosts, "id": lead_id})
    else:
        await database.execute(
            """INSERT INTO party_feedback (lead_id, token, categories, host_names, created_by)
               VALUES (:id, :t, CAST(:c AS JSONB), :h, :by)""",
            values={"id": lead_id, "t": secrets.token_urlsafe(12), "c": json.dumps(cats), "h": hosts,
                    "by": (body.changed_by or "").strip()[:80] or None})
    return await admin_get_feedback(lead_id, x_admin_password)


class ChangedBy(BaseModel):
    changed_by: str = ""


def _email_html(first_name: str, child: str, url: str) -> str:
    from routers.leads import MASCOT_URL, BRAND_PURPLE
    hi = f"Hi {first_name}," if first_name else "Hi,"
    party = f"{child}'s party" if child else "your party"
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#F5F0FF;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F0FF;padding:28px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(45,33,64,.08)">
<tr><td style="background:linear-gradient(135deg,#E65A96 0%,{BRAND_PURPLE} 100%);padding:26px;text-align:center">
<img src="{MASCOT_URL}" width="150" alt="" style="display:block;margin:0 auto 10px;border-radius:18px;background:#fff;padding:8px 12px">
<div style="font-family:Georgia,serif;font-size:21px;font-weight:700;color:#fff">How was {party}?</div></td></tr>
<tr><td style="padding:24px 26px;font-size:15px;line-height:1.6;color:#2D2140">
{hi}<br><br>Thank you for celebrating with Wondershop Experiences! We'd love to hear how it went —
it takes about a minute, and it helps us make every party better.
<div style="text-align:center;margin:24px 0 8px">
<a href="{url}" style="display:inline-block;background:#E65A96;color:#fff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 28px;border-radius:999px">⭐ Rate your party</a></div>
<div style="text-align:center;font-size:12px;color:#8B7FA0">Or open: <a href="{url}" style="color:{BRAND_PURPLE}">{url}</a></div>
</td></tr>
<tr><td style="padding:0 26px 24px;font-size:12.5px;color:#8B7FA0;text-align:center;border-top:1px solid #F0E9FA">
<br>Questions? +91 90044 35362 · +91 97422 40477</td></tr></table>
</td></tr></table></body></html>"""


@router.post("/admin/feedback/{lead_id}/email")
async def admin_email_feedback(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    if not lead["email"]:
        raise HTTPException(status_code=400, detail="This booking has no email on file.")
    row = await database.fetch_one("SELECT token FROM party_feedback WHERE lead_id = :id", values={"id": lead_id})
    if not row:
        raise HTTPException(status_code=400, detail="Create the feedback link first.")
    from routers.leads import _gmail_send
    from catalogue_data import greeting_name
    url = feedback_url(row["token"])
    child = _first(lead["child_names"])
    first = greeting_name(lead["parent_name"]) if lead["parent_name"] else ""
    subject = f"How was {child}'s party? 💜" if child else "How was your party? 💜"
    text = (f"Hi {first},\n\n" if first else "Hi,\n\n") + \
        "Thank you for celebrating with Wondershop Experiences! We'd love to hear how it went — it takes about a minute:\n" \
        f"{url}\n\nTeam Wondershop Experiences\n+91 90044 35362 · +91 97422 40477"
    try:
        await _gmail_send(lead["email"], subject, text, _email_html(first, child, url))
    except Exception as e:
        logger.exception(f"Lead #{lead_id}: feedback email failed")
        raise HTTPException(status_code=502, detail=f"Couldn't send the email: {e}")
    await database.execute("UPDATE party_feedback SET emailed_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True, "sent_to": lead["email"]}


@router.post("/admin/feedback/{lead_id}/whatsapp")
async def admin_whatsapp_feedback(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("UPDATE party_feedback SET whatsapp_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True}


# ─── public ────────────────────────────────────────────────────────────────

async def _by_token(token: str):
    try:
        row = await database.fetch_one("SELECT * FROM party_feedback WHERE token = :t", values={"t": token})
    except Exception:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="This feedback link isn't valid — please check the link we sent.")
    return dict(row)


@router.get("/feedback/{token}")
async def public_feedback(token: str):
    row = await _by_token(token)
    lead = await _lead(row["lead_id"])
    if not row["opened_at"]:
        await database.execute("UPDATE party_feedback SET opened_at = NOW() WHERE id = :id", values={"id": row["id"]})
    labels = dict(CATEGORIES)
    hosts = row["host_names"]
    cats = []
    for k in _j(row["categories"]) or []:
        if k in labels:
            lbl = labels[k]
            if k == "host":
                lbl = "Host" + ("s" if hosts and ("," in hosts or "&" in hosts or " and " in hosts) else "") + (f" ({hosts})" if hosts else "")
            cats.append({"key": k, "label": lbl})
    from catalogue_data import greeting_name
    return {
        "child_name": _first(lead["child_names"]),
        "client_name": (lead["parent_name"] or "").strip(),
        "client_first_name": greeting_name(lead["parent_name"]) if lead["parent_name"] else "",
        "event_date": lead["event_date"].strftime("%d %b %Y").lstrip("0") if lead["event_date"] else None,
        "categories": cats,
        "submitted": bool(row["submitted_at"]),
        "overall": row["overall"], "ratings": _j(row["ratings"]) or {}, "remarks": row["remarks"],
        "category_remarks": _j(dict(row).get("category_remarks")) or {},
        "google_review_url": (settings.GOOGLE_REVIEW_URL or "").strip() or None,
    }


class FeedbackIn(BaseModel):
    overall: int
    ratings: Dict[str, Optional[int]] = {}
    remarks: Optional[str] = None
    category_remarks: Dict[str, Optional[str]] = {}
    respondent: Optional[str] = None


@router.post("/feedback/{token}")
async def submit_feedback(token: str, body: FeedbackIn):
    row = await _by_token(token)
    if not (1 <= int(body.overall) <= 5):
        raise HTTPException(status_code=400, detail="Please give an overall rating (1 to 5 stars).")
    allowed = set(_j(row["categories"]) or [])
    ratings = {k: int(v) for k, v in (body.ratings or {}).items() if k in allowed and v and 1 <= int(v) <= 5}
    remarks = (body.remarks or "").strip()[:3000] or None
    cat_rm = {k: v.strip()[:1000] for k, v in (body.category_remarks or {}).items() if k in allowed and v and v.strip()}
    await database.execute(
        """UPDATE party_feedback SET overall = :o, ratings = CAST(:r AS JSONB), remarks = :rm,
                  category_remarks = CAST(:crm AS JSONB), respondent = :who, submitted_at = NOW() WHERE id = :id""",
        values={"o": int(body.overall), "r": json.dumps(ratings), "rm": remarks, "crm": json.dumps(cat_rm),
                "who": (body.respondent or "").strip()[:80] or None, "id": row["id"]})
    logger.info(f"Lead #{row['lead_id']}: feedback received ({body.overall}★)")
    return {"success": True, "google_review_url": (settings.GOOGLE_REVIEW_URL or "").strip() or None}


@router.post("/feedback/{token}/google")
async def feedback_google_clicked(token: str):
    row = await _by_token(token)
    await database.execute("UPDATE party_feedback SET google_clicked_at = NOW() WHERE id = :id", values={"id": row["id"]})
    return {"success": True}
