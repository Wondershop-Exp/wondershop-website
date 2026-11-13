"""
Venue master — 2026-11-13, per Shruti:

  "in some cases, 1 party can have multiple venue recce. we would like to
  build a venue master with all the details and then link a venue to a
  party/booking/lead. the current venue link from booking/lead is ok, but give
  another method to create a venue on sales quote and booking, where team can
  input the details. it can or cannot be linked to a lead/booking. give a
  listing page of the venue as well where we can see the details, photo/video
  of the venue".

Decisions (Shruti, 2026-11-13): several venues per party = client shortlists
venues; going back to a venue = reuse and update the same record; timings,
floor map, other event that day and T&C stay per party (venue_info.PARTY_KEYS).

Tables (migration 085): venues, lead_venues, venue_media.venue_id.
A lead's venue form (venue.html) shares answers with its Final venue (or its
only linked venue) — see venue_info.linked_venue / push_to_venue.

Admin (X-Admin-Password; sales login allowed — security.py):
  GET    /api/admin/venues?q=                         list (search name / address)
  POST   /api/admin/venues                            create {name, answers, lead_id?, status?, changed_by}
  GET    /api/admin/venues/meta                       the questions (venue-level only)
  GET    /api/admin/venues/{id}                       details + media + linked parties
  POST   /api/admin/venues/{id}                       update {name?, answers, changed_by}
  DELETE /api/admin/venues/{id}                       delete (admin only)
  POST   /api/admin/venues/{id}/media                 upload a photo / video
  GET    /api/admin/venues/{id}/media/{mid}           a file
  POST   /api/admin/venues/{id}/media/{mid}           tags / caption
  DELETE /api/admin/venues/{id}/media/{mid}           remove
  POST   /api/admin/venues/{id}/link                  {lead_id, status, changed_by}
  DELETE /api/admin/venues/{id}/link/{lead_id}        unlink
  GET    /api/admin/lead-venues/{lead_id}             venues linked to a lead
"""
import json
import logging
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str
from routers import venue_info as vi
from security import password_role

logger = logging.getLogger(__name__)
router = APIRouter()

STATUSES = {"shortlisted": "Shortlisted", "final": "Final", "rejected": "Not chosen"}
VENUE_TAGS = vi.TAGS + vi.RECCE_TAGS


def _j(v):
    return vi._j(v) or {}


def _venue_keys() -> set:
    keys = set()
    for _t, qs in vi.venue_level_sections():
        for q in qs:
            keys.add(q[0])
            if q[5]:
                keys.add(q[5][0])
    return keys


def _clean(raw: Dict[str, Optional[str]]) -> dict:
    allowed = _venue_keys()
    cleaned = vi._clean_answers({k: v for k, v in (raw or {}).items() if k in allowed})
    return cleaned


def _summary(a: dict) -> dict:
    """The handful of facts shown on a venue card."""
    def t(k):
        v = a.get(k)
        return vi._answer_text(k, v) if v else None
    return {"address": a.get("venue_address"), "maps_link": a.get("maps_link"), "venue_type": t("venue_type"),
            "floor": t("floor"), "route": t("route"), "ceiling": (a.get("ceiling_exact") or t("ceiling")),
            "plug16": t("plug16"), "tape": t("tape"), "contact": " · ".join(x for x in [a.get("venue_contact_name"), a.get("venue_contact_phone")] if x) or None}


async def _media_for_venue(vid: int) -> list:
    """Photos added to the venue + those from the venue forms of parties where it is Final."""
    rows = await database.fetch_all(
        """SELECT m.id, m.kind, m.mime, m.filename, m.size_bytes, m.tags, m.caption, m.created_at, m.lead_id
             FROM venue_media m
            WHERE m.venue_id = :v
               OR m.lead_id IN (SELECT lead_id FROM lead_venues WHERE venue_id = :v AND status = 'final')
            ORDER BY m.id DESC""", values={"v": vid})
    return [{"id": r["id"], "kind": r["kind"], "mime": r["mime"], "caption": r["caption"], "tags": _j(r["tags"]) or [],
             "from_lead": r["lead_id"], "uploaded_at": _to_ist_str(r["created_at"]),
             "url": f"/api/admin/venues/{vid}/media/{r['id']}"} for r in rows]


