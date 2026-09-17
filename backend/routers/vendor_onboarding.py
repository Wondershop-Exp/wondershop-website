"""
Public vendor onboarding form (2026-09-17, per Shruti — "create vendor
onboarding form... We'll ask the details from the vendor, including
uploading a cancelled check or adding account details for payment").

No admin password required — this is a public-facing router, like
leads.py's /submit, meant to be hit by a vendor filling in vendor-
onboarding.html from a link the team sends them, not by anyone signed into
the admin panel.

A submission lands as an ordinary vendor_master row — inactive, flagged
onboarding_source='self_submitted' / onboarding_reviewed=FALSE — so it
shows up in admin.html's existing Vendors tab (sorted to the top, with a
"Pending review" badge) rather than needing a separate review screen. See
migrations/031_vendor_onboarding.sql for the columns this writes to, and
routers/vendors.py for the admin-side read/review endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException

from database import database

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB — comfortably fits a phone photo or scanned page
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _clean(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()
    return s or None


def _normalize_mobile(raw: Optional[str]) -> Optional[str]:
    """Strips spaces/dashes/+ and a leading '91' country code so '+91
    98765 43210', '091-98765-43210', and '9876543210' all normalize to the
    same 10-digit value — matches primary_mobile's VARCHAR(10) column."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    # Defensive cap, not validation — alternate_mobile/whatsapp_number are
    # optional and only lightly cleaned (unlike primary_mobile, which is
    # hard-validated to exactly 10 digits below); this just stops a stray
    # long paste from overflowing the column's VARCHAR(10) and 500-ing.
    return digits[:10]


@router.post("/submit")
async def submit_vendor_onboarding(
    name: str = Form(...),
    primary_contact_name: Optional[str] = Form(None),
    primary_mobile: str = Form(...),
    alternate_mobile: Optional[str] = Form(None),
    whatsapp_number: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    deals_in: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    bank_account_holder_name: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account_number: Optional[str] = Form(None),
    bank_ifsc_code: Optional[str] = Form(None),
    preferred_payment_mode: Optional[str] = Form(None),
    gst_number: Optional[str] = Form(None),
    cancelled_cheque: Optional[UploadFile] = File(None),
):
    name = _clean(name)
    if not name:
        raise HTTPException(status_code=400, detail="Business/vendor name is required.")

    mobile = _normalize_mobile(primary_mobile)
    if len(mobile) != 10:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")

    bank_account_holder_name = _clean(bank_account_holder_name)
    bank_name = _clean(bank_name)
    bank_account_number = _clean(bank_account_number)
    bank_ifsc_code = _clean(bank_ifsc_code)
    if bank_ifsc_code:
        bank_ifsc_code = bank_ifsc_code.upper()
        if len(bank_ifsc_code) != 11:
            raise HTTPException(status_code=400, detail="IFSC code should be 11 characters (e.g. HDFC0001234).")
    has_full_bank_details = bool(
        bank_account_holder_name and bank_name and bank_account_number and bank_ifsc_code
    )

    # Optional — "cash" or "gpay" per Shruti (2026-09-17, "add preferred
    # payment mode - cash / gpay"). Blank/omitted is fine; anything else
    # is rejected rather than silently dropped, so a typo in a future
    # frontend build fails loudly instead of writing garbage.
    preferred_payment_mode = _clean(preferred_payment_mode)
    if preferred_payment_mode:
        preferred_payment_mode = preferred_payment_mode.lower()
        if preferred_payment_mode not in ("cash", "gpay"):
            raise HTTPException(status_code=400, detail="Preferred payment mode must be Cash or GPay.")

    # Optional GSTIN (2026-09-17, "ask for gst info as well - optional").
    # Only length-checked when given, same as IFSC — GSTIN format/checksum
    # validation isn't worth the false-rejection risk on a vendor's phone.
    gst_number = _clean(gst_number)
    if gst_number:
        gst_number = gst_number.upper()
        if len(gst_number) != 15:
            raise HTTPException(status_code=400, detail="GST number should be 15 characters.")

    file_bytes = None
    file_name = None
    file_content_type = None
    if cancelled_cheque is not None and cancelled_cheque.filename:
        file_content_type = cancelled_cheque.content_type
        if file_content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="The file must be a JPG, PNG, or PDF.")
        raw = await cancelled_cheque.read()
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="That file is too large — please keep it under 5MB.")
        if raw:
            file_bytes = raw
            file_name = cancelled_cheque.filename[:255]

    # Per Shruti: "uploading a cancelled check OR adding account details" —
    # either is an acceptable way to capture payment info, but the vendor
    # must give at least one of the two, or there's nothing to pay them
    # against.
    if not has_full_bank_details and not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Please either upload a cancelled cheque/passbook photo, or fill in all four bank account fields.",
        )

    values = {
        "name": name,
        "primary_contact_name": _clean(primary_contact_name),
        "primary_mobile": mobile,
        "alternate_mobile": _normalize_mobile(alternate_mobile) or None,
        "whatsapp_number": _normalize_mobile(whatsapp_number) or None,
        "email": _clean(email),
        "deals_in": _clean(deals_in),
        "address": _clean(address),
        "city": _clean(city),
        "pincode": _clean(pincode),
        "bank_account_holder_name": bank_account_holder_name,
        "bank_name": bank_name,
        "bank_account_number": bank_account_number,
        "bank_ifsc_code": bank_ifsc_code,
        "preferred_payment_mode": preferred_payment_mode,
        "gst_number": gst_number,
        "cancelled_cheque_file": file_bytes,
        "cancelled_cheque_filename": file_name,
        "cancelled_cheque_content_type": file_content_type if file_bytes else None,
    }
    cols = ", ".join(values.keys())
    placeholders = ", ".join(f":{k}" for k in values.keys())
    await database.execute(
        f"""INSERT INTO vendor_master
              ({cols}, is_active, onboarding_source, onboarding_reviewed, submitted_on)
            VALUES
              ({placeholders}, FALSE, 'self_submitted', FALSE, NOW())""",
        values=values,
    )
    logger.info(f"Vendor onboarding submission received: {name} ({mobile})")
    return {"ok": True, "message": "Thanks! Your details have been submitted and our team will be in touch."}
