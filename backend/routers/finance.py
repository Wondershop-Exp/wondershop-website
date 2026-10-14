"""
Finance dashboard API (2026-10-14, per Shruti).

Backs finance.html: P&L, EBITDA, cash flow, event GM%, revenue per FTE.
  GET    /api/admin/finance/costs              all hand-entered costs
  POST   /api/admin/finance/costs              add one
  DELETE /api/admin/finance/costs/{id}         remove one
  GET    /api/admin/finance/snapshot           latest MIS summary (months + events)
  PUT    /api/admin/finance/snapshot           replace it (after uploading a new MIS .xlsx)

ADMIN password only. security.py already blocks the sales login from any
/api/admin path not in SALES_ALLOWED; _admin_only() below double-checks so a
future edit to that list can't open finance up by accident.
"""
import json
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from database import database
from routers.admin import _require_admin

router = APIRouter()

CATEGORIES = {"man", "rent", "elec", "wifi", "mkt", "shopx", "other"}
START_YM = "202610"   # finance tracking starts Oct 2026 (per Shruti)


def _admin_only(pw: Optional[str]):
    if _require_admin(pw) != "admin":
        raise HTTPException(status_code=403, detail="Finance is available to the admin login only.")


class CostIn(BaseModel):
    ym: str = Field(..., min_length=6, max_length=6)
    category: str
    description: Optional[str] = Field(None, max_length=300)
    amount: float = Field(..., gt=0, lt=1e9)
    paid: bool = True
    by: Optional[str] = Field(None, max_length=100)


class SnapshotIn(BaseModel):
    data: dict
    source_name: Optional[str] = Field(None, max_length=300)
    by: Optional[str] = Field(None, max_length=100)


@router.get("/finance/costs")
async def list_costs(x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    rows = await database.fetch_all(
        "SELECT id, ym, category, description, amount, paid, created_by, created_on "
        "FROM finance_costs ORDER BY ym DESC, id DESC")
    return [{**dict(r), "amount": float(r["amount"]), "created_on": r["created_on"].isoformat()} for r in rows]


@router.post("/finance/costs")
async def add_cost(body: CostIn, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    if not re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", body.ym) or body.ym < START_YM:
        raise HTTPException(status_code=400, detail="Month must be Oct 2026 or later.")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category.")
    new_id = await database.execute(
        "INSERT INTO finance_costs (ym, category, description, amount, paid, created_by) "
        "VALUES (:ym, :c, :d, :a, :p, :by) RETURNING id",
        {"ym": body.ym, "c": body.category, "d": (body.description or "").strip() or None,
         "a": body.amount, "p": body.paid, "by": (body.by or "").strip() or None})
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
