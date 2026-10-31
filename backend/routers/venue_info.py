"""
Venue & society information form — 2026-10-31, per Shruti (replaces the
Google Form "Venue & Society Information Form"):

  "this should be asked at the time of booking or can be shared separately
  to the customer - whether it's website booking or backend booking ... like
  ikea, we would like this info to plan our events better. T&C would be the
  latest T&C updated on the website. also give an option to upload venue pics
  and videos and option to add tags like decor placement, DJ placement,
  return gift placement ... booking details should be shown on this form."

One link per booking (table venue_info, migration 080): venue.html?t=<token>.
Answers save as the customer goes (nothing is required to save); the page and
the bookings panel show what's still missing. Photos are shrunk in the
browser before upload; videos are capped at 30 MB each, 3 per booking. Files
live in Postgres (venue_media.data, BYTEA) like the other uploads.

Created automatically when a website booking is placed (the link is shown on
the order confirmation page and in the confirmation email) or from the
booking page (email / WhatsApp buttons) for bookings made in the panel.

Public:
  GET    /api/venue-info/{token}                      form data + booking details
  POST   /api/venue-info/{token}                      save answers (+ accept T&C / submit)
  POST   /api/venue-info/{token}/media                upload one photo / video (multipart)
  GET    /api/venue-info/{token}/media/{id}           the file (Range supported, for video)
  POST   /api/venue-info/{token}/media/{id}           change its tags / caption
  DELETE /api/venue-info/{token}/media/{id}           remove it
Admin (X-Admin-Password; sales login allowed — see security.py):
  GET    /api/admin/bookings/{lead_id}/venue-info               link, status, answers, media
  GET    /api/admin/bookings/{lead_id}/venue-info/media/{id}    a file
  POST   /api/admin/bookings/{lead_id}/venue-info/email         email the link
  POST   /api/admin/bookings/{lead_id}/venue-info/whatsapp      note it was sent on WhatsApp
"""
import json
import logging
import re
import secrets
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str
from catalogue_data import greeting_name

logger = logging.getLogger(__name__)
router = APIRouter()

SITE_BASE_URL = "https://www.wondershopexperiences.com"
TNC_URL = SITE_BASE_URL + "/terms.html"

MAX_IMAGE_BYTES = 10 * 1024 * 1024    # the page shrinks photos to ~1 MB before upload
MAX_VIDEO_BYTES = 30 * 1024 * 1024
MAX_IMAGES = 20
MAX_VIDEOS = 3

