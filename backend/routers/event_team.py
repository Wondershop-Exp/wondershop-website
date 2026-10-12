"""
Event team per booking — 2026-10-12, per Shruti: "one activity can have many
volunteers. Example: for higher no. of kids, we might need 2 volunteers ...
for spy, we have 4-8 stations, every station can have 1-2 volunteers - shall
we track the volunteers for every event? ... we can also add payment".
Pay varies by person (fixed amount, typed per person; hours optional, for
reference); tracking is Amount + Paid / Pending.

Table event_team (migration 049). The booking page's "Event Team" card loads
the list and saves it back whole (simple to edit: add / remove rows, Save).
  GET  /api/admin/event-team/{lead_id}
  POST /api/admin/event-team/{lead_id}   {rows:[...], changed_by}
Host rows also feed the host name(s) on the feedback form (routers/feedback.py).
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str

logger = logging.getLogger(__name__)
router = APIRouter()

ROLES = ["Host", "Volunteer", "Station volunteer", "Lead volunteer", "Decor", "Music / DJ",
         "Photographer", "Mascot", "Other"]


def _num(v):
    try:
        return None if v in (None, "") else round(float(v), 2)
    except (TypeError, ValueError):
        return None


async def team_rows(lead_id: int) -> list:
    try:
        rows = await database.fetch_all(
            "SELECT * FROM event_team WHERE lead_id = :id ORDER BY sort_order, id", values={"id": lead_id})
    except Exception:
        logger.exception("event_team read failed (run migration 049?)")
        return []
    out = []
    for r in rows:
        r = dict(r)
        out.append({
            "id": r["id"], "person_name": r["person_name"], "role": r["role"], "assigned_to": r["assigned_to"],
            "hours": float(r["hours"]) if r["hours"] is not None else None,
            "amount": float(r["amount"]) if r["amount"] is not None else None,
            "paid": bool(r["paid"]), "paid_at": _to_ist_str(r["paid_at"]), "notes": r["notes"],
        })
    return out


async def host_names(lead_id: int) -> Optional[str]:
    names = [r["person_name"] for r in await team_rows(lead_id) if (r["role"] or "") == "Host"]
    names = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not names:
        return None
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def _summary(rows: list) -> dict:
    total = sum(r["amount"] or 0 for r in rows)
    paid = sum(r["amount"] or 0 for r in rows if r["paid"])
    return {"people": len({(r["person_name"] or "").strip().lower() for r in rows if r["person_name"]}),
            "total": round(total, 2), "paid": round(paid, 2), "pending": round(total - paid, 2)}


@router.get("/admin/event-team/{lead_id}")
async def get_team(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    rows = await team_rows(lead_id)
    return {"rows": rows, "roles": ROLES, "summary": _summary(rows)}


class TeamRow(BaseModel):
    person_name: Optional[str] = None
    role: Optional[str] = None
    assigned_to: Optional[str] = None
    hours: Optional[float] = None
    amount: Optional[float] = None
    paid: bool = False
    notes: Optional[str] = None


class TeamSave(BaseModel):
    rows: List[TeamRow] = []
    changed_by: str = ""


@router.post("/admin/event-team/{lead_id}")
async def save_team(lead_id: int, body: TeamSave, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    who = (body.changed_by or "").strip()
    if not who:
        raise HTTPException(status_code=400, detail="changed_by is required.")
    if not await database.fetch_one("SELECT lead_id FROM leads WHERE lead_id = :id", values={"id": lead_id}):
        raise HTTPException(status_code=404, detail="Booking not found.")
    # Original "paid on" times, kept while a row stays paid.
    old_paid = {}
    for r in await database.fetch_all(
            "SELECT person_name, role, assigned_to, paid_at FROM event_team WHERE lead_id = :id AND paid",
            values={"id": lead_id}):
        old_paid[(r["person_name"], r["role"], r["assigned_to"])] = r["paid_at"]
    clean = []
    for r in body.rows:
        name = (r.person_name or "").strip()
        if not name:
            continue
        for v, label in ((r.amount, "Amount"), (r.hours, "Hours")):
            if v is not None and v < 0:
                raise HTTPException(status_code=400, detail=f"{label} can't be negative ({name}).")
        clean.append(r)
    now = datetime.utcnow()
    async with database.transaction():
        await database.execute("DELETE FROM event_team WHERE lead_id = :id", values={"id": lead_id})
        for i, r in enumerate(clean):
            name = (r.person_name or "").strip()[:120]
            role = (r.role or "").strip()[:40] or None
            to = (r.assigned_to or "").strip()[:200] or None
            paid_at = (old_paid.get((name, role, to)) or now) if r.paid else None
            await database.execute(
                """INSERT INTO event_team (lead_id, sort_order, person_name, role, assigned_to, hours, amount,
                                           paid, paid_at, notes, updated_by, updated_at)
                   VALUES (:lid, :i, :n, :role, :to, :h, :a, :p, :pa, :notes, :by, :now)""",
                values={"lid": lead_id, "i": i, "n": name, "role": role, "to": to,
                        "h": _num(r.hours), "a": _num(r.amount), "p": bool(r.paid), "pa": paid_at,
                        "notes": (r.notes or "").strip()[:500] or None, "by": who[:80], "now": now})
    logger.info(f"Lead #{lead_id}: event team saved ({len(clean)} rows) by {who}")
    return await get_team(lead_id, x_admin_password)
