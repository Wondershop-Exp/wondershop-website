"""
Finance dashboard API (2026-10-14, per Shruti).

Backs finance.html: P&L, EBITDA, cash flow, event GM%, revenue per FTE.
  GET    /api/admin/finance/costs              all hand-entered costs
  POST   /api/admin/finance/costs              add one
  DELETE /api/admin/finance/costs/{id}         remove one
  POST   /api/admin/finance/costs/{id}/paid    change payment mode (Pending = unpaid)
  GET    /api/admin/finance/snapshot           latest MIS summary (months + events)
  PUT    /api/admin/finance/snapshot           replace it (after uploading a new MIS .xlsx)

ADMIN password only. security.py already blocks the sales login from any
/api/admin path not in SALES_ALLOWED; _admin_only() below double-checks so a
future edit to that list can't open finance up by accident.
"""
import json
from datetime import date
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from database import database
from routers.admin import _require_admin

router = APIRouter()

PAID_VIA = ["Pending", "Gpay", "Cash", "Bank transfer", "UPI (other)", "Card"]   # same as event_team
# "owner" = money put in by the co-founders/owners (2026-10-28): not a cost - shown
# under Financing in the cash flow, never in the P&L.
CATEGORIES = {"man", "rent", "elec", "wifi", "mkt", "shopx", "other", "owner"}
START_YM = "202610"   # finance tracking starts Oct 2026 (per Shruti)


def _admin_only(pw: Optional[str]):
    if _require_admin(pw) != "admin":
        raise HTTPException(status_code=403, detail="Finance is available to the admin login only.")


# 2026-10-16 — marketing costs carry a lead source (Finance = single source of
# truth for the Sales Dashboard's spend). Default from an obvious partner.
LEAD_SOURCE_RULES = [(r"facebook|instagram|meta|aisensy", "Instagram"), (r"google", "Google"),
                     (r"wonderfest", "Wonderfest Feb 2026"), (r"rotary", "Powai Rotary Christmas Stall 2025")]


def default_lead_source(partner: Optional[str]) -> Optional[str]:
    for rx, src in LEAD_SOURCE_RULES:
        if partner and re.search(rx, partner, re.I):
            return src
    return None


class CostIn(BaseModel):
    ym: Optional[str] = Field(None, min_length=6, max_length=6)
    spent_on: Optional[str] = None          # YYYY-MM-DD (2026-10-16); ym is derived from it
    lead_source: Optional[str] = Field(None, max_length=100)
    paid: Optional[bool] = None             # older page versions sent a tick instead of paid_via
    category: str
    description: Optional[str] = Field(None, max_length=300)
    amount: float = Field(..., gt=0, lt=1e9)
    paid_via: str = "Pending"
    partner: Optional[str] = Field(None, max_length=200)
    by: Optional[str] = Field(None, max_length=100)


class SnapshotIn(BaseModel):
    data: dict
    source_name: Optional[str] = Field(None, max_length=300)
    by: Optional[str] = Field(None, max_length=100)


