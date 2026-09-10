"""
Vendor Master admin API (2026-09-10, per Shruti — "update the vendor
master... and link it to the admin panel"). Wraps vendor_master, first
populated from Shruti's supplier-tracking spreadsheet (see
backend/scripts/import_vendor_master.py and
migrations/022_relax_vendor_master_mobile.sql for the import itself).

Deliberately plain CRUD — vendor_master has none of the booking pages'
override/change-log machinery (booking_field_overrides, booking_change_log).
It's a straight team-maintained directory: what you save is what's there,
no "customer's choice vs assigned value" distinction, because there's no
customer-submitted original to preserve here.

duplicate_of_id already exists on the table (flagging a row as a dupe of
another vendor) but has no UI here yet — every row from the first import
had it blank; Shruti will be finding dupes by hand as she cleans this up,
so a proper "mark as duplicate of..." picker is a natural follow-up once
that becomes a real workflow rather than a hypothetical one.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str

router = APIRouter()
logger = logging.getLogger(__name__)

VENDOR_FIELDS = [
    "name", "primary_contact_name", "primary_mobile", "alternate_mobile",
    "whatsapp_number", "email", "deals_in", "address", "city", "pincode",
    "timings", "website", "remarks", "is_active",
]


class VendorRequest(BaseModel):
    name: str
    primary_contact_name: Optional[str] = None
    primary_mobile: Optional[str] = None
    alternate_mobile: Optional[str] = None
    whatsapp_number: Optional[str] = None
    email: Optional[str] = None
    deals_in: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    timings: Optional[str] = None
    website: Optional[str] = None
    remarks: Optional[str] = None
    is_active: bool = True


def _row_out(r) -> dict:
    d = dict(r)
    d["created_on_ist"] = _to_ist_str(d.pop("created_on", None))
    d["updated_on_ist"] = _to_ist_str(d.pop("updated_on", None))
    return d


def _values_for_write(body: VendorRequest) -> dict:
    v = body.dict()
    v["name"] = v["name"].strip()
    return v


@router.get("/vendors")
async def list_vendors(q: Optional[str] = None, active_only: bool = False,
                        x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    where = []
    values: dict = {}
    if q:
        where.append(
            "(name ILIKE :q OR primary_contact_name ILIKE :q OR primary_mobile ILIKE :q "
            "OR alternate_mobile ILIKE :q OR whatsapp_number ILIKE :q OR email ILIKE :q "
            "OR deals_in ILIKE :q OR city ILIKE :q OR address ILIKE :q)"
        )
        values["q"] = f"%{q}%"
    if active_only:
        where.append("is_active = TRUE")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = await database.fetch_all(
        f"SELECT * FROM vendor_master {where_sql} ORDER BY name ASC",
        values=values,
    )
    return {"vendors": [_row_out(r) for r in rows], "total": len(rows)}


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one("SELECT * FROM vendor_master WHERE vendor_id = :id", {"id": vendor_id})
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return _row_out(row)


@router.post("/vendors")
async def create_vendor(body: VendorRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")
    values = _values_for_write(body)
    cols = ", ".join(VENDOR_FIELDS)
    placeholders = ", ".join(f":{k}" for k in VENDOR_FIELDS)
    row = await database.fetch_one(
        f"INSERT INTO vendor_master ({cols}) VALUES ({placeholders}) RETURNING *",
        values,
    )
    return _row_out(row)


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: int, body: VendorRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")
    existing = await database.fetch_one("SELECT vendor_id FROM vendor_master WHERE vendor_id = :id", {"id": vendor_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    values = _values_for_write(body)
    set_clause = ", ".join(f"{k} = :{k}" for k in VENDOR_FIELDS)
    values["id"] = vendor_id
    row = await database.fetch_one(
        f"UPDATE vendor_master SET {set_clause} WHERE vendor_id = :id RETURNING *",
        values,
    )
    return _row_out(row)
