"""
Partners & Expenses per booking — 2026-10-12, per Shruti.

"one activity can have many volunteers ... for spy, we have 4-8 stations,
every station can have 1-2 volunteers - shall we track the volunteers for
every event? ... we can also add payment", then (same day): "we don't need
to distinguish between vendor and volunteer. Let everyone be a partner ...
The new section should cover everything - decor, music, volunteers, cake,
activities/engagement, mascot, etc. ... Basically any cost for an event that
we want to link to this event should come up here - including transport,
printing or any other additional cost ... rename person to partner ... would
like to track all expenses in this section against the event" (replacing the
team's expense sheet: supplier, bill amount, date, paid in, tag, remarks).

One row per cost: partner (from the partners list, or any name — "Porter",
"Petrol"), category (Host / Volunteer / Decor / Transport / Printing ...,
open-ended), details (activity, station, what it was for), bill date, amount,
and how it was paid (Pending / Gpay / Cash / ...). Saved as a whole list.

ADMIN ONLY — payouts are hidden from the sales team: these endpoints are not
in security.SALES_ALLOWED (the sales password gets a 403 before reaching
them) and admin.html doesn't render the section for the sales login.

Table event_team (migration 049).
  GET  /api/admin/event-team/{lead_id}
  POST /api/admin/event-team/{lead_id}   {rows:[...], changed_by}
Host rows also name the host(s) on the feedback form (routers/feedback.py).
"""
import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str

logger = logging.getLogger(__name__)
router = APIRouter()

# Suggestions only — any other category can be typed in.
CATEGORIES = ["Host", "Volunteer", "Lead volunteer", "Activity", "Decor", "Music", "Cake", "Mascot",
              "Photographer", "Social media", "Return gifts", "Printing", "Transport", "Food",
              "Materials", "Other"]
PAID_VIA = ["Pending", "Gpay", "Cash", "Bank transfer", "UPI (other)", "Card"]


def _num(v):
    try:
        return None if v in (None, "") else round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _date(v) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Bill date must be a date (YYYY-MM-DD).")


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
            "id": r["id"], "partner": r["person_name"], "category": r["role"], "details": r["assigned_to"],
            "bill_date": r["bill_date"].isoformat() if r.get("bill_date") else None,
            "amount": float(r["amount"]) if r["amount"] is not None else None,
            "paid_via": r.get("paid_via") or ("Paid" if r["paid"] else "Pending"),
            "paid": bool(r["paid"]), "paid_at": _to_ist_str(r["paid_at"]),
        })
    return out


async def host_names(lead_id: int) -> Optional[str]:
    names = [r["partner"] for r in await team_rows(lead_id) if (r["category"] or "").strip().lower() == "host"]
    names = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not names:
        return None
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def _summary(rows: list) -> dict:
    total = sum(r["amount"] or 0 for r in rows)
    paid = sum(r["amount"] or 0 for r in rows if r["paid"])
    return {"rows": len(rows), "total": round(total, 2), "paid": round(paid, 2), "pending": round(total - paid, 2)}


