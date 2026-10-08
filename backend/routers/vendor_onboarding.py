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
import time
from difflib import SequenceMatcher
from typing import List, Optional

import httpx
from fastapi import APIRouter, Form, File, UploadFile, HTTPException

from database import database

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB — comfortably fits a phone photo or scanned page
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9]{6,34}$")
# 2026-09-30: mobile numbers must be 10 digits starting 6-9; emails must look valid.
_MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")
_PINCODE_RE = re.compile(r"^[1-9][0-9]{5}$")
_CITY_RE = re.compile(r"^(?=.*[A-Za-z]{2})[A-Za-z .'()-]{2,50}$")
_LOCALITY_RE = re.compile(r"^(?=.*[A-Za-z]{2})[A-Za-z0-9 .,'()/&-]{2,100}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")


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
    "deals_in", "address", "locality", "city", "pincode", "preferred_payment_mode", "gst_number",
]
_BANK_FIELDS = ["bank_account_holder_name", "bank_name", "bank_account_number", "bank_ifsc_code"]
_DIGITS = "right(regexp_replace(COALESCE({c}, ''), '[^0-9]', '', 'g'), 10)"


def _same(field: str, a: Optional[str], b: Optional[str]) -> bool:
    if field in ("alternate_mobile", "whatsapp_number"):
        return _normalize_mobile(a) == _normalize_mobile(b)
    norm = lambda x: re.sub(r"\s+", " ", (x or "").strip()).lower()
    return norm(a) == norm(b)


def _name_key(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _pick_by_name(rows, submitted_name: str):
    """2026-10-01, per Shruti: some different businesses share one contact's
    number (e.g. SM Enterprises / Ace Telecom — same POC). When a number
    matches several partners, only update one if the submitted business name
    clearly points to it; otherwise update none and let the team decide.

    Compares the submitted name against the words that make each partner's
    name DIFFERENT from the others on that number ("Sejal" vs "Sakshi", not
    the shared "Tattoo"). Exact word hits first, then near-misses for typos.
    A partner is chosen only if it alone gets a hit."""
    want = set(_name_key(submitted_name).split())
    if not want:
        return None
    toks = [set(_name_key(r["name"]).split()) for r in rows]
    distinct = [t - set().union(*(o for j, o in enumerate(toks) if j != i)) for i, t in enumerate(toks)]

    def only_one(hit):
        winners = [r for r, d in zip(rows, distinct) if any(hit(w, x) for w in want for x in d)]
        return winners[0] if len(winners) == 1 else None

    return (only_one(lambda w, x: w == x)
            or only_one(lambda w, x: len(w) >= 4 and SequenceMatcher(None, w, x).ratio() >= 0.85))


async def _update_existing_vendor(mobile: str, values: dict, file_bytes, file_name, file_type,
                                  defaulted: frozenset = frozenset()):
    """If a vendor with this mobile (primary or alternate) already exists,
    merge the submission into it and return True. Return False when there is
    no match, or a list of the matching partners when the number belongs to
    several and the submitted name doesn't clearly pick one — either way the
    caller then creates a new (inactive, pending-review) entry."""
    prim, alt = _DIGITS.format(c="primary_mobile"), _DIGITS.format(c="alternate_mobile")
    cols = ", ".join(_PLAIN_FIELDS + _BANK_FIELDS)
    async with database.transaction():
        matches = await database.fetch_all(
            f"SELECT vendor_id, {cols} FROM vendor_master "
            f"WHERE duplicate_of_id IS NULL AND ({prim} = :m OR {alt} = :m) "
            f"ORDER BY ({prim} = :m) DESC, vendor_id ASC",
            {"m": mobile},
        )
        if not matches:
            return False
        existing = matches[0] if len(matches) == 1 else _pick_by_name(matches, values.get("name"))
        if existing is None:
            return [(m["vendor_id"], m["name"]) for m in matches]

        fill, pending = {}, {}
        for f in _PLAIN_FIELDS:
            new = values.get(f)
            if not new:
                continue
            cur = existing[f]
            if not (cur or "").strip():
                fill[f] = new
            elif f in defaulted:
                # Value was defaulted (e.g. WhatsApp = mobile because the box
                # was left blank), not typed by the vendor — only use it to
                # fill an empty field, never to propose replacing a real one.
                continue
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


# ─── Decorator rate card (2026-10-08, per Shruti) ───────────────────────────
# When the partner picks "Decorator", vendor-onboarding.html adds a Decor Rate
# Card section: a rate for each of the 4 standard decors (with pastel/chrome
# extras and, per website design, same rate / other rate / can't do), a
# transport rate per Mumbai zone, flex pickup, booking notice and 1-5 photos of
# past work. It arrives as one JSON form field plus the photos, and is saved to
# decor_rate_cards / decor_rate_card_photos (migrations/044) so the team can
# compare decorators side by side (decor-rate-cards.html).
_MAX_RATE_CARD_CHARS = 200_000
MAX_WORK_PHOTOS = 5
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _parse_rate_card(raw: Optional[str]) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None
    if len(raw) > _MAX_RATE_CARD_CHARS:
        raise HTTPException(status_code=400, detail="The decor rate card is too long — please shorten the remarks.")
    try:
        card = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="We could not read the decor rate card — please try again.")
    if not isinstance(card, dict) or not isinstance(card.get("tiers"), dict):
        raise HTTPException(status_code=400, detail="We could not read the decor rate card — please try again.")
    return card


