"""
Sorting Hat party app — 2026-10-18, per Shruti.

"preload the details for every event and give a unique code ... the sorting
hat volunteer or the host enters this code to load the ui" / "admin can create
codes for confirmed bookings" / "1 tablet per party" / "let's not make the
code stop working for now" / "are we saving the team split anywhere?" -> later: "this information is not
really useful (the team-child mapping)", so the split stays on the tablet only

One row per confirmed booking in sorting_hat_events (migration 069): a
6-character event code and the team setup (config JSON). The results /
device_id columns are unused (team split stays on the tablet). Team audio clips live in sorting_hat_audio.

Admin only (X-Admin-Password, admin role; not in security.SALES_ALLOWED):
  GET  /api/admin/sorting-hat/{lead_id}                 setup, code, audio
  POST /api/admin/sorting-hat/{lead_id}                 save setup (creates code)
  POST /api/admin/sorting-hat/{lead_id}/audio           upload a clip (multipart)
  POST /api/admin/sorting-hat/audio/{audio_id}/remove   delete a clip
  POST /api/admin/sorting-hat/{lead_id}/new-code        replace the code
With the event code (tools/sorting-hat-*/index.html; wrong codes throttled):
  GET  /api/sorting-hat/event/{code}                    everything for the tablet
  GET  /api/sorting-hat/event/{code}/audio/{audio_id}   a clip
"""
import json
import secrets
import time
from typing import List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin

router = APIRouter()
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L
MAX_AUDIO = 7 * 1024 * 1024
_fails: dict = {}
MAX_FAILS, WINDOW = 10, 15 * 60


def _admin_only(pw):
    if _require_admin(pw) != "admin":
        raise HTTPException(403, "Admin only")


def _j(v, default):
    if v is None:
        return default
    return json.loads(v) if isinstance(v, str) else v


