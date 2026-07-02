"""
Catalogue endpoints — read-only service master data for the birthday builder.
Source of truth: WS_DataDictionary_v1.docx
"""
from fastapi import APIRouter, Query
from typing import Optional
from database import database

router = APIRouter()


# ─── DECOR ──────────────────────────────────────────────────────────────────

@router.get("/decor")
async def get_decor_themes(
    age_group: Optional[str] = Query(None),
    gender:    Optional[str] = Query(None),
    type:      Optional[str] = Query(None),   # 'Theme' | 'Standard'
    theme:     Optional[str] = Query(None),   # free-text search on name
):
    """
    Returns decor_theme rows joined with base_decor_master.
    """
    conditions = ["dt.is_active = TRUE", "bd.is_active = TRUE"]
    values: dict = {}

    if age_group:
        conditions.append("(dt.age_group ILIKE :age_group OR dt.age_group = 'All')")
        values["age_group"] = f"%{age_group}%"
    if gender:
        conditions.append("(dt.gender = :gender OR dt.gender = 'Any')")
        values["gender"] = gender
    if type:
        conditions.append("dt.type = :type")
        values["type"] = type
    if theme:
        conditions.append("dt.name ILIKE :theme")
        values["theme"] = f"%{theme}%"

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"""
        SELECT
            dt.decor_theme_id, dt.name, dt.type, dt.age_group, dt.gender,
            dt.image_url, dt.video_url, dt.balloon_colours, dt.description,
            bd.decor_id, bd.name AS base_name, bd.price AS base_price,
            bd.print_requirements, bd.stand_requirements, bd.lights_requirements
        FROM decor_theme dt
        JOIN base_decor_master bd ON bd.decor_id = dt.fk_decor_id
        WHERE {where}
        ORDER BY dt.type, dt.name
        """,
        values=values,
    )
    return [dict(r) for r in rows]


@router.get("/decor/{decor_theme_id}")
async def get_decor_theme(decor_theme_id: int):
    row = await database.fetch_one(
        """
        SELECT dt.*, bd.name AS base_name, bd.price AS base_price,
               bd.print_requirements, bd.stand_requirements, bd.lights_requirements
        FROM decor_theme dt
        JOIN base_decor_master bd ON bd.decor_id = dt.fk_decor_id
        WHERE dt.decor_theme_id = :id AND dt.is_active = TRUE
        """,
        values={"id": decor_theme_id},
    )
    return dict(row) if row else {}


# ─── ACTIVITIES ──────────────────────────────────────────────────────────────

@router.get("/activities")
async def get_activities(
    age_group:     Optional[str] = Query(None),
    gender:        Optional[str] = Query(None),
    interest_area: Optional[str] = Query(None),
    category:      Optional[str] = Query(None),
):
    """
    Returns activities catalogue. Pricing is in pricing_models / service_vendor,
    not in this table.
    """
    conditions = ["is_active = TRUE"]
    values: dict = {}

    if age_group:
        conditions.append("age_group ILIKE :age_group")
        values["age_group"] = f"%{age_group}%"
    if gender:
        conditions.append("(gender = :gender OR gender = 'Any')")
        values["gender"] = gender
    if interest_area:
        conditions.append("interest_area ILIKE :interest_area")
        values["interest_area"] = f"%{interest_area}%"
    if category:
        conditions.append("category = :category")
        values["category"] = category

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"SELECT * FROM activities_master WHERE {where} ORDER BY name",
        values=values,
    )
    return [dict(r) for r in rows]


@router.get("/activities/{activity_id}")
async def get_activity(activity_id: int):
    row = await database.fetch_one(
        "SELECT * FROM activities_master WHERE activity_id = :id AND is_active = TRUE",
        values={"id": activity_id},
    )
    return dict(row) if row else {}


# ─── HOSTS ───────────────────────────────────────────────────────────────────

@router.get("/hosts")
async def get_host_tiers():
    """
    Returns tier options ONLY. Individual host names/photos are INTERNAL —
    never exposed to clients. Host is assigned post-booking by AM.
    """
    rows = await database.fetch_all(
        """
        SELECT
            host_tier,
            COUNT(*) AS available_count
        FROM host_master
        WHERE is_active = TRUE
        GROUP BY host_tier
        ORDER BY CASE host_tier
            WHEN 'Standard'      THEN 1
            WHEN 'Premium'       THEN 2
            WHEN 'Super Premium' THEN 3
        END
        """
    )
    return [dict(r) for r in rows]


# ─── DJS ─────────────────────────────────────────────────────────────────────

@router.get("/djs")
async def get_dj_tiers():
    rows = await database.fetch_all(
        """
        SELECT
            dj_tier,
            COUNT(*) AS available_count
        FROM dj_master
        WHERE is_active = TRUE
        GROUP BY dj_tier
        ORDER BY CASE dj_tier
            WHEN 'Standard' THEN 1
            WHEN 'Premium'  THEN 2
        END
        """
    )
    return [dict(r) for r in rows]