# (key, label, type, options [(value, label)], required, follow-up)
# follow-up = (key, label, show when the answer is one of these values)
SECTIONS = [
    ("Timings", [
        ("setup_from", "Our team can enter the venue for setup from", "time", None, True, None),
        ("clear_by", "The venue must be cleared by", "time", None, True, None),
        ("other_event", "Is there another event at the venue that day?", "chips",
         [("none", "No"), ("before", "Before ours"), ("after", "After ours"), ("both", "Both")], True,
         ("other_event_note", "Its timing (e.g. till 3 PM)", ["before", "after", "both"])),
    ]),
    ("Getting our things in", [
        ("floor", "Which floor is the party on?", "chips",
         [("ground", "Ground"), ("1-3", "1–3"), ("4-10", "4–10"), ("11+", "11+"), ("terrace", "Terrace")], True, None),
        ("vehicle", "Can our vehicle (car / tempo) reach the building?", "chips",
         [("yes", "Yes, till the entrance"), ("gate", "Only till the gate"), ("unsure", "Not sure")], True, None),
        ("parking", "Parking for our team", "chips",
         [("yes", "Yes"), ("paid", "Paid / outside"), ("no", "No")], True, None),
        ("unloading", "Distance from the unloading point to the venue", "chips",
         [("lt20", "Under 20 m"), ("20-50", "20–50 m"), ("gt50", "50 m+"), ("unsure", "Not sure")], True, None),
        ("route", "How do materials reach the venue?", "chips",
         [("service_lift", "Service lift"), ("passenger_lift", "Passenger lift"), ("stairs", "Stairs"),
          ("none", "No lift needed"), ("unsure", "Not sure")], True, None),
        ("lift_limits", "Any time limits for the lift or entry?", "chips",
         [("no", "No"), ("yes", "Yes")], True,
         ("lift_limits_note", "What are the timings?", ["yes"])),
        ("trolleys", "Are trolleys available?", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
    ]),
    ("Society rules", [
        ("gate_pass", "Does the society need a gate pass / permission for our team?", "chips",
         [("yes", "Yes, I'll arrange it"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("tape", "Can we use tape on the walls?", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("venue_notes", "Anything else the venue or society told you?", "text", None, False, None),
    ]),
]
QUESTIONS = {q[0]: q for _s, qs in SECTIONS for q in qs}
FOLLOWUPS = {q[5][0]: q for q in QUESTIONS.values() if q[5]}
REQUIRED = [k for k, q in QUESTIONS.items() if q[4]]

TAGS = [("decor", "Decor"), ("dj", "DJ / music"), ("activity", "Activity area"), ("return_gifts", "Return gifts"),
        ("food", "Food"), ("cake", "Cake table"), ("entry", "Entry / welcome"), ("unloading", "Unloading / lift"),
        ("other", "Other")]
TAG_KEYS = [k for k, _ in TAGS]


def venue_url(token: str) -> str:
    return f"{SITE_BASE_URL}/venue.html?t={token}"


def _j(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def _first(s) -> str:
    return (str(s or "").split(",")[0]).strip()


async def _lead(lead_id: int) -> dict:
    r = await database.fetch_one(
        "SELECT lead_id, is_booking, parent_name, email, phone, child_names, child_ages, event_date, event_time, venue "
        "FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not r:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return dict(r)


async def ensure_venue_link(lead_id: int, by: Optional[str] = None) -> str:
    """The booking's venue form link, creating it the first time."""
    row = await database.fetch_one("SELECT token FROM venue_info WHERE lead_id = :id", values={"id": lead_id})
    if row:
        return venue_url(row["token"])
    tok = secrets.token_urlsafe(12)
    await database.execute(
        "INSERT INTO venue_info (lead_id, token, created_by) VALUES (:id, :t, :by) ON CONFLICT (lead_id) DO NOTHING",
        values={"id": lead_id, "t": tok, "by": (by or "")[:80] or None})
    row = await database.fetch_one("SELECT token FROM venue_info WHERE lead_id = :id", values={"id": lead_id})
    return venue_url(row["token"])


def _missing(answers: dict) -> List[str]:
    out = []
    for k in REQUIRED:
        if not str(answers.get(k) or "").strip():
            out.append(k)
    return out


def _label(key: str) -> str:
    q = QUESTIONS.get(key) or FOLLOWUPS.get(key)
    if key in FOLLOWUPS:
        return FOLLOWUPS[key][5][1]
    return q[1] if q else key


def _answer_text(key: str, val) -> str:
    q = QUESTIONS.get(key)
    if q and q[3]:
        return dict(q[3]).get(val, str(val))
    if q and q[2] == "time":
        from routers.sales_leads import _fmt_time_12h
        return _fmt_time_12h(val) or str(val)
    return str(val)


def _booking_header(lead: dict) -> dict:
    from routers.sales_leads import _fmt_time_12h
    age = _first(lead.get("child_ages"))
    return {
        "lead_id": lead["lead_id"],
        "parent_name": (lead.get("parent_name") or "").strip(),
        "first_name": greeting_name(lead["parent_name"]) if lead.get("parent_name") else "",
        "child_name": _first(lead.get("child_names")),
        "child_age": age or None,
        "event_date": lead["event_date"].strftime("%a, %d %b %Y").replace(" 0", " ") if isinstance(lead.get("event_date"), date) else lead.get("event_date"),
        "event_time": _fmt_time_12h(lead.get("event_time")) if lead.get("event_time") else None,
        "venue": (lead.get("venue") or "").strip() or None,
    }


async def _media(lead_id: int, base: str) -> list:
    rows = await database.fetch_all(
        "SELECT id, kind, mime, filename, size_bytes, tags, caption, created_at FROM venue_media "
        "WHERE lead_id = :id ORDER BY id", values={"id": lead_id})
    return [{"id": r["id"], "kind": r["kind"], "mime": r["mime"], "filename": r["filename"],
             "size": r["size_bytes"], "tags": _j(r["tags"]) or [], "caption": r["caption"],
             "url": f"{base}/{r['id']}", "uploaded_at": _to_ist_str(r["created_at"])} for r in rows]


def _questions_out() -> list:
    out = []
    for title, qs in SECTIONS:
        out.append({"title": title, "questions": [
            {"key": k, "label": l, "type": t, "required": req,
             "options": [{"value": v, "label": ol} for v, ol in (opts or [])],
             "followup": ({"key": fu[0], "label": fu[1], "when": fu[2]} if fu else None)}
            for k, l, t, opts, req, fu in qs]})
    return out


def _range_response(data: bytes, mime: str, range_header: Optional[str]) -> Response:
    """Serves a file, honouring a single "bytes=a-b" range (Safari needs it for video)."""
    total = len(data)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    m = re.match(r"bytes=(\d*)-(\d*)$", (range_header or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else total - 1
        else:
            start = max(0, total - int(m.group(2)))
            end = total - 1
        end = min(end, total - 1)
        if start > end or start >= total:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(content=data[start:end + 1], status_code=206, media_type=mime, headers=headers)
    return Response(content=data, media_type=mime, headers=headers)


# ─── public ────────────────────────────────────────────────────────────────

async def _by_token(token: str) -> dict:
    try:
        row = await database.fetch_one("SELECT * FROM venue_info WHERE token = :t", values={"t": token})
    except Exception:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="This link isn't valid — please check the link we sent you.")
    return dict(row)


@router.get("/venue-info/{token}")
async def public_get(token: str):
    row = await _by_token(token)
    lead = await _lead(row["lead_id"])
    if not row["opened_at"]:
        await database.execute("UPDATE venue_info SET opened_at = NOW() WHERE id = :id", values={"id": row["id"]})
    answers = _j(row["answers"]) or {}
    return {
        "booking": _booking_header(lead),
        "sections": _questions_out(),
        "answers": answers,
        "missing": _missing(answers),
        "tags": [{"key": k, "label": l} for k, l in TAGS],
        "media": await _media(row["lead_id"], f"/api/venue-info/{token}/media"),
        "limits": {"image_mb": MAX_IMAGE_BYTES // (1024 * 1024), "video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
                   "images": MAX_IMAGES, "videos": MAX_VIDEOS},
        "tnc_url": TNC_URL,
        "tnc_accepted": bool(row["tnc_accepted_at"]),
        "submitted_at": _to_ist_str(row["submitted_at"]),
    }


class VenueAnswers(BaseModel):
    answers: Dict[str, Optional[str]] = {}
    accept_tnc: Optional[bool] = None
    submit: bool = False


def _clean_answers(raw: Dict[str, Optional[str]]) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        v = (str(v).strip() if v is not None else "")
        if k in QUESTIONS:
            q = QUESTIONS[k]
            if v and q[3] and v not in {o[0] for o in q[3]}:
                raise HTTPException(status_code=400, detail=f"Please pick one of the options for: {q[1]}")
            if v and q[2] == "time" and not re.fullmatch(r"\d{1,2}:\d{2}", v):
                raise HTTPException(status_code=400, detail=f"Please pick a time for: {q[1]}")
            out[k] = v[:1500]
        elif k in FOLLOWUPS:
            out[k] = v[:300]
    return out


@router.post("/venue-info/{token}")
async def public_save(token: str, body: VenueAnswers):
    row = await _by_token(token)
    answers = _j(row["answers"]) or {}
    answers.update(_clean_answers(body.answers))
    answers = {k: v for k, v in answers.items() if v}
    tnc = bool(row["tnc_accepted_at"]) if body.accept_tnc is None else bool(body.accept_tnc)
    if body.submit and not tnc:
        raise HTTPException(status_code=400, detail="Please tick that you've read the Terms & Conditions.")
    await database.execute(
        """UPDATE venue_info SET answers = CAST(:a AS JSONB), updated_at = NOW(),
                  tnc_accepted_at = CASE WHEN :tnc THEN COALESCE(tnc_accepted_at, NOW()) ELSE NULL END,
                  submitted_at = CASE WHEN :sub THEN NOW() ELSE submitted_at END
           WHERE id = :id""",
        values={"a": json.dumps(answers), "tnc": tnc, "sub": bool(body.submit), "id": row["id"]})
    if body.submit:
        logger.info(f"Lead #{row['lead_id']}: venue details submitted ({len(_missing(answers))} missing)")
    return {"success": True, "answers": answers, "missing": _missing(answers), "tnc_accepted": tnc}


def _clean_tags(tags: str) -> list:
    return [t for t in TAG_KEYS if t in {x.strip() for x in (tags or "").split(",")}]


@router.post("/venue-info/{token}/media")
async def public_upload(token: str, file: UploadFile = File(...), tags: str = Form(""), caption: str = Form("")):
    row = await _by_token(token)
    mime = (file.content_type or "").lower()
    kind = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else None
    if not kind:
        raise HTTPException(status_code=400, detail="Please upload a photo or a video.")
    data = await file.read()
    cap = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    if len(data) > cap:
        raise HTTPException(status_code=413, detail=f"That {kind} is too large — up to {cap // (1024 * 1024)} MB please."
                            + (" Try a shorter clip." if kind == "video" else ""))
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    n = await database.fetch_val("SELECT COUNT(*) FROM venue_media WHERE lead_id = :id AND kind = :k",
                                 values={"id": row["lead_id"], "k": kind})
    if n >= (MAX_IMAGES if kind == "image" else MAX_VIDEOS):
        raise HTTPException(status_code=400, detail=f"You can add up to {MAX_IMAGES} photos and {MAX_VIDEOS} videos.")
    mid = await database.fetch_val(
        """INSERT INTO venue_media (lead_id, kind, mime, filename, size_bytes, data, tags, caption)
           VALUES (:id, :k, :m, :f, :s, :d, CAST(:t AS JSONB), :c) RETURNING id""",
        values={"id": row["lead_id"], "k": kind, "m": mime[:60], "f": (file.filename or "")[:120] or None,
                "s": len(data), "d": data, "t": json.dumps(_clean_tags(tags)), "c": (caption or "").strip()[:200] or None})
    await database.execute("UPDATE venue_info SET updated_at = NOW() WHERE id = :id", values={"id": row["id"]})
    media = await _media(row["lead_id"], f"/api/venue-info/{token}/media")
    return {"success": True, "id": mid, "media": media}


async def _media_row(lead_id: int, mid: int):
    r = await database.fetch_one("SELECT data, mime FROM venue_media WHERE id = :m AND lead_id = :id",
                                 values={"m": mid, "id": lead_id})
    if not r:
        raise HTTPException(status_code=404, detail="File not found.")
    return r


@router.get("/venue-info/{token}/media/{mid}")
async def public_media(token: str, mid: int, request: Request):
    row = await _by_token(token)
    r = await _media_row(row["lead_id"], mid)
    return _range_response(bytes(r["data"]), r["mime"], request.headers.get("range"))


class MediaEdit(BaseModel):
    tags: List[str] = []
    caption: Optional[str] = None


@router.post("/venue-info/{token}/media/{mid}")
async def public_media_edit(token: str, mid: int, body: MediaEdit):
    row = await _by_token(token)
    await _media_row(row["lead_id"], mid)
    await database.execute(
        "UPDATE venue_media SET tags = CAST(:t AS JSONB), caption = :c WHERE id = :m",
        values={"t": json.dumps(_clean_tags(",".join(body.tags or []))), "c": (body.caption or "").strip()[:200] or None, "m": mid})
    return {"success": True}


@router.delete("/venue-info/{token}/media/{mid}")
async def public_media_delete(token: str, mid: int):
    row = await _by_token(token)
    await database.execute("DELETE FROM venue_media WHERE id = :m AND lead_id = :id", values={"m": mid, "id": row["lead_id"]})
    return {"success": True}


# ─── admin ─────────────────────────────────────────────────────────────────

@router.get("/admin/bookings/{lead_id}/venue-info")
async def admin_get(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    try:
        url = await ensure_venue_link(lead_id)
    except Exception:
        logger.exception("venue_info table missing (migration 080?)")
        raise HTTPException(status_code=500, detail="The venue form isn't set up yet — the server needs a restart to add its table.")
    row = dict(await database.fetch_one("SELECT * FROM venue_info WHERE lead_id = :id", values={"id": lead_id}))
    answers = _j(row["answers"]) or {}
    rows = []
    for title, qs in SECTIONS:
        for k, l, _t, _o, _req, fu in qs:
            v = answers.get(k)
            txt = _answer_text(k, v) if v else None
            if fu and answers.get(fu[0]) and v in fu[2]:
                txt = (txt or "") + " — " + answers[fu[0]]
            rows.append({"section": title, "key": k, "label": l, "answer": txt, "required": _req})
    return {
        "url": url, "booking": _booking_header(lead), "email": lead["email"], "phone": lead["phone"],
        "rows": rows, "missing": [_label(k) for k in _missing(answers)],
        "answered": len(REQUIRED) - len(_missing(answers)), "total": len(REQUIRED),
        "tags": [{"key": k, "label": l} for k, l in TAGS],
        "media": await _media(lead_id, f"/api/admin/bookings/{lead_id}/venue-info/media"),
        "tnc_accepted_at": _to_ist_str(row["tnc_accepted_at"]),
        "opened_at": _to_ist_str(row["opened_at"]), "updated_at": _to_ist_str(row["updated_at"]),
        "submitted_at": _to_ist_str(row["submitted_at"]),
        "emailed_at": _to_ist_str(row["emailed_at"]), "whatsapp_at": _to_ist_str(row["whatsapp_at"]),
    }


@router.get("/admin/bookings/{lead_id}/venue-info/media/{mid}")
async def admin_media(lead_id: int, mid: int, request: Request, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    r = await _media_row(lead_id, mid)
    return _range_response(bytes(r["data"]), r["mime"], request.headers.get("range"))


def _email_html(first: str, child: str, url: str, hdr: dict) -> str:
    from routers.leads import MASCOT_URL, BRAND_PURPLE
    hi = f"Hi {first}," if first else "Hi,"
    party = f"{child}'s party" if child else "your party"
    when = " · ".join(x for x in [hdr.get("event_date"), hdr.get("event_time")] if x)
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#F5F0FF;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F0FF;padding:28px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(45,33,64,.08)">
<tr><td style="background:linear-gradient(135deg,#E65A96 0%,{BRAND_PURPLE} 100%);padding:26px;text-align:center">
<img src="{MASCOT_URL}" width="150" alt="" style="display:block;margin:0 auto 10px;border-radius:18px;background:#fff;padding:8px 12px">
<div style="font-family:Georgia,serif;font-size:21px;font-weight:700;color:#fff">A quick venue check for {party}</div></td></tr>
<tr><td style="padding:24px 26px;font-size:15px;line-height:1.6;color:#2D2140">
{hi}<br><br>To plan setup, timings and pack-up smoothly, please tell us a little about the venue —
timings, lift and parking, society rules — and add a few photos of the space. It takes about 2 minutes,
and you can save and come back anytime.
<div style="margin:14px 0 0;font-size:13px;color:#6B6280">Booking #{hdr.get('lead_id')}{(' · ' + when) if when else ''}{(' · ' + hdr['venue']) if hdr.get('venue') else ''}</div>
<div style="text-align:center;margin:24px 0 8px">
<a href="{url}" style="display:inline-block;background:#E65A96;color:#fff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 28px;border-radius:999px">📍 Share venue details</a></div>
<div style="text-align:center;font-size:12px;color:#8B7FA0">Or open: <a href="{url}" style="color:{BRAND_PURPLE}">{url}</a></div>
</td></tr>
<tr><td style="padding:0 26px 24px;font-size:12.5px;color:#8B7FA0;text-align:center;border-top:1px solid #F0E9FA">
<br>Questions? +91 90044 35362 · +91 97422 40477</td></tr></table>
</td></tr></table></body></html>"""


class ChangedBy(BaseModel):
    changed_by: str = ""


@router.post("/admin/bookings/{lead_id}/venue-info/email")
async def admin_email(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    if not lead["email"]:
        raise HTTPException(status_code=400, detail="This booking has no email on file.")
    url = await ensure_venue_link(lead_id, body.changed_by)
    from routers.leads import _gmail_send
    hdr = _booking_header(lead)
    child, first = hdr["child_name"], hdr["first_name"]
    subject = f"📍 Venue details for {child}'s party (Booking #{lead_id})" if child else f"📍 Venue details for your party (Booking #{lead_id})"
    text = (f"Hi {first},\n\n" if first else "Hi,\n\n") + \
        "To plan setup, timings and pack-up smoothly, please share a few details about the venue " \
        f"(about 2 minutes — you can save and come back anytime):\n{url}\n\n" \
        "Team Wondershop Experiences\n+91 90044 35362 · +91 97422 40477"
    try:
        await _gmail_send(lead["email"], subject, text, _email_html(first, child, url, hdr))
    except Exception as e:
        logger.exception(f"Lead #{lead_id}: venue form email failed")
        raise HTTPException(status_code=502, detail=f"Couldn't send the email: {e}")
    await database.execute("UPDATE venue_info SET emailed_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True, "sent_to": lead["email"]}


@router.post("/admin/bookings/{lead_id}/venue-info/whatsapp")
async def admin_whatsapp(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("UPDATE venue_info SET whatsapp_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True}
