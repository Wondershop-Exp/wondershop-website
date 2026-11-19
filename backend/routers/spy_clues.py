"""
Spy clue prep — 2026-11-19, per Shruti.

  "for every spy, Sid or I prepare a spy station movement matrix, and then add
   clues in envelopes and write names of the station master who will be
   handing over the envelope ... Help me setup a visual dashboard for ops team
   (Shilpa) to be able to do the whole process from putting the clues in
   envelopes to adding volunteer names herself. She has a very basic
   education, 10th pass, so UI needs to be very simple. Volunteer name to
   station mapping will always be done by Sid or Shruti ... we reuse our
   clues, so we would be reusing the earlier matrixes built ... this is our
   IP ... this link should expire. Sales team should not have access."

How a party's envelopes work (Shruti's walk-through, 19 Nov 2026)
  * T teams (colours), S stations, T <= S, 5..8 stations in practice.
  * The matrix gives each team its own order of stations; in any round no two
    teams are at the same station (a Latin rectangle).
  * Each team has S+1 envelopes. Envelope k holds the clue to the team's k-th
    station; envelope S+1 is the final clue.
  * Envelope 1 is handed over by the host. Envelope k (k >= 2) is handed over
    by the volunteer of the station the team has just finished — station
    number grid[team][k-2].
    e.g. Red = 1,2,3,4,5 with 1 Surveillance/Mitika, 2 Hotel/Shilpa,
    3 Tarot/Nia, 4 Treasury/Hadi, 5 Bookstore/Ziya and host Sunny ->
    Red-1 Sunny (clue: Surveillance), Red-2 Mitika (Hotel), Red-3 Shilpa
    (Tarot), Red-4 Nia (Treasury), Red-5 Hadi (Bookstore), Red-6 Ziya (final).

Two trust models, like routers/decor_jobs.py:
  /admin/spy-clues/...     Shruti / Sid (X-Admin-Password, ADMIN login only —
                           not in security.SALES_ALLOWED, and checked again here).
  /spy-clue-job/{token}    Shilpa's link: no login, the long random token is
                           the access; it stops working at expires_at or when
                           revoked. Only ever looked up by its exact token.
Tables: spy_matrices, spy_clue_jobs (migration 090).
"""
import hashlib
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

SITE = "https://www.wondershopexperiences.com"
IST = ZoneInfo("Asia/Kolkata")
MIN_STATIONS, MAX_STATIONS = 3, 10
MAX_LINK_DAYS = 14

COLOURS = {   # name -> (background, text)
    "Red": ("#E53935", "#fff"), "Blue": ("#1E63D6", "#fff"), "Green": ("#2E9D46", "#fff"),
    "Purple": ("#7B3FB5", "#fff"), "Yellow": ("#F6C700", "#191919"), "Orange": ("#F57C00", "#fff"),
    "Pink": ("#E65A96", "#fff"), "Black": ("#222222", "#fff"), "White": ("#FFFFFF", "#191919"),
    "Brown": ("#7A4A24", "#fff"), "Silver": ("#B8BCC4", "#191919"), "Gold": ("#C9A227", "#191919"),
}
DEFAULT_COLOURS = ["Red", "Blue", "Green", "Purple", "Yellow", "Orange", "Pink", "Black", "White", "Brown"]

# Room names are standard per theme and live in clue_rooms (migration 091):
# picked from a dropdown, and a room added from any party shows in all of them
# (Shruti, 19 Nov 2026). Spy is seeded with its 5 rooms.
THEMES = ["Spy", "Harry Potter"]
_ICONS = [("surveil", "📷"), ("photo", "📷"), ("hotel", "🏨"), ("tarot", "🔮"), ("fortune", "🔮"),
          ("scarlet", "🔮"), ("treasur", "👑"), ("vault", "👑"), ("book", "📚"), ("lab", "🧪"),
          ("laser", "🔦"), ("potion", "🧪"), ("wand", "🪄"), ("owl", "🦉"), ("quidditch", "🧹"), ("gringott", "🏦"), ("library", "📚"), ("great hall", "🏰"),  ("museum", "🏛️"), ("bank", "🏦"), ("airport", "✈️"), ("cafe", "☕")]


