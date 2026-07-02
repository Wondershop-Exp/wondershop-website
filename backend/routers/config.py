"""
Platform config endpoints — read-only for frontend.
Source of truth: WS_DataDictionary_v1.docx (platform_config, Section 8)
"""
from fastapi import APIRouter
from database import database

router = APIRouter()


@router.get("/platform")
async def get_platform_config():
    """Returns all platform config key-value pairs."""
    rows = await database.fetch_all(
        "SELECT config_key, config_value, description FROM platform_config"
    )
    return {r["config_key"]: r["config_value"] for r in rows}


@router.get("/terms")
async def get_active_terms():
    """Returns the currently active Terms & Conditions."""
    row = await database.fetch_one(
        """
        SELECT tc_id, version, content, effective_from
        FROM terms_conditions
        WHERE is_active = TRUE
        ORDER BY created_on DESC
        LIMIT 1
        """
    )
    return dict(row) if row else {}


@router.get("/coupons/validate/{code}")
async def validate_coupon(code: str):
    """
    Validates a coupon or referral code.
    Returns validity, discount details, and cap.
    """
    row = await database.fetch_one(
        """
        SELECT coupon_id, code, discount_pct, discount_amt,
               max_discount_amt, minimum_cart_value,
               valid_from, valid_to, owner_name
        FROM coupons
        WHERE UPPER(code) = UPPER(:code)
          AND status    = 'Active'
          AND is_active = TRUE
          AND valid_from <= CURRENT_DATE
          AND valid_to   >= CURRENT_DATE
          AND (usage_limit IS NULL OR usage_count < usage_limit)
        """,
        values={"code": code},
    )
    if not row:
        return {"valid": False, "message": "Invalid or expired code"}

    return {
        "valid":             True,
        "code":              row["code"],
        "discount_pct":      float(row["discount_pct"] or 0),
        "discount_amt":      float(row["discount_amt"] or 0),
        "max_discount_amt":  float(row["max_discount_amt"] or 0),
        "minimum_cart_value": float(row["minimum_cart_value"] or 0),
        "is_referral":       bool(row["owner_name"]),
    }


@router.get("/discounts")
async def get_discount_slabs():
    """Returns active volume discount slabs (from cart_pack_discount)."""
    rows = await database.fetch_all(
        """
        SELECT id, cart_value, discount_pct
        FROM cart_pack_discount
        WHERE is_active = TRUE
        ORDER BY cart_value
        """
    )
    return [dict(r) for r in rows]