async def _booking(lead_id: int) -> dict:
    r = await database.fetch_one(
        "SELECT lead_id, parent_name, child_names, child_ages, child_genders, kids_count, venue, city, event_date, status, is_booking "
        "FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not r:
        raise HTTPException(404, "Booking not found")
    d = dict(r)
    d["event_date"] = d["event_date"].isoformat() if d.get("event_date") else None
    return d


async def _audio_list(lead_id: int):
    rows = await database.fetch_all("SELECT id, name, mime FROM sorting_hat_audio WHERE lead_id=:id ORDER BY id", values={"id": lead_id})
    return [dict(r) for r in rows]


def _event_out(ev) -> Optional[dict]:
    if not ev:
        return None
    return {"code": ev["code"], "config": _j(ev["config"], {})}


async def _new_code() -> str:
    for _ in range(20):
        c = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not await database.fetch_one("SELECT 1 FROM sorting_hat_events WHERE code=:c", values={"c": c}):
            return c
    raise HTTPException(500, "Couldn't make a code, please retry")


# ─── admin ────────────────────────────────────────────────────────────────

@router.get("/admin/sorting-hat/{lead_id}")
async def admin_get(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    ev = await database.fetch_one("SELECT * FROM sorting_hat_events WHERE lead_id=:id", values={"id": lead_id})
    return {"booking": await _booking(lead_id), "event": _event_out(ev), "audio": await _audio_list(lead_id)}


class Team(BaseModel):
    name: str
    color: str
    cap: int
    audio: List[int] = []


class Setup(BaseModel):
    teams: List[Team]
    ask_names: bool = False
    kids: int = 0


@router.post("/admin/sorting-hat/{lead_id}")
async def admin_save(lead_id: int, body: Setup, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    b = await _booking(lead_id)
    if not b["is_booking"] or b["status"] == "Cancelled":
        raise HTTPException(400, "Codes can only be made for confirmed bookings.")
    if not 2 <= len(body.teams) <= 8:
        raise HTTPException(400, "Use 2 to 8 teams.")
    cfg = {"teams": [t.dict() for t in body.teams], "ask_names": body.ask_names, "kids": body.kids}
    ev = await database.fetch_one("SELECT code FROM sorting_hat_events WHERE lead_id=:id", values={"id": lead_id})
    if ev:
        await database.execute("UPDATE sorting_hat_events SET config=CAST(:c AS JSONB), updated_at=NOW() WHERE lead_id=:id",
                               values={"c": json.dumps(cfg), "id": lead_id})
    else:
        await database.execute("INSERT INTO sorting_hat_events (lead_id, code, config) VALUES (:id, :code, CAST(:c AS JSONB))",
                               values={"id": lead_id, "code": await _new_code(), "c": json.dumps(cfg)})
    return await admin_get(lead_id, x_admin_password)


@router.post("/admin/sorting-hat/{lead_id}/audio")
async def admin_audio(lead_id: int, file: UploadFile = File(...), x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await _booking(lead_id)
    raw = await file.read()
    if not raw or len(raw) > MAX_AUDIO:
        raise HTTPException(400, "Audio must be under 7 MB.")
    mime = (file.content_type or "").lower()
    if not mime.startswith("audio/") and mime not in ("video/mp4", "application/octet-stream"):
        raise HTTPException(400, "Please upload an audio file (mp3, m4a, wav).")
    r = await database.fetch_one(
        "INSERT INTO sorting_hat_audio (lead_id, name, mime, data) VALUES (:id, :n, :m, :d) RETURNING id",
        values={"id": lead_id, "n": (file.filename or "audio")[:160], "m": mime or "audio/mpeg", "d": raw})
    return {"id": r["id"], "name": (file.filename or "audio")[:160]}


@router.post("/admin/sorting-hat/audio/{audio_id}/remove")
async def admin_audio_remove(audio_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await database.execute("DELETE FROM sorting_hat_audio WHERE id=:id", values={"id": audio_id})
    return {"ok": True}


@router.post("/admin/sorting-hat/{lead_id}/new-code")
async def admin_new_code(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await database.execute("UPDATE sorting_hat_events SET code=:c, updated_at=NOW() WHERE lead_id=:id",
                           values={"c": await _new_code(), "id": lead_id})
    return await admin_get(lead_id, x_admin_password)


# ─── tablet (event code) ──────────────────────────────────────────────────

async def _by_code(request: Request, code: str):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    n, t0 = _fails.get(ip, [0, time.time()])
    if time.time() - t0 > WINDOW:
        n, t0 = 0, time.time()
    if n >= MAX_FAILS:
        raise HTTPException(429, "Too many tries. Please wait a few minutes.")
    ev = await database.fetch_one("SELECT * FROM sorting_hat_events WHERE code=:c", values={"c": (code or "").strip().upper()})
    if not ev:
        _fails[ip] = [n + 1, t0]
        raise HTTPException(404, "No event with that code")
    return ev


@router.get("/sorting-hat/event/{code}")
async def tablet_event(code: str, request: Request):
    ev = await _by_code(request, code)
    b = await _booking(ev["lead_id"])
    if b["status"] == "Cancelled":
        raise HTTPException(410, "This booking was cancelled.")
    b.pop("status", None); b.pop("is_booking", None)
    return {"booking": b, **_event_out(ev), "audio": await _audio_list(ev["lead_id"])}


@router.get("/sorting-hat/event/{code}/audio/{audio_id}")
async def tablet_audio(code: str, audio_id: int, request: Request):
    ev = await _by_code(request, code)
    r = await database.fetch_one("SELECT mime, data FROM sorting_hat_audio WHERE id=:a AND lead_id=:l",
                                 values={"a": audio_id, "l": ev["lead_id"]})
    if not r:
        raise HTTPException(404, "Audio not found")
    return Response(content=bytes(r["data"]), media_type=r["mime"] or "audio/mpeg",
                    headers={"Cache-Control": "private, max-age=31536000"})