def _s(v, n: int = 120) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _j(v, default):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def icon_for(room: str) -> str:
    r = (room or "").lower()
    for key, ic in _ICONS:
        if key in r:
            return ic
    return "🎯"


def colour_of(name: str):
    for k, v in COLOURS.items():
        if k.lower() == (name or "").strip().lower():
            return v
    return ("#6B7280", "#fff")


# ─── matrix rules ──────────────────────────────────────────────────────────

def check_grid(grid: Any, teams: int, stations: int) -> List[List[int]]:
    """Returns the grid as ints, or raises 400 saying what is wrong in plain words."""
    if not (MIN_STATIONS <= stations <= MAX_STATIONS):
        raise HTTPException(status_code=400, detail=f"Stations must be {MIN_STATIONS} to {MAX_STATIONS}.")
    if not (1 <= teams <= stations):
        raise HTTPException(status_code=400, detail="Teams can't be more than stations.")
    if not isinstance(grid, list) or len(grid) != teams:
        raise HTTPException(status_code=400, detail=f"The matrix needs {teams} team rows.")
    out = []
    for t, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != stations:
            raise HTTPException(status_code=400, detail=f"Team row {t + 1} needs {stations} stations.")
        try:
            row = [int(x) for x in row]
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Team row {t + 1} has an empty box.")
        if sorted(row) != list(range(1, stations + 1)):
            raise HTTPException(status_code=400, detail=f"Team row {t + 1} must visit every station exactly once.")
        out.append(row)
    for c in range(stations):
        col = [out[t][c] for t in range(teams)]
        if len(set(col)) != len(col):
            raise HTTPException(status_code=400, detail=f"Round {c + 1}: two teams are sent to the same station.")
    return out


def envelopes_of(grid: List[List[int]], setup: List[dict], host: str, final_label: str) -> List[List[dict]]:
    """grid[team] -> that team's S+1 envelopes, per the rule in the module docstring."""
    def st(n):
        return setup[n - 1] if 0 < n <= len(setup) else {}

    out = []
    for t, row in enumerate(grid):
        envs = []
        for k in range(1, len(row) + 2):
            if k == 1:
                giver, giver_at = host or "Host", "Host"
            else:
                prev = st(row[k - 2])
                giver, giver_at = prev.get("volunteer") or "?", prev.get("room") or f"Station {row[k - 2]}"
            if k <= len(row):
                nxt = st(row[k - 1])
                clue = nxt.get("room") or f"Station {row[k - 1]}"
                envs.append({"no": k, "station": row[k - 1], "clue": clue, "icon": nxt.get("icon") or icon_for(clue),
                             "activity": nxt.get("activity") or "", "final": False,
                             "giver": giver, "giver_at": giver_at})
            else:
                envs.append({"no": k, "station": None, "clue": final_label or "Final clue", "icon": "🏁",
                             "activity": "", "final": True, "giver": giver, "giver_at": giver_at})
        out.append(envs)
    return out


def sig_of(env: dict) -> str:
    raw = f"{env['clue']}|{env['giver']}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ─── jobs ──────────────────────────────────────────────────────────────────

def _job_dict(r) -> dict:
    d = dict(r)
    for k, dflt in (("grid", []), ("team_colours", []), ("station_setup", []), ("progress", {})):
        d[k] = _j(d.get(k), dflt)
    return d


def _team_names(job: dict) -> List[str]:
    names = [(_s(c, 30) or DEFAULT_COLOURS[i % len(DEFAULT_COLOURS)]) for i, c in enumerate(job["team_colours"])]
    while len(names) < job["teams"]:
        names.append(DEFAULT_COLOURS[len(names) % len(DEFAULT_COLOURS)])
    return names[:job["teams"]]