# ─── PINATAS ─────────────────────────────────────────────────────────────────

@router.get("/pinatas")
async def get_pinatas(
    base_type: Optional[str] = Query(None),
    theme:     Optional[str] = Query(None),
):
    conditions = ["is_active = TRUE"]
    values: dict = {}
    if base_type:
        conditions.append("base_type = :base_type")
        values["base_type"] = base_type
    if theme:
        conditions.append("theme ILIKE :theme")
        values["theme"] = f"%{theme}%"

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"SELECT * FROM pinata_master WHERE {where} ORDER BY base_type, name",
        values=values,
    )
    return [dict(r) for r in rows]


# ─── E-INVITES ───────────────────────────────────────────────────────────────

@router.get("/einvites")
async def get_einvites(
    theme:                Optional[str]  = Query(None),
    supports_multi_child: Optional[bool] = Query(None),
):
    conditions = ["is_active = TRUE"]
    values: dict = {}
    if theme:
        conditions.append("theme ILIKE :theme")
        values["theme"] = f"%{theme}%"
    if supports_multi_child is not None:
        conditions.append("supports_multi_child = :multi")
        values["multi"] = supports_multi_child

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"""
        SELECT invite_id, name, theme, image_url, video_url, supports_multi_child
        FROM einvite_master
        WHERE {where}
        ORDER BY name
        """,
        values=values,
    )
    return [dict(r) for r in rows]


# ─── PHOTOGRAPHY ─────────────────────────────────────────────────────────────

@router.get("/photographers")
async def get_photographer_packages():
    rows = await database.fetch_all(
        """
        SELECT photographer_id, package_name, tier, hours,
               deliverables, portfolio_url, addons_available
        FROM photographer_master
        WHERE is_active = TRUE
        ORDER BY CASE tier
            WHEN 'Basic'    THEN 1
            WHEN 'Standard' THEN 2
            WHEN 'Premium'  THEN 3
        END
        """
    )
    return [dict(r) for r in rows]


# ─── RETURN GIFTS ────────────────────────────────────────────────────────────

@router.get("/gifts")
async def get_gifts(
    age_group:    Optional[str]  = Query(None),
    utility_tag:  Optional[str]  = Query(None),
    theme:        Optional[str]  = Query(None),
    personalised: Optional[bool] = Query(None),
):
    conditions = ["is_active = TRUE"]
    values: dict = {}
    if age_group:
        conditions.append("age_group ILIKE :age_group")
        values["age_group"] = f"%{age_group}%"
    if utility_tag:
        conditions.append("utility_tag = :utility_tag")
        values["utility_tag"] = utility_tag
    if theme:
        conditions.append("theme ILIKE :theme")
        values["theme"] = f"%{theme}%"
    if personalised is not None:
        conditions.append("personalisation_available = :personalised")
        values["personalised"] = personalised

    where = " AND ".join(conditions)
    rows = await database.fetch_all(
        f"""
        SELECT gift_id, name, theme, age_group, utility_tag,
               mrp, sp, dimensions, image_url, packaging_options,
               personalisation_available
        FROM gift_master
        WHERE {where}
        ORDER BY name
        """,
        values=values,
    )
    return [dict(r) for r in rows]


# ─── TESTIMONIALS ────────────────────────────────────────────────────────────

@router.get("/testimonials")
async def get_testimonials():
    rows = await database.fetch_all(
        """
        SELECT testimonial_id, text, image_url, video_url, client_name, client_city
        FROM testimonials_master
        ORDER BY created_on DESC
        """
    )
    return [dict(r) for r in rows]


# ─── PRICING MODEL LOOKUP ────────────────────────────────────────────────────

@router.get("/pricing/{pincode}")
async def get_pricing_for_pincode(pincode: str):
    """
    Returns the full pricing model for a given pincode.
    Falls back to platform_config('default_pricing_model_id') with a soft message.
    """
    row = await database.fetch_one(
        """
        SELECT pm.*
        FROM mapping_pricing_pincode mpp
        JOIN pricing_models pm ON pm.id = mpp.fk_pricing_model_id
        WHERE mpp.pincode = :pincode
          AND mpp.is_active = TRUE
          AND pm.is_active  = TRUE
        LIMIT 1
        """,
        values={"pincode": pincode},
    )

    is_fallback = False
    if not row:
        is_fallback = True
        cfg = await database.fetch_one(
            "SELECT config_value FROM platform_config WHERE config_key = 'default_pricing_model_id'"
        )
        if cfg:
            row = await database.fetch_one(
                "SELECT * FROM pricing_models WHERE id = :id AND is_active = TRUE",
                values={"id": int(cfg["config_value"])},
            )

    if not row:
        return {"found": False, "message": "No pricing model available"}

    return {
        "found": True,
        "is_fallback": is_fallback,
        "fallback_message": (
            "We'll show you our standard pricing — your Party Lead will confirm final pricing for your area."
            if is_fallback else None
        ),
        "pricing": dict(row),
    }