async def _read_work_photos(files) -> list:
    photos = []
    for f in files or []:
        if f is None or not getattr(f, "filename", None):
            continue
        if len(photos) >= MAX_WORK_PHOTOS:
            raise HTTPException(status_code=400, detail=f"Please add at most {MAX_WORK_PHOTOS} photos of your work.")
        raw = await f.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="One of the work photos is too large — please keep each under 5MB.")
        if not raw:
            continue
        kind = _sniff_file_type(raw)
        if kind not in _IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Work photos must be JPG, PNG or WEBP images.")
        photos.append((raw, kind, _safe_filename(f.filename)))
    return photos


async def _save_rate_card(card: dict, photos: list, vendor_name: str, mobile: str) -> None:
    prim, alt = _DIGITS.format(c="primary_mobile"), _DIGITS.format(c="alternate_mobile")
    language = str(card.get("language") or "")[:5] or None
    async with database.transaction():
        vendor_id = await database.fetch_val(
            f"SELECT vendor_id FROM vendor_master WHERE duplicate_of_id IS NULL AND ({prim} = :m OR {alt} = :m) "
            f"ORDER BY ({prim} = :m) DESC, vendor_id DESC LIMIT 1",
            {"m": mobile},
        )
        card_id = await database.fetch_val(
            """INSERT INTO decor_rate_cards (vendor_id, vendor_name, mobile, language, rate_card)
               VALUES (:vid, :name, :m, :lang, CAST(:card AS JSONB)) RETURNING id""",
            {"vid": vendor_id, "name": vendor_name, "m": mobile, "lang": language,
             "card": json.dumps(card, ensure_ascii=False)},
        )
        for raw, kind, fname in photos:
            await database.execute(
                """INSERT INTO decor_rate_card_photos (rate_card_id, image, image_type, image_name)
                   VALUES (:cid, :img, :t, :n)""",
                {"cid": card_id, "img": raw, "t": kind, "n": fname},
            )
    logger.info(f"Decor rate card {card_id} saved for {vendor_name} ({mobile}), vendor {vendor_id}, {len(photos)} photo(s)")


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
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    # Defensive cap, not validation — alternate_mobile/whatsapp_number are
    # optional and only lightly cleaned (unlike primary_mobile, which is
    # hard-validated to exactly 10 digits below); this just stops a stray
    # long paste from overflowing the column's VARCHAR(10) and 500-ing.
    return digits[:10]


def _checked_mobile(raw: Optional[str], label: str) -> Optional[str]:
    """Blank -> None. Otherwise must normalize to a 10-digit Indian mobile
    (starting 6-9), or the submission is rejected with a clear message."""
    if not (raw or "").strip():
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _MOBILE_RE.match(digits):
        raise HTTPException(status_code=400, detail=f"Please enter a valid 10-digit {label}.")
    return digits


# ─── Pincode lookup (2026-09-30, per Shruti: "city autofill on pincode, and
# also add a textbox for locality (based on pincode). autofill that as well") ─
# Proxies India Post's public pincode data so the form gets one small, cached,
# rate-limited endpoint (see security.py) instead of calling a third party
# from the browser. A failed lookup never blocks the form — the vendor just
# types city/locality themselves.
_PIN_API = "https://api.postalpincode.in/pincode/{pin}"
_PIN_CACHE: dict = {}                 # pin -> (fetched_at, result)
_PIN_CACHE_TTL = 7 * 24 * 3600
_PO_SUFFIX = re.compile(r"\s+(S\.?O|B\.?O|H\.?O|GPO)\.?$", re.I)