def link_state(job: dict) -> str:
    if not job.get("token"):
        return "none"
    if job.get("revoked"):
        return "revoked"
    exp = job.get("expires_at")
    if exp and exp <= datetime.now(timezone.utc):
        return "expired"
    return "live"


def _fmt_ist(dt) -> str:
    if not dt:
        return ""
    return dt.astimezone(IST).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _fmt_date(d) -> str:
    if not d:
        return ""
    return d.strftime("%a, %d %b %Y").replace(", 0", ", ")


def kids_label(kids, teams: int) -> str:
    """24 kids, 5 teams -> '24 kids · about 5 per team'."""
    if not kids:
        return ""
    lo, extra = divmod(int(kids), max(teams, 1))
    per = f"{lo}" if not extra else f"{lo}-{lo + 1}"
    return f"{kids} kids · {per} per team"


def view_of(job: dict, for_admin: bool) -> dict:
    envs = envelopes_of(job["grid"], job["station_setup"], job.get("host_name") or "", job.get("final_label") or "")
    names = _team_names(job)
    prog = job.get("progress") or {}
    teams, done_n, total = [], 0, 0
    for t, team_envs in enumerate(envs):
        bg, fg = colour_of(names[t])
        rows = []
        for e in team_envs:
            key = f"{t + 1}-{e['no']}"
            s = sig_of(e)
            done = prog.get(key) == s
            changed = bool(prog.get(key)) and not done
            done_n += done
            total += 1
            rows.append(dict(e, key=key, done=done, changed=changed))
        teams.append({"name": names[t], "bg": bg, "fg": fg, "envelopes": rows,
                      "done": sum(r["done"] for r in rows)})
    out = {
        "title": job["title"], "theme": job.get("theme") or "Spy", "event_date": job["event_date"].isoformat() if job.get("event_date") else "",
        "date_label": _fmt_date(job.get("event_date")), "teams_count": job["teams"], "stations_count": job["stations"],
        "kids": job.get("kids"), "kids_label": kids_label(job.get("kids"), job["teams"]),
        "host_name": job.get("host_name") or "", "final_label": job.get("final_label") or "Final clue",
        "teams": teams, "done": done_n, "total": total,
        "expires_label": _fmt_ist(job.get("expires_at")),
    }
    if for_admin:
        out.update({
            "id": job["id"], "lead_id": job.get("lead_id"), "matrix_id": job.get("matrix_id"),
            "grid": job["grid"], "team_colours": names, "station_setup": job["station_setup"],
            "link_state": link_state(job), "link": f"{SITE}/spy-clues.html?t={job['token']}" if job.get("token") else "",
            "expires_at": job["expires_at"].isoformat() if job.get("expires_at") else "",
            "opened_label": _fmt_ist(job.get("opened_at")),
            "updated_label": _fmt_ist(job.get("updated_at") or job.get("created_at")),
            "updated_by": job.get("updated_by") or job.get("created_by") or "",
        })
    return out


async def _job(job_id: int) -> dict:
    r = await database.fetch_one("SELECT * FROM spy_clue_jobs WHERE id = :id", values={"id": job_id})
    if not r:
        raise HTTPException(status_code=404, detail="Party not found.")
    return _job_dict(r)


async def _job_by_token(token: str) -> Optional[dict]:
    if not token or not (20 <= len(token) <= 64) or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return None
    r = await database.fetch_one("SELECT * FROM spy_clue_jobs WHERE token = :t", values={"t": token})
    return _job_dict(r) if r else None


def _admin_only(pw: Optional[str]) -> None:
    if _require_admin(pw) != "admin":
        raise HTTPException(status_code=403, detail="Only Shruti / Sid can open spy clue prep.")


# ─── admin: library + parties ──────────────────────────────────────────────