@router.get("/admin/event-team/{lead_id}")
async def get_team(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Partners & Expenses is for admins only.")
    rows = await team_rows(lead_id)
    return {"rows": rows, "categories": CATEGORIES, "paid_via": PAID_VIA, "summary": _summary(rows)}


class TeamRow(BaseModel):
    partner: Optional[str] = None
    category: Optional[str] = None
    details: Optional[str] = None
    bill_date: Optional[str] = None
    amount: Optional[float] = None
    paid_via: Optional[str] = None


class TeamSave(BaseModel):
    rows: List[TeamRow] = []
    changed_by: str = ""


@router.post("/admin/event-team/{lead_id}")
async def save_team(lead_id: int, body: TeamSave, x_admin_password: Optional[str] = Header(None)):
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Partners & Expenses is for admins only.")
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
        name = (r.partner or "").strip()
        if not name and r.amount in (None, 0):
            continue   # empty row
        if not name:
            raise HTTPException(status_code=400, detail="Every row with an amount needs a partner / payee name.")
        if r.amount is not None and r.amount < 0:
            raise HTTPException(status_code=400, detail=f"Amount can't be negative ({name}).")
        clean.append(r)
    now = datetime.utcnow()
    async with database.transaction():
        await database.execute("DELETE FROM event_team WHERE lead_id = :id", values={"id": lead_id})
        for i, r in enumerate(clean):
            name = (r.partner or "").strip()[:120]
            cat = (r.category or "").strip()[:40] or None
            det = (r.details or "").strip()[:300] or None
            via = (r.paid_via or "").strip()[:30] or "Pending"
            paid = via.lower() != "pending"
            paid_at = (old_paid.get((name, cat, det)) or now) if paid else None
            await database.execute(
                """INSERT INTO event_team (lead_id, sort_order, person_name, role, assigned_to, bill_date, amount,
                                           paid_via, paid, paid_at, updated_by, updated_at)
                   VALUES (:lid, :i, :n, :cat, :det, :bd, :a, :via, :p, :pa, :by, :now)""",
                values={"lid": lead_id, "i": i, "n": name, "cat": cat, "det": det, "bd": _date(r.bill_date),
                        "a": _num(r.amount), "via": via, "p": paid, "pa": paid_at, "by": who[:80], "now": now})
    logger.info(f"Lead #{lead_id}: partners & expenses saved ({len(clean)} rows) by {who}")
    return await get_team(lead_id, x_admin_password)


# ─── one-time carry-over of the old "Assigned Value" partners ──────────────
# 2026-10-12 — the partner pickers on the Decor / Host / Music / Photography /
# Activities / Gifts rows are replaced by this section. Existing assignments
# are copied in once (no amounts), for bookings that have no rows here yet.
ASSIGN_CATEGORY = {"svc_decor": "Decor", "svc_host": "Host", "svc_dj": "Music", "svc_photo": "Photographer",
                   "svc_activities": "Activity", "svc_gifts": "Return gifts"}


async def carry_over_assignments() -> None:
    flag = "event_team_from_assignments_v1"
    if await database.fetch_one("SELECT key FROM app_flags WHERE key = :k", values={"k": flag}):
        return
    rows = await database.fetch_all(
        "SELECT lead_id, field_key, assigned_value FROM booking_field_overrides "
        "WHERE field_key = ANY(:keys) AND removed = FALSE AND COALESCE(TRIM(assigned_value), '') <> ''",
        values={"keys": list(ASSIGN_CATEGORY)})
    by_lead = {}
    for r in rows:
        cat = ASSIGN_CATEGORY[r["field_key"]]
        av = r["assigned_value"].strip()
        if r["field_key"] in ("svc_activities", "svc_gifts"):
            for seg in av.split(";"):            # "Slime: Ravi; Tattoo: Maira"
                item, _, who = seg.partition(":")
                if who.strip():
                    by_lead.setdefault(r["lead_id"], []).append((who.strip(), cat, item.strip() or None))
        else:
            by_lead.setdefault(r["lead_id"], []).append((av, cat, None))
    added = 0
    for lead_id, items in by_lead.items():
        if await database.fetch_one("SELECT 1 FROM event_team WHERE lead_id = :id LIMIT 1", values={"id": lead_id}):
            continue
        for i, (name, cat, det) in enumerate(items):
            await database.execute(
                """INSERT INTO event_team (lead_id, sort_order, person_name, role, assigned_to, paid_via, paid, updated_by)
                   VALUES (:lid, :i, :n, :c, :d, 'Pending', FALSE, 'carried over')""",
                values={"lid": lead_id, "i": i, "n": name[:120], "c": cat, "d": det})
            added += 1
    await database.execute("INSERT INTO app_flags (key) VALUES (:k) ON CONFLICT DO NOTHING", values={"k": flag})
    logger.info(f"Partners & Expenses: carried over {added} assigned partner(s)")
