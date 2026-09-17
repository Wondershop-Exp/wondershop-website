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

2026-09-17, per Shruti — vendor onboarding: vendors now also arrive here
via the public form in routers/vendor_onboarding.py (bank/payment details
+ an optional cancelled-cheque upload — see migrations/031_vendor_
onboarding.sql), landing as an ordinary row here, just inactive and
flagged onboarding_source='self_submitted' / onboarding_reviewed=FALSE
until a team member opens and saves it. cancelled_cheque_file is BYTEA and
deliberately never selected in the list/get JSON responses below (it's
fetched raw, once, only by the dedicated download endpoint at the bottom)
— both to keep the list/detail responses light and because raw bytes
can't serialize into JSON anyway.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str

router = APIRouter()
logger = logging.getLogger(__name__)

VENDOR_FIELDS = [
    "name", "primary_contact_name", "primary_mobile", "alternate_mobile",
    "whatsapp_number", "email", "deals_in", "address", "city", "pincode",
    "timings", "website", "remarks", "is_active",
    "bank_account_holder_name", "bank_name", "bank_account_number", "bank_ifsc_code",
]

# Explicit column list for reads — everything EXCEPT the bytea file itself,
# which only the dedicated /cancelled-cheque endpoint below ever fetches.
VENDOR_READ_COLUMNS = VENDOR_FIELDS + [
    "vendor_id", "duplicate_of_id", "created_on", "updated_on",
    "onboarding_source", "onboarding_reviewed", "submitted_on",
    "cancelled_cheque_filename", "cancelled_cheque_content_type",
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
    bank_account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc_code: Optional[str] = None


def _row_out(r) -> dict:
    d = dict(r)
    d["created_on_ist"] = _to_ist_str(d.pop("created_on", None))
    d["updated_on_ist"] = _to_ist_str(d.pop("updated_on", None))
    d["submitted_on_ist"] = _to_ist_str(d.pop("submitted_on", None))
    d["has_cancelled_cheque"] = bool(d.get("cancelled_cheque_filename"))
    return d


def _values_for_write(body: VendorRequest) -> dict:
    v = body.dict()
    v["name"] = v["name"].strip()
    if v.get("bank_ifsc_code"):
        v["bank_ifsc_code"] = v["bank_ifsc_code"].strip().upper() or None
    return v


@router.get("/vendors")
async def list_vendors(q: Optional[str] = None, active_only: bool = False, pending_review: bool = False,
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
    if pending_review:
        where.append("onboarding_reviewed = FALSE")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(VENDOR_READ_COLUMNS)
    rows = await database.fetch_all(
        f"SELECT {cols} FROM vendor_master {where_sql} ORDER BY onboarding_reviewed ASC, name ASC",
        values=values,
    )
    pending_row = await database.fetch_one(
        "SELECT COUNT(*) AS cnt FROM vendor_master WHERE onboarding_reviewed = FALSE"
    )
    return {"vendors": [_row_out(r) for r in rows], "total": len(rows), "pending_review_count": pending_row["cnt"] or 0}


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    cols = ", ".join(VENDOR_READ_COLUMNS)
    row = await database.fetch_one(f"SELECT {cols} FROM vendor_master WHERE vendor_id = :id", {"id": vendor_id})
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return _row_out(row)


@router.get("/vendors/{vendor_id}/cancelled-cheque")
async def get_vendor_cancelled_cheque(vendor_id: int, x_admin_password: Optional[str] = Header(None)):
    """Streams back the raw file a vendor uploaded through the public
    onboarding form (or one added by hand later, if that's ever wired up).
    Admin-only, like everything else here — this is the one place the raw
    bytea column is actually read."""
    _require_admin(x_admin_password)
    row = await database.fetch_one(
        "SELECT cancelled_cheque_file, cancelled_cheque_filename, cancelled_cheque_content_type "
        "FROM vendor_master WHERE vendor_id = :id",
        {"id": vendor_id},
    )
    if not row or not row["cancelled_cheque_file"]:
        raise HTTPException(status_code=404, detail="No file on file for this vendor.")
    filename = row["cancelled_cheque_filename"] or "cancelled-cheque"
    content_type = row["cancelled_cheque_content_type"] or "application/octet-stream"
    return Response(
        content=bytes(row["cancelled_cheque_file"]),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/vendors")
async def create_vendor(body: VendorRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")
    values = _values_for_write(body)
    cols = ", ".join(VENDOR_FIELDS)
    placeholders = ", ".join(f":{k}" for k in VENDOR_FIELDS)
    read_cols = ", ".join(VENDOR_READ_COLUMNS)
    row = await database.fetch_one(
        f"INSERT INTO vendor_master ({cols}) VALUES ({placeholders}) RETURNING {read_cols}",
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
    # Any admin save reviews the record — whether they activate it or
    # deliberately leave it inactive, it's no longer "pending review"
    # (2026-09-17, per the vendor-onboarding self-submission flow above).
    set_clause = ", ".join(f"{k} = :{k}" for k in VENDOR_FIELDS) + ", onboarding_reviewed = TRUE"
    values["id"] = vendor_id
    read_cols = ", ".join(VENDOR_READ_COLUMNS)
    row = await database.fetch_one(
        f"UPDATE vendor_master SET {set_clause} WHERE vendor_id = :id RETURNING {read_cols}",
        values,
    )
    return _row_out(row)