async def _matrices() -> List[dict]:
    rows = await database.fetch_all(
        """SELECT m.id, m.name, m.theme, m.teams, m.stations, m.grid, m.notes, m.created_at,
                  COUNT(j.id) AS used, MAX(j.event_date) AS last_used
           FROM spy_matrices m LEFT JOIN spy_clue_jobs j ON j.matrix_id = m.id
           WHERE NOT m.archived GROUP BY m.id ORDER BY m.stations, m.teams, m.id""")
    return [{"id": r["id"], "name": r["name"], "theme": r["theme"], "teams": r["teams"], "stations": r["stations"],
             "grid": _j(r["grid"], []), "notes": r["notes"] or "", "used": r["used"],
             "last_used": _fmt_date(r["last_used"])} for r in rows]


async def _rooms() -> List[dict]:
    rows = await database.fetch_all(
        "SELECT id, theme, name, icon, games FROM clue_rooms WHERE NOT archived ORDER BY theme, sort_order, id")
    return [{"id": r["id"], "theme": r["theme"], "room": r["name"], "icon": r["icon"] or icon_for(r["name"]),
             "games": _j(r["games"], [])} for r in rows]


@router.get("/admin/spy-clues/setup")
async def admin_setup(x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    rows = await database.fetch_all(
        """SELECT id, title, theme, event_date, teams, stations, kids, token, revoked, expires_at, progress, grid,
                  station_setup, host_name, final_label, team_colours
           FROM spy_clue_jobs ORDER BY event_date DESC NULLS LAST, id DESC LIMIT 200""")
    jobs = []
    for r in rows:
        j = _job_dict(r)
        v = view_of(dict(j, opened_at=None, updated_at=None, created_at=None, lead_id=None, matrix_id=None), True)
        jobs.append({"id": j["id"], "title": j["title"], "theme": j.get("theme") or "Spy", "date_label": v["date_label"],
                     "event_date": v["event_date"], "size": f"{j['teams']} teams × {j['stations']} stations" + (f" · {j['kids']} kids" if j.get("kids") else ""),
                     "done": v["done"], "total": v["total"], "link_state": v["link_state"]})
    return {"matrices": await _matrices(), "jobs": jobs, "rooms": await _rooms(), "themes": THEMES,
            "colours": [{"name": k, "bg": v[0], "fg": v[1]} for k, v in COLOURS.items()],
            "default_colours": DEFAULT_COLOURS}


@router.get("/admin/spy-clues/prefill/{lead_id}")
async def admin_prefill(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    """Party name, date and host from a booking, for a new party opened from the booking row."""
    _admin_only(x_admin_password)
    out = {"lead_id": lead_id, "title": "", "event_date": "", "host_name": "", "kids": None, "existing_id": None}
    ex = await database.fetch_one("SELECT id FROM spy_clue_jobs WHERE lead_id = :id ORDER BY id DESC LIMIT 1",
                                  values={"id": lead_id})
    if ex:
        out["existing_id"] = ex["id"]
    try:
        from event_naming import event_name
        b = await database.fetch_one("SELECT * FROM leads WHERE lead_id = :id", values={"id": lead_id})
        if b:
            b = dict(b)
            out["title"] = event_name(b) or f"Booking #{lead_id}"
            ed = b.get("event_date")
            out["event_date"] = ed.isoformat()[:10] if hasattr(ed, "isoformat") else _s(ed, 10)
            out["kids"] = b.get("kids_count") or None
    except Exception:
        logger.exception(f"Lead #{lead_id}: spy clue prefill couldn't read the booking")
    try:
        from routers.event_team import host_names
        out["host_name"] = await host_names(lead_id) or ""
    except Exception:
        logger.exception(f"Lead #{lead_id}: spy clue prefill couldn't read the host")
    return out


@router.get("/admin/spy-clues/for-booking/{lead_id}")
async def admin_for_booking(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    """The booking page's 🕵️ box: this booking's latest spy party (or none)."""
    _admin_only(x_admin_password)
    r = await database.fetch_one("SELECT * FROM spy_clue_jobs WHERE lead_id = :id ORDER BY id DESC LIMIT 1",
                                 values={"id": lead_id})
    if not r:
        return {"job": None}
    v = view_of(_job_dict(r), True)
    return {"job": {"id": v["id"], "done": v["done"], "total": v["total"], "link_state": v["link_state"],
                    "size": f"{v['teams_count']} teams × {v['stations_count']} stations"}}


@router.get("/admin/spy-clues/jobs/{job_id}")
async def admin_get(job_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    return view_of(await _job(job_id), True)


class StationIn(BaseModel):
    room: str = ""
    activity: str = ""
    volunteer: str = ""


class JobIn(BaseModel):
    title: str
    theme: str = "Spy"
    event_date: Optional[str] = None
    lead_id: Optional[int] = None
    teams: int
    stations: int
    kids: Optional[int] = None
    grid: List[List[Any]]
    save_matrix_as: Optional[str] = None
    team_colours: List[str] = []
    station_setup: List[StationIn] = []
    host_name: str = ""
    final_label: str = ""
    changed_by: Optional[str] = None


async def _match_or_save_matrix(grid, teams, stations, save_as: Optional[str], who, theme: str = "Spy") -> Optional[int]:
    rows = await database.fetch_all(
        "SELECT id, grid FROM spy_matrices WHERE teams = :t AND stations = :s AND theme = :th AND NOT archived ORDER BY id",
        values={"t": teams, "s": stations, "th": theme})
    for r in rows:
        if _j(r["grid"], []) == grid:
            if save_as:   # same grid already in the library: just (re)name it
                await database.execute("UPDATE spy_matrices SET name = :n WHERE id = :id",
                                       values={"n": _s(save_as, 80), "id": r["id"]})
            return r["id"]
    if not save_as:
        return None
    return await database.execute(
        "INSERT INTO spy_matrices (name, theme, teams, stations, grid, created_by) VALUES (:n, :th, :t, :s, :g, :by) RETURNING id",
        values={"n": _s(save_as, 80), "th": theme, "t": teams, "s": stations, "g": json.dumps(grid), "by": who})


async def _save(job_id: Optional[int], body: JobIn) -> int:
    title = _s(body.title, 120)
    if not title:
        raise HTTPException(status_code=400, detail="Give the party a name.")
    grid = check_grid(body.grid, body.teams, body.stations)
    setup = [{"room": _s(s.room, 60), "activity": _s(s.activity, 80), "volunteer": _s(s.volunteer, 40)}
             for s in body.station_setup][:body.stations]
    if len(setup) != body.stations:
        raise HTTPException(status_code=400, detail=f"Fill in all {body.stations} stations.")
    theme = body.theme if body.theme in THEMES else None
    if not theme:
        raise HTTPException(status_code=400, detail="Pick the theme.")
    master = {r["room"].lower(): r for r in await _rooms() if r["theme"] == theme}
    seen = set()
    for i, s in enumerate(setup):
        if not s["room"]:
            raise HTTPException(status_code=400, detail=f"Station {i + 1} needs a room.")
        m = master.get(s["room"].lower())
        if not m:
            raise HTTPException(status_code=400, detail=f"Station {i + 1}: pick the room from the list (or add it as a new room).")
        if m["room"].lower() in seen:
            raise HTTPException(status_code=400, detail=f"{m['room']} is used for two stations.")
        seen.add(m["room"].lower())
        s["room"], s["icon"] = m["room"], m["icon"]
    colours = [_s(c, 30) for c in body.team_colours][:body.teams]
    if len(set(c.lower() for c in colours if c)) != len([c for c in colours if c]):
        raise HTTPException(status_code=400, detail="Two teams have the same colour.")
    ed = None
    if body.event_date:
        try:
            ed = date.fromisoformat(body.event_date[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="Party date isn't a valid date.")
    kids = body.kids if body.kids and 0 < body.kids <= 500 else None
    who = _s(body.changed_by, 60) or None
    mid = await _match_or_save_matrix(grid, body.teams, body.stations, _s(body.save_matrix_as, 80) or None, who, theme)
    vals = {"lid": body.lead_id, "title": title, "theme": theme, "ed": ed, "mid": mid, "t": body.teams, "s": body.stations, "kids": kids,
            "g": json.dumps(grid), "tc": json.dumps(colours), "ss": json.dumps(setup),
            "host": _s(body.host_name, 60) or None, "fl": _s(body.final_label, 60) or None, "by": who}
    if job_id:
        await _job(job_id)
        await database.execute(
            """UPDATE spy_clue_jobs SET lead_id = :lid, title = :title, theme = :theme, event_date = :ed, matrix_id = :mid,
                   teams = :t, stations = :s, kids = :kids, grid = :g, team_colours = :tc, station_setup = :ss,
                   host_name = :host, final_label = :fl, updated_at = NOW(), updated_by = :by
               WHERE id = :id""", values=dict(vals, id=job_id))
        return job_id
    return await database.execute(
        """INSERT INTO spy_clue_jobs (lead_id, title, theme, event_date, matrix_id, teams, stations, kids, grid, team_colours,
               station_setup, host_name, final_label, created_by, updated_at, updated_by)
           VALUES (:lid, :title, :theme, :ed, :mid, :t, :s, :kids, :g, :tc, :ss, :host, :fl, :by, NOW(), :by) RETURNING id""",
        values=vals)


@router.post("/admin/spy-clues/jobs")
async def admin_create(body: JobIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    return view_of(await _job(await _save(None, body)), True)


@router.post("/admin/spy-clues/jobs/{job_id}")
async def admin_update(job_id: int, body: JobIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    return view_of(await _job(await _save(job_id, body)), True)


class LinkIn(BaseModel):
    mode: str = "party"      # "party": till the end of the day after the party; "days": N days from now
    days: int = 3
    new_token: bool = False  # True = old link stops working, a new one is made


@router.post("/admin/spy-clues/jobs/{job_id}/link")
async def admin_link(job_id: int, body: LinkIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    job = await _job(job_id)
    now = datetime.now(timezone.utc)
    if body.mode == "party" and job.get("event_date"):
        end = datetime.combine(job["event_date"] + timedelta(days=1), datetime.max.time().replace(microsecond=0), IST)
        if end <= now:
            raise HTTPException(status_code=400, detail="That party is over — pick a number of days instead.")
    else:
        end = now + timedelta(days=max(1, min(int(body.days or 3), MAX_LINK_DAYS)))
    end = min(end, now + timedelta(days=MAX_LINK_DAYS))
    token = job.get("token")
    if not token or body.new_token:
        token = secrets.token_urlsafe(24)
    await database.execute(
        "UPDATE spy_clue_jobs SET token = :tok, expires_at = :e, revoked = FALSE WHERE id = :id",
        values={"tok": token, "e": end, "id": job_id})
    return view_of(await _job(job_id), True)


@router.post("/admin/spy-clues/jobs/{job_id}/revoke")
async def admin_revoke(job_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await _job(job_id)
    await database.execute("UPDATE spy_clue_jobs SET revoked = TRUE WHERE id = :id", values={"id": job_id})
    return view_of(await _job(job_id), True)


@router.post("/admin/spy-clues/jobs/{job_id}/reset-ticks")
async def admin_reset(job_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await _job(job_id)
    await database.execute("UPDATE spy_clue_jobs SET progress = '{}'::jsonb WHERE id = :id", values={"id": job_id})
    return view_of(await _job(job_id), True)


@router.post("/admin/spy-clues/jobs/{job_id}/delete")
async def admin_delete(job_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await database.execute("DELETE FROM spy_clue_jobs WHERE id = :id", values={"id": job_id})
    return {"ok": True}


class MatrixIn(BaseModel):
    name: str
    theme: str = "Spy"
    teams: int
    stations: int
    grid: List[List[Any]]
    changed_by: Optional[str] = None


@router.post("/admin/spy-clues/matrices")
async def admin_matrix_save(body: MatrixIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    if not _s(body.name):
        raise HTTPException(status_code=400, detail="Give the matrix a name.")
    grid = check_grid(body.grid, body.teams, body.stations)
    mid = await _match_or_save_matrix(grid, body.teams, body.stations, body.name, _s(body.changed_by, 60) or None,
                                      body.theme if body.theme in THEMES else "Spy")
    return {"id": mid, "matrices": await _matrices()}


@router.post("/admin/spy-clues/matrices/{matrix_id}/archive")
async def admin_matrix_archive(matrix_id: int, x_admin_password: Optional[str] = Header(None)):
    """Hides it from the library; parties that used it keep their own copy of the grid."""
    _admin_only(x_admin_password)
    await database.execute("UPDATE spy_matrices SET archived = TRUE WHERE id = :id", values={"id": matrix_id})
    return {"matrices": await _matrices()}


class RoomIn(BaseModel):
    theme: str
    name: str
    games: List[str] = []
    changed_by: Optional[str] = None


@router.post("/admin/spy-clues/rooms")
async def admin_room_add(body: RoomIn, x_admin_password: Optional[str] = Header(None)):
    """A new standard room for a theme — from then on it's in every party's dropdown."""
    _admin_only(x_admin_password)
    if body.theme not in THEMES:
        raise HTTPException(status_code=400, detail="Unknown theme.")
    name = _s(body.name, 60)
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Type the room name.")
    ex = await database.fetch_one("SELECT id, archived FROM clue_rooms WHERE theme = :t AND lower(name) = lower(:n)",
                                  values={"t": body.theme, "n": name})
    if ex:
        if ex["archived"]:
            await database.execute("UPDATE clue_rooms SET archived = FALSE WHERE id = :id", values={"id": ex["id"]})
    else:
        nxt = await database.fetch_val("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM clue_rooms WHERE theme = :t",
                                       values={"t": body.theme})
        await database.execute(
            """INSERT INTO clue_rooms (theme, name, icon, games, sort_order, created_by)
               VALUES (:t, :n, :i, :g, :o, :by)""",
            values={"t": body.theme, "n": name, "i": icon_for(name),
                    "g": json.dumps([_s(g, 80) for g in body.games if _s(g)][:6]), "o": nxt,
                    "by": _s(body.changed_by, 60) or None})
    return {"rooms": await _rooms()}


# ─── Shilpa's link ─────────────────────────────────────────────────────────

_GONE = "This link has expired. Please ask Shruti or Sid for a new link."
_BAD = "This link is not correct. Please use the link exactly as Shruti or Sid sent it."


async def _live_job(token: str) -> dict:
    job = await _job_by_token(token)
    if not job:
        raise HTTPException(status_code=404, detail=_BAD)
    if link_state(job) != "live":
        raise HTTPException(status_code=410, detail=_GONE)
    return job


@router.get("/spy-clue-job/{token}")
async def public_get(token: str):
    job = await _live_job(token)
    if not job.get("opened_at"):
        await database.execute("UPDATE spy_clue_jobs SET opened_at = NOW() WHERE id = :id", values={"id": job["id"]})
    return view_of(job, False)


class TickIn(BaseModel):
    key: str
    done: bool = True


@router.post("/spy-clue-job/{token}/tick")
async def public_tick(token: str, body: TickIn):
    job = await _live_job(token)
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", body.key or "")
    if not m:
        raise HTTPException(status_code=400, detail="Unknown envelope.")
    t, k = int(m.group(1)), int(m.group(2))
    envs = envelopes_of(job["grid"], job["station_setup"], job.get("host_name") or "", job.get("final_label") or "")
    if not (1 <= t <= len(envs) and 1 <= k <= len(envs[t - 1])):
        raise HTTPException(status_code=400, detail="Unknown envelope.")
    if body.done:
        await database.execute(
            "UPDATE spy_clue_jobs SET progress = progress || jsonb_build_object(CAST(:k AS TEXT), CAST(:v AS TEXT)) WHERE id = :id",
            values={"k": body.key, "v": sig_of(envs[t - 1][k - 1]), "id": job["id"]})
    else:
        await database.execute("UPDATE spy_clue_jobs SET progress = progress - CAST(:k AS TEXT) WHERE id = :id",
                               values={"k": body.key, "id": job["id"]})
    return view_of(await _job(job["id"]), False)