@router.get("/finance/costs")
async def list_costs(x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    rows = await database.fetch_all(
        "SELECT id, ym, spent_on, category, partner, lead_source, description, amount, paid, COALESCE(paid_via, CASE WHEN paid THEN 'Paid' ELSE 'Pending' END) AS paid_via, created_by, created_on "
        "FROM finance_costs ORDER BY COALESCE(spent_on, to_date(ym || '01', 'YYYYMMDD')) DESC, id DESC")
    return [{**dict(r), "amount": float(r["amount"]), "created_on": r["created_on"].isoformat(),
             "spent_on": r["spent_on"].isoformat() if r["spent_on"] else None} for r in rows]


@router.post("/finance/costs")
async def add_cost(body: CostIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    spent_on = None
    if body.spent_on:
        try:
            spent_on = date.fromisoformat(body.spent_on[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD.")
        body.ym = spent_on.strftime("%Y%m")
    elif body.ym and re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", body.ym):
        spent_on = date(int(body.ym[:4]), int(body.ym[4:]), 1)
    if body.paid is not None and body.paid_via == "Pending" and body.paid:
        body.paid_via = "Bank transfer"
    if not body.ym or not re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", body.ym) or body.ym < START_YM:
        raise HTTPException(status_code=400, detail="Month must be Oct 2026 or later.")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category.")
    if body.paid_via not in PAID_VIA:
        raise HTTPException(status_code=400, detail="Unknown payment mode.")
    new_id = await database.execute(
        "INSERT INTO finance_costs (ym, spent_on, category, partner, lead_source, description, amount, paid, paid_via, created_by) "
        "VALUES (:ym, :so, :c, :pt, :ls, :d, :a, :p, :pv, :by) RETURNING id",
        {"ym": body.ym, "so": spent_on,
         "ls": ((body.lead_source or "").strip() or default_lead_source(body.partner)) if body.category == "mkt" else None,
         "c": body.category, "pt": (body.partner or "").strip() or None, "d": (body.description or "").strip() or None,
         "a": body.amount, "p": body.paid_via != "Pending", "pv": body.paid_via, "by": (body.by or "").strip() or None})
    return {"id": new_id}


@router.delete("/finance/costs/{cost_id}")
async def delete_cost(cost_id: int, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await database.execute("DELETE FROM finance_costs WHERE id = :id", {"id": cost_id})
    return {"ok": True}


@router.get("/finance/snapshot")
async def get_snapshot(x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    r = await database.fetch_one("SELECT data, source_name, updated_by, updated_on FROM finance_snapshot WHERE id = 1")
    if not r:
        return {"data": None}
    data = r["data"]
    if isinstance(data, str):
        data = json.loads(data)
    return {"data": data, "source_name": r["source_name"], "updated_by": r["updated_by"],
            "updated_on": r["updated_on"].isoformat()}


@router.put("/finance/snapshot")
async def put_snapshot(body: SnapshotIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    await database.execute(
        "INSERT INTO finance_snapshot (id, data, source_name, updated_by, updated_on) "
        "VALUES (1, CAST(:d AS JSONB), :s, :by, now()) "
        "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, source_name = EXCLUDED.source_name, "
        "updated_by = EXCLUDED.updated_by, updated_on = now()",
        {"d": json.dumps(body.data), "s": body.source_name, "by": (body.by or "").strip() or None})
    return {"ok": True}


@router.get("/finance/bookings")
async def finance_bookings(x_admin_password: Optional[str] = Header(None)):
    """Birthday bookings (Oct 2026 on, not cancelled) with the SAME figures the
    booking page shows (2026-10-28, per Shruti - the stored client_budget was
    stale): Grand Total is priced live by routers.admin.get_booking_detail,
    client paid = Advance Paid + Event Payment Confirmed, and costs = every
    row of that booking's Partners & Expenses (event_team)."""
    _admin_only(x_admin_password)
    from routers.admin import get_booking_detail
    from routers.event_team import team_rows
    ids = await database.fetch_all(
        "SELECT lead_id FROM leads WHERE is_booking = TRUE AND status != 'Cancelled' AND event_date >= :start "
        "ORDER BY event_date DESC",
        values={"start": date(int(START_YM[:4]), int(START_YM[4:]), 1)})

    def f(v):
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip()) if v not in (None, "") else 0.0
        except ValueError:
            return 0.0
    out = []
    for r in ids:
        lid = r["lead_id"]
        d = await get_booking_detail(lid, x_admin_password)
        fl = {x["field_key"]: x for sec in (d.get("sections") or []) for x in (sec.get("fields") or [])} \
            if isinstance(d.get("sections"), list) else \
            {x["field_key"]: x for xs in (d.get("sections") or {}).values() for x in xs}

        def val(k):
            x = fl.get(k) or {}
            return None if x.get("removed") else x.get("customer_choice")
        lead = await database.fetch_one("SELECT parent_name, child_names, event_date FROM leads WHERE lead_id = :id", values={"id": lid})
        rows = await team_rows(lid)
        cost = sum(x["amount"] or 0 for x in rows)
        unpaid = sum(x["amount"] or 0 for x in rows if (x.get("paid_via") or "Pending") == "Pending" and not x.get("paid"))
        advance, final = f(val("bill_advance")), f(val("event_payment_confirmed_amount"))
        ev = lead["event_date"]
        out.append({
            "lead_id": lid, "parent": lead["parent_name"], "child": lead["child_names"],
            "date": ev.isoformat() if ev else None, "ym": ev.strftime("%Y%m") if ev else None,
            "revenue": f(val("bill_grand_total")),
            "advance": advance, "final_payment": final, "paid_amount": advance + final,
            "paid_mode": val("event_payment_confirmed_mode"),
            "cost": round(cost, 2), "cost_unpaid": round(unpaid, 2), "cost_lines": len(rows),
            "costs": [{"partner": x["partner"], "category": x["category"], "amount": x["amount"], "paid_via": x["paid_via"]} for x in rows],
        })
    return out


class PaidIn(BaseModel):
    paid_via: str


@router.post("/finance/costs/{cost_id}/paid")
async def set_cost_paid(cost_id: int, body: PaidIn, x_admin_password: Optional[str] = Header(None)):
    """Change how a cost was paid ('Pending' = unpaid)."""
    _admin_only(x_admin_password)
    if body.paid_via not in PAID_VIA:
        raise HTTPException(status_code=400, detail="Unknown payment mode.")
    await database.execute("UPDATE finance_costs SET paid_via = :v, paid = :p WHERE id = :id",
                           {"v": body.paid_via, "p": body.paid_via != "Pending", "id": cost_id})
    return {"ok": True}


class LeadSourceIn(BaseModel):
    lead_source: Optional[str] = Field(None, max_length=100)


@router.post("/finance/costs/{cost_id}/lead-source")
async def set_cost_lead_source(cost_id: int, body: LeadSourceIn, x_admin_password: Optional[str] = Header(None)):
    """Set / change the lead source of a marketing cost (2026-10-16). Empty = brand / general."""
    _admin_only(x_admin_password)
    await database.execute("UPDATE finance_costs SET lead_source = :s WHERE id = :id AND category = 'mkt'",
                           {"s": (body.lead_source or "").strip() or None, "id": cost_id})
    return {"ok": True}