@router.get("/pincode/{pin}")
async def lookup_pincode(pin: str):
    if not _PINCODE_RE.match(pin or ""):
        raise HTTPException(status_code=400, detail="Please enter a valid 6-digit pincode.")
    hit = _PIN_CACHE.get(pin)
    if hit and time.time() - hit[0] < _PIN_CACHE_TTL:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(_PIN_API.format(pin=pin))
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"Pincode lookup failed for {pin}: {e}")
        raise HTTPException(status_code=503, detail="Pincode lookup is unavailable right now.")
    entry = data[0] if isinstance(data, list) and data else {}
    offices = entry.get("PostOffice") or []
    if entry.get("Status") != "Success" or not offices:
        result = {"found": False, "city": None, "state": None, "localities": []}
    else:
        districts = [o.get("District") for o in offices if o.get("District")]
        city = max(set(districts), key=districts.count) if districts else None
        seen, localities = set(), []
        for o in offices:
            name = _PO_SUFFIX.sub("", (o.get("Name") or "").strip())
            if name and name.lower() not in seen:
                seen.add(name.lower())
                localities.append(name)
        result = {"found": True, "city": city, "state": offices[0].get("State"),
                  "localities": sorted(localities)}
    if len(_PIN_CACHE) > 5000:
        _PIN_CACHE.clear()
    _PIN_CACHE[pin] = (time.time(), result)
    return result


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
    locality: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    bank_account_holder_name: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account_number: Optional[str] = Form(None),
    bank_ifsc_code: Optional[str] = Form(None),
    preferred_payment_mode: Optional[str] = Form(None),
    gst_number: Optional[str] = Form(None),
    cancelled_cheque: Optional[UploadFile] = File(None),
    decor_rate_card: Optional[str] = Form(None),
    work_photos: Optional[List[UploadFile]] = File(None),
):
    name = _clean(name)
    if not name:
        raise HTTPException(status_code=400, detail="Business/vendor name is required.")

    mobile = _checked_mobile(primary_mobile, "mobile number")
    if not mobile:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
    alternate_mobile = _checked_mobile(alternate_mobile, "alternate mobile number")
    whatsapp_number = _checked_mobile(whatsapp_number, "WhatsApp number")
    email = _clean(email)
    if email:
        if len(email) > 254 or not _EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        email = email.lower()
    # 2026-09-30, per Shruti: "add city pincode validation as well" (both optional).
    city = _clean(city)
    if city:
        city = re.sub(r"\s+", " ", city)
        if not _CITY_RE.match(city):
            raise HTTPException(status_code=400, detail="Please enter a valid city name.")
    locality = _clean(locality)
    if locality:
        locality = re.sub(r"\s+", " ", locality)
        if not _LOCALITY_RE.match(locality):
            raise HTTPException(status_code=400, detail="Please enter a valid locality.")
    pincode = re.sub(r"\s", "", pincode or "") or None
    if pincode and not _PINCODE_RE.match(pincode):
        raise HTTPException(status_code=400, detail="Please enter a valid 6-digit pincode.")

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

    # Optional — "bank_transfer" or "cash". Originally cash / gpay
    # (2026-09-17); 2026-09-30, per Shruti: "make it bank transfer and then
    # cash. remove gpay". Existing rows saved as "gpay" are left as-is.
    # Blank/omitted is fine; anything else
    # is rejected rather than silently dropped, so a typo in a future
    # frontend build fails loudly instead of writing garbage.
    preferred_payment_mode = _clean(preferred_payment_mode)
    if preferred_payment_mode:
        preferred_payment_mode = preferred_payment_mode.lower()
        if preferred_payment_mode not in ("bank_transfer", "cash"):
            raise HTTPException(status_code=400, detail="Preferred payment mode must be Bank Transfer or Cash.")

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

    # Decorator rate card (2026-10-08): checked before anything is written, so a
    # bad card or photo is reported to the vendor instead of half-saving.
    rate_card = _parse_rate_card(decor_rate_card) if (_clean(deals_in) or "").lower() == "decorator" else None
    work = await _read_work_photos(work_photos) if rate_card is not None else []

    # 2026-09-30, per Shruti: "by default, save the mobile no. as the whatsapp
    # no. in the database. if the user inputs something on whatsapp no - then
    # update accordingly".
    whatsapp_given = whatsapp_number or None
    values = {
        "name": name,
        "primary_contact_name": _clean(primary_contact_name),
        "primary_mobile": mobile,
        "alternate_mobile": alternate_mobile,
        "whatsapp_number": whatsapp_given or mobile,
        "email": email,
        "deals_in": _clean(deals_in),
        "address": _clean(address),
        "locality": locality,
        "city": city,
        "pincode": pincode,
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
    defaulted = frozenset() if whatsapp_given else frozenset({"whatsapp_number"})
    matched = await _update_existing_vendor(mobile, values, file_bytes, file_name, file_content_type, defaulted)
    if matched is True:
        if rate_card is not None:
            await _save_rate_card(rate_card, work, name, mobile)
        return {"ok": True, "message": "Thanks! Your details have been submitted and our team will be in touch."}
    if matched:   # number shared by several partners and the name didn't pick one
        values["remarks"] = (
            "Mobile number is also on: "
            + "; ".join(f"{n} (#{i})" for i, n in matched)
            + " — check whether this is one of them before activating."
        )

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
    if rate_card is not None:
        await _save_rate_card(rate_card, work, name, mobile)
    return {"ok": True, "message": "Thanks! Your details have been submitted and our team will be in touch."}
