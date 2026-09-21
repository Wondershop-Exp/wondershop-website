"""
Public vendor onboarding form (2026-09-17, per Shruti — "create vendor
onboarding form... We'll ask the details from the vendor, including
uploading a cancelled check or adding account details for payment").

No admin password required — this is a public-facing router, like
leads.py's /submit, meant to be hit by a vendor filling in vendor-
onboarding.html from a link the team sends them, not by anyone signed into
the admin panel.

(2026-09-21) A submission whose mobile number already belongs to a vendor is
merged into that vendor instead of creating a duplicate — blanks are filled in,
while changed values and ALL bank details are held for approval in the Partners
tab (see _update_existing_vendor below and migrations/032_vendor_pending_update.sql).

Otherwise, a submission lands as an ordinary vendor_master row — inactive, flagged
onboarding_source='self_submitted' / onboarding_reviewed=FALSE — so it
shows up in admin.html's existing Vendors tab (sorted to the top, with a
"Pending review" badge) rather than needing a separate review screen. See
migrations/031_vendor_onboarding.sql for the columns this writes to, and
routers/vendors.py for the admin-side read/review endpoints.
"""
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException

from database import database

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB — comfortably fits a phone photo or scanned page
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9]{6,34}$")


def _sniff_file_type(raw: bytes) -> Optional[str]:
    """What the file REALLY is, judged from its first bytes — the browser-
    supplied Content-Type is just a claim and can say anything."""
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _safe_filename(name: Optional[str]) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "cancelled-cheque")[:100]


# ─── Matching a submission to a vendor we already have ──────────────────────
# (2026-09-21, per Shruti — "form match on mobile number and update the
# existing vendor instead" of creating a duplicate.) A public form must never
# be able to change what we pay a vendor, so:
#   * fields that are blank on the existing vendor are filled in directly;
#   * a DIFFERENT value for a field that already has one, and ALL bank details
#     and the cheque file, are held as a "pending update" that a team member
#     approves in the Partners tab (routers/vendors.py: pending/apply|dismiss).
# The reply to the vendor is identical whether or not a match was found, so the
# form can't be used to find out which phone numbers are in our vendor list.
_PLAIN_FIELDS = [
    "name", "primary_contact_name", "alternate_mobile", "whatsapp_number", "email",
    "deals_in", "address", "city", "pincode", "preferred_payment_mode", "gst_number",
]
_BANK_FIELDS = ["bank_account_holder_name", "bank_name", "bank_account_number", "bank_ifsc_code"]
_DIGITS = "right(regexp_replace(COALESCE({c}, ''), '[^0-9]', '', 'g'), 10)"


def _same(field: str, a: Optional[str], b: Optional[str]) -> bool:
    if field in ("alternate_mobile", "whatsapp_number"):
        return _normalize_mobile(a) == _normalize_mobile(b)
    norm = lambda x: re.sub(r"\s+", " ", (x or "").strip()).lower()
    return norm(a) == norm(b)


async def _update_existing_vendor(mobile: str, values: dict, file_bytes, file_name, file_type) -> bool:
    """If a vendor with this mobile (primary or alternate) already exists,
    merge the submission into it and return True; otherwise return False and
    let the caller create a new vendor."""
    prim, alt = _DIGITS.format(c="primary_mobile"), _DIGITS.format(c="alternate_mobile")
    cols = ", ".join(_PLAIN_FIELDS + _BANK_FIELDS)
    async with database.transaction():
        existing = await database.fetch_one(
            f"SELECT vendor_id, {cols} FROM vendor_master "
            f"WHERE duplicate_of_id IS NULL AND ({prim} = :m OR {alt} = :m) "
            f"ORDER BY ({prim} = :m) DESC, vendor_id ASC LIMIT 1",
            {"m": mobile},
        )
        if not existing:
            return False

        fill, pending = {}, {}
        for f in _PLAIN_FIELDS:
            new = values.get(f)
            if not new:
                continue
            cur = existing[f]
            if not (cur or "").strip():
                fill[f] = new
            elif not _same(f, cur, new):
                pending[f] = new
        for f in _BANK_FIELDS:
            new = values.get(f)
            if new and not _same(f, existing[f], new):
                pending[f] = new

        sets = [f"{f} = :{f}" for f in fill]
        params = {"id": existing["vendor_id"], "pending": json.dumps(pending) if pending else None, **fill}
        # The newest submission replaces any earlier held-back values.
        sets.append("pending_update = CAST(:pending AS JSONB)")
        if pending or file_bytes:
            sets.append("pending_submitted_on = NOW()")
        if fill or pending or file_bytes:
            sets += ["onboarding_reviewed = FALSE", "submitted_on = NOW()"]
        if file_bytes:
            sets += ["pending_cheque_file = :pcf", "pending_cheque_filename = :pcn", "pending_cheque_content_type = :pct"]
            params.update({"pcf": file_bytes, "pcn": file_name, "pct": file_type})
        await database.execute(
            f"UPDATE vendor_master SET {', '.join(sets)} WHERE vendor_id = :id", params
        )
    logger.info(
        f"Vendor onboarding form matched existing vendor {existing['vendor_id']} ({mobile}): "
        f"filled {sorted(fill)}, held for approval {sorted(pending)}{' + cheque' if file_bytes else ''}"
    )
    return True


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
    if bank_account_number:
        bank_account_number = re.sub(r"[\s-]", "", bank_account_number)
        if not _ACCOUNT_RE.match(bank_account_number):
            raise HTTPException(status_code=400, detail="Account number should be 6 to 34 letters/digits, with no other symbols.")
    if bank_ifsc_code:
        bank_ifsc_code = bank_ifsc_code.upper()
        if not _IFSC_RE.match(bank_ifsc_code):
            raise HTTPException(status_code=400, detail="IFSC code should look like HDFC0001234 (4 letters, a zero, then 6 letters/digits).")
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
        # Read at most one byte past the limit, so a huge upload is refused
        # without ever being loaded into memory in full.
        raw = await cancelled_cheque.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="That file is too large — please keep it under 5MB.")
        if raw:
            sniffed = _sniff_file_type(raw)
            if sniffed is None:
                raise HTTPException(status_code=400, detail="The file must be a JPG, PNG, or PDF.")
            file_content_type = sniffed
            file_bytes = raw
            file_name = _safe_filename(cancelled_cheque.filename)

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
    # Already one of our vendors? Merge into that record instead of duplicating.
    if await _update_existing_vendor(mobile, values, file_bytes, file_name, file_content_type):
        return {"ok": True, "message": "Thanks! Your details have been submitted and our team will be in touch."}

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