async def _get(vid: int) -> dict:
    r = await database.fetch_one("SELECT * FROM venues WHERE id = :id", values={"id": vid})
    if not r:
        raise HTTPException(status_code=404, detail="Venue not found.")
    return dict(r)


def _date(d):
    return d.strftime("%d %b %Y").lstrip("0") if isinstance(d, date) else d


async def _links(vid: int) -> list:
    rows = await database.fetch_all(
        """SELECT lv.lead_id, lv.status, lv.note, lv.created_at, l.parent_name, l.child_names, l.event_date, l.is_booking, l.status AS lead_status
             FROM lead_venues lv JOIN leads l ON l.lead_id = lv.lead_id
            WHERE lv.venue_id = :v ORDER BY l.event_date DESC NULLS LAST, lv.id DESC""", values={"v": vid})
    return [{"lead_id": r["lead_id"], "status": r["status"], "status_label": STATUSES.get(r["status"], r["status"]),
             "client": (r["parent_name"] or "").strip(), "child": vi._first(r["child_names"]), "event_date": _date(r["event_date"]),
             "is_booking": bool(r["is_booking"]), "note": r["note"]} for r in rows]


# ─── list / create ─────────────────────────────────────────────────────────

@router.get("/venues")
async def list_venues(q: str = "", x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    rows = await database.fetch_all(
        """SELECT v.id, v.name, v.answers, v.updated_at, v.created_at,
                  (SELECT COUNT(*) FROM lead_venues lv WHERE lv.venue_id = v.id) AS parties,
                  (SELECT COUNT(*) FROM venue_media m WHERE m.venue_id = v.id
                      OR m.lead_id IN (SELECT lead_id FROM lead_venues WHERE venue_id = v.id AND status = 'final')) AS media,
                  (SELECT m.id FROM venue_media m WHERE m.kind = 'image' AND (m.venue_id = v.id
                      OR m.lead_id IN (SELECT lead_id FROM lead_venues WHERE venue_id = v.id AND status = 'final'))
                    ORDER BY (m.tags ? 'decor_wide') DESC, (m.tags ? 'decor') DESC, m.id LIMIT 1) AS thumb
             FROM venues v
            WHERE (:q = '' OR LOWER(v.name) LIKE :like OR LOWER(COALESCE(v.answers->>'venue_address','')) LIKE :like)
            ORDER BY COALESCE(v.updated_at, v.created_at) DESC LIMIT 300""",
        values={"q": q.strip(), "like": f"%{q.strip().lower()}%"})
    out = []
    for r in rows:
        a = _j(r["answers"])
        out.append({"id": r["id"], "name": r["name"], **_summary(a), "parties": r["parties"], "media": r["media"],
                    "thumb_url": f"/api/admin/venues/{r['id']}/media/{r['thumb']}" if r["thumb"] else None,
                    "recce_at": a.get("_recce_at"), "recce_by": a.get("_recce_by"),
                    "updated_at": _to_ist_str(r["updated_at"] or r["created_at"])})
    return {"venues": out}


@router.get("/venues/meta")
async def meta(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    secs = []
    for title, qs in vi.venue_level_sections():
        secs.append({"title": title, "team_only": title.startswith("Recce"), "questions": [
            {"key": k, "label": l, "type": t, "options": [{"value": v, "label": ol} for v, ol in (opts or [])],
             "followup": ({"key": fu[0], "label": fu[1], "when": fu[2]} if fu else None)}
            for k, l, t, opts, _req, fu in qs]})
    return {"sections": secs, "tags": [{"key": k, "label": l} for k, l in VENUE_TAGS],
            "statuses": [{"key": k, "label": l} for k, l in STATUSES.items()]}


class VenueIn(BaseModel):
    name: Optional[str] = None
    answers: Dict[str, Optional[str]] = {}
    lead_id: Optional[int] = None
    status: str = "shortlisted"
    changed_by: str = ""


@router.post("/venues")
async def create_venue(body: VenueIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Please give the venue a name.")
    answers = _clean(body.answers)
    # Starting from a lead that already has venue-form answers: carry them over.
    if body.lead_id:
        row = await database.fetch_one("SELECT answers FROM venue_info WHERE lead_id = :id", values={"id": body.lead_id})
        if row:
            for k, v in (_j(row["answers"])).items():
                if k in _venue_keys() and v and not answers.get(k):
                    answers[k] = v
    vid = await database.fetch_val(
        "INSERT INTO venues (name, answers, created_by, updated_at, updated_by) VALUES (:n, CAST(:a AS JSONB), :by, NOW(), :by) RETURNING id",
        values={"n": name[:150], "a": json.dumps(answers), "by": (body.changed_by or "")[:80] or None})
    if body.lead_id:
        await _link(vid, body.lead_id, body.status, body.changed_by)
    return {"success": True, "id": vid}


# ─── one venue ─────────────────────────────────────────────────────────────

@router.get("/venues/{vid}")
async def get_venue(vid: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    v = await _get(vid)
    a = _j(v["answers"])
    rows = []
    for title, qs in vi.venue_level_sections():
        for k, l, _t, _o, _req, fu in qs:
            val = a.get(k)
            txt = vi._answer_text(k, val) if val else None
            if fu and a.get(fu[0]) and val in fu[2]:
                txt = (txt or "") + " — " + a[fu[0]]
            rows.append({"section": title, "key": k, "label": l, "answer": txt})
    return {"id": v["id"], "name": v["name"], "answers": {k: x for k, x in a.items() if not k.startswith("_")},
            "summary": _summary(a), "rows": rows, "media": await _media_for_venue(vid), "links": await _links(vid),
            "tags": [{"key": k, "label": l} for k, l in VENUE_TAGS],
            "recce_at": a.get("_recce_at"), "recce_by": a.get("_recce_by"),
            "created_by": v["created_by"], "created_at": _to_ist_str(v["created_at"]),
            "updated_by": v["updated_by"], "updated_at": _to_ist_str(v["updated_at"])}


@router.post("/venues/{vid}")
async def update_venue(vid: int, body: VenueIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    v = await _get(vid)
    a = _j(v["answers"])
    for k, val in _clean(body.answers).items():
        if val:
            a[k] = val
        else:
            a.pop(k, None)
    for k in [k for k in body.answers if k in _venue_keys() and not (body.answers[k] or "").strip()]:
        a.pop(k, None)
    name = (body.name or "").strip() or v["name"]
    await database.execute(
        "UPDATE venues SET name = :n, answers = CAST(:a AS JSONB), updated_at = NOW(), updated_by = :by WHERE id = :id",
        values={"n": name[:150], "a": json.dumps(a), "by": (body.changed_by or "")[:80] or None, "id": vid})
    return {"success": True}


@router.delete("/venues/{vid}")
async def delete_venue(vid: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if password_role(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Only the admin login can delete a venue.")
    await _get(vid)
    await database.execute("DELETE FROM venues WHERE id = :id", values={"id": vid})
    return {"success": True}


# ─── media ─────────────────────────────────────────────────────────────────

@router.post("/venues/{vid}/media")
async def upload(vid: int, file: UploadFile = File(...), tags: str = Form(""), caption: str = Form(""),
                 x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get(vid)
    mime = (file.content_type or "").lower()
    kind = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else None
    if not kind:
        raise HTTPException(status_code=400, detail="Please upload a photo or a video.")
    data = await file.read()
    cap = vi.MAX_IMAGE_BYTES if kind == "image" else vi.MAX_VIDEO_BYTES
    if not data or len(data) > cap:
        raise HTTPException(status_code=413 if data else 400,
                            detail=f"That {kind} is {'too large — up to ' + str(cap // (1024 * 1024)) + ' MB please' if data else 'empty'}.")
    mid = await database.fetch_val(
        """INSERT INTO venue_media (venue_id, kind, mime, filename, size_bytes, data, tags, caption)
           VALUES (:v, :k, :m, :f, :s, :d, CAST(:t AS JSONB), :c) RETURNING id""",
        values={"v": vid, "k": kind, "m": mime[:60], "f": (file.filename or "")[:120] or None, "s": len(data), "d": data,
                "t": json.dumps(vi._clean_tags(tags)), "c": (caption or "").strip()[:200] or None})
    await database.execute("UPDATE venues SET updated_at = NOW() WHERE id = :id", values={"id": vid})
    return {"success": True, "id": mid, "media": await _media_for_venue(vid)}


async def _media_row(vid: int, mid: int):
    r = await database.fetch_one(
        """SELECT id, data, mime, venue_id FROM venue_media WHERE id = :m AND (venue_id = :v
             OR lead_id IN (SELECT lead_id FROM lead_venues WHERE venue_id = :v AND status = 'final'))""",
        values={"m": mid, "v": vid})
    if not r:
        raise HTTPException(status_code=404, detail="File not found.")
    return r


@router.get("/venues/{vid}/media/{mid}")
async def media(vid: int, mid: int, request: Request, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    r = await _media_row(vid, mid)
    return vi._range_response(bytes(r["data"]), r["mime"], request.headers.get("range"))


class MediaEdit(BaseModel):
    tags: List[str] = []
    caption: Optional[str] = None


@router.post("/venues/{vid}/media/{mid}")
async def media_edit(vid: int, mid: int, body: MediaEdit, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _media_row(vid, mid)
    await database.execute("UPDATE venue_media SET tags = CAST(:t AS JSONB), caption = :c WHERE id = :m",
                           values={"t": json.dumps(vi._clean_tags(",".join(body.tags or []))),
                                   "c": (body.caption or "").strip()[:200] or None, "m": mid})
    return {"success": True}


@router.delete("/venues/{vid}/media/{mid}")
async def media_delete(vid: int, mid: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    r = await _media_row(vid, mid)
    if r["venue_id"] != vid:
        raise HTTPException(status_code=400, detail="This photo came from a party's venue form — remove it there.")
    await database.execute("DELETE FROM venue_media WHERE id = :m", values={"m": mid})
    return {"success": True}


# ─── links to leads / bookings ─────────────────────────────────────────────

async def _link(vid: int, lead_id: int, status: str, who: str):
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    if not await database.fetch_val("SELECT 1 FROM leads WHERE lead_id = :id", values={"id": lead_id}):
        raise HTTPException(status_code=404, detail=f"Lead #{lead_id} not found.")
    await database.execute(
        """INSERT INTO lead_venues (lead_id, venue_id, status, created_by) VALUES (:l, :v, :s, :by)
           ON CONFLICT (lead_id, venue_id) DO UPDATE SET status = EXCLUDED.status""",
        values={"l": lead_id, "v": vid, "s": status, "by": (who or "")[:80] or None})
    if status == "final":
        # Only one Final per party: the others go back to Shortlisted.
        await database.execute("UPDATE lead_venues SET status = 'shortlisted' WHERE lead_id = :l AND venue_id <> :v AND status = 'final'",
                               values={"l": lead_id, "v": vid})
        # Fill the venue's blanks from what the party's form already knows.
        row = await database.fetch_one("SELECT answers FROM venue_info WHERE lead_id = :id", values={"id": lead_id})
        if row:
            v = await _get(vid)
            a = _j(v["answers"])
            add = {k: x for k, x in _j(row["answers"]).items() if k in _venue_keys() and x and not a.get(k)}
            if add:
                await database.execute("UPDATE venues SET answers = answers || CAST(:a AS JSONB), updated_at = NOW() WHERE id = :id",
                                       values={"a": json.dumps(add), "id": vid})


class LinkIn(BaseModel):
    lead_id: int
    status: str = "shortlisted"
    changed_by: str = ""


@router.post("/venues/{vid}/link")
async def link(vid: int, body: LinkIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await _get(vid)
    await _link(vid, body.lead_id, body.status, body.changed_by)
    return {"success": True, "venues": await _lead_venues(body.lead_id)}


@router.delete("/venues/{vid}/link/{lead_id}")
async def unlink(vid: int, lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("DELETE FROM lead_venues WHERE venue_id = :v AND lead_id = :l", values={"v": vid, "l": lead_id})
    return {"success": True, "venues": await _lead_venues(lead_id)}


async def _lead_venues(lead_id: int) -> list:
    rows = await database.fetch_all(
        """SELECT v.id, v.name, v.answers, lv.status,
                  (SELECT COUNT(*) FROM venue_media m WHERE m.venue_id = v.id) AS media
             FROM lead_venues lv JOIN venues v ON v.id = lv.venue_id
            WHERE lv.lead_id = :l ORDER BY (lv.status = 'final') DESC, (lv.status = 'rejected'), lv.id""", values={"l": lead_id})
    return [{"id": r["id"], "name": r["name"], "status": r["status"], "status_label": STATUSES.get(r["status"], r["status"]),
             "media": r["media"], "recce_at": _j(r["answers"]).get("_recce_at"), **_summary(_j(r["answers"]))} for r in rows]


@router.get("/lead-venues/{lead_id}")
async def lead_venues(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    return {"venues": await _lead_venues(lead_id)}
