"""
Order & Cart session endpoints.
Source of truth: WS_DataDictionary_v1.docx

Architecture (from DD Decision 1):
  cart_config = pre-booking config layer (builder UI reads/writes here)
  order_item  = post-booking financial ledger (auto-generated on Awaiting Advance)

Session flow:
  POST /order/start        → create client_master + child_master + orders + cart + cart_config
  GET  /order/{event_code} → fetch full order state (order + cart + cart_config + children)
  POST /cart/config/update → update cart_config (builder step selection)
  POST /cart/confirm       → move order → Awaiting Advance, generate order_item rows
  GET  /order/lead/{lead_id}/resume → load builder_snapshot from leads table
"""
import json
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import database

router = APIRouter()


# ─── PYDANTIC MODELS ─────────────────────────────────────────────────────────

class ChildIn(BaseModel):
    name: str
    dob:  str   # YYYY-MM-DD
    gender: str  # Male | Female | Other


class OrderStartRequest(BaseModel):
    # Client
    parent_name:      str
    primary_mobile:   str
    email:            Optional[str] = None
    secondary_mobile: Optional[str] = None
    # Event basics (Step 0)
    kids_count:       int
    event_date:       str       # YYYY-MM-DD
    event_start_time: str       # HH:MM
    event_end_time:   str       # HH:MM
    venue_type:       str
    city:             str
    pincode:          str
    theme:            Optional[str] = None
    # Child(ren)
    children:         List[ChildIn] = []


class CartConfigUpdate(BaseModel):
    event_code:          str
    # Builder step selections (all optional — partial updates allowed)
    fk_decor_theme_id:   Optional[int] = None
    host_tier:           Optional[str] = None
    dj_tier:             Optional[str] = None
    pinata_category:     Optional[str] = None
    fk_einvite_id:       Optional[int] = None
    photographer_pack:   Optional[str] = None
    json_giftbundle:     Optional[list] = None   # [{gift_id, qty, personalised, tag_design}]
    json_activity:       Optional[list] = None   # [{activity_id, qty}]
    gift_delivery_address: Optional[str] = None
    gift_required_by_date: Optional[str] = None


class ConfirmRequest(BaseModel):
    event_code: str
    coupon_code: Optional[str] = None


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _generate_event_code(city: str, order_id: int) -> str:
    """Generates WSE-MUM-2026-0042 style code."""
    city_codes = {
        "Mumbai":     "MUM",
        "Pune":       "PUN",
        "Navi Mumbai": "NMB",
    }
    code = city_codes.get(city, "WS")
    year = date.today().year
    return f"WSE-{code}-{year}-{order_id:04d}"


async def _get_or_create_client(mobile: str, name: str, email: Optional[str],
                                 secondary_mobile: Optional[str],
                                 city: str, pincode: str) -> int:
    """Returns existing client_id or creates a new client."""
    row = await database.fetch_one(
        "SELECT client_id FROM client_master WHERE primary_mobile = :mobile",
        values={"mobile": mobile},
    )
    if row:
        return row["client_id"]

    client_id = await database.execute(
        """
        INSERT INTO client_master
            (name, primary_mobile, secondary_mobile, email, pincode, city)
        VALUES
            (:name, :mobile, :secondary, :email, :pincode, :city)
        RETURNING client_id
        """,
        values={
            "name": name, "mobile": mobile, "secondary": secondary_mobile,
            "email": email, "pincode": pincode, "city": city,
        },
    )
    return client_id


async def _get_or_create_child(client_id: int, child: ChildIn) -> int:
    """Returns existing child_id (matched on client+name+dob) or creates."""
    row = await database.fetch_one(
        """
        SELECT child_id FROM child_master
        WHERE client_id = :client_id AND name = :name AND dob = :dob
        """,
        values={"client_id": client_id, "name": child.name, "dob": child.dob},
    )
    if row:
        return row["child_id"]

    child_id = await database.execute(
        """
        INSERT INTO child_master (client_id, name, dob, gender)
        VALUES (:client_id, :name, :dob, :gender)
        RETURNING child_id
        """,
        values={
            "client_id": client_id, "name": child.name,
            "dob": child.dob, "gender": child.gender,
        },
    )
    return child_id


async def _recalculate_cart(cart_id: int, order_id: int) -> None:
    """
    Recalculates cart totals from pricing_models via the order's pincode.
    In MVP, pricing is sourced from the active pricing_model for the pincode.
    Full line-item repricing happens at confirm time (order_item generation).
    This function updates total_wo_discount, pack discount, and total_payable.
    """
    # Get current cart
    cart = await database.fetch_one(
        "SELECT * FROM cart WHERE cart_id = :id", values={"id": cart_id}
    )
    if not cart:
        return

    # Get cart_config for this cart
    cfg = await database.fetch_one(
        "SELECT * FROM cart_config WHERE cart_id = :id", values={"id": cart_id}
    )
    if not cfg:
        return

    # Get order for pincode
    order = await database.fetch_one(
        "SELECT pincode FROM orders WHERE order_id = :id", values={"id": order_id}
    )
    if not order:
        return

    # Look up pricing model for pincode
    pm = await database.fetch_one(
        """
        SELECT pm.*
        FROM mapping_pricing_pincode mpp
        JOIN pricing_models pm ON pm.id = mpp.fk_pricing_model_id
        WHERE mpp.pincode = :pincode AND mpp.is_active = TRUE AND pm.is_active = TRUE
        LIMIT 1
        """,
        values={"pincode": order["pincode"]},
    )
    if not pm:
        # Try default pricing model
        default_cfg = await database.fetch_one(
            "SELECT config_value FROM platform_config WHERE config_key = 'default_pricing_model_id'"
        )
        if default_cfg:
            pm = await database.fetch_one(
                "SELECT * FROM pricing_models WHERE id = :id AND is_active = TRUE",
                values={"id": int(default_cfg["config_value"])},
            )

    if not pm:
        return  # Cannot calculate without a pricing model

    # Sum selected services from pricing model
    total = 0.0
    if cfg["fk_decor_theme_id"] and pm["decor_theme_price"]:
        total += float(pm["decor_theme_price"])
    if cfg["host_tier"] and pm["host_price"]:
        total += float(pm["host_price"])
    if cfg["dj_tier"] and cfg["dj_tier"] != "None" and pm["dj_price"]:
        total += float(pm["dj_price"])
    if cfg["pinata_category"] and cfg["pinata_category"] != "None" and pm["pinnata_price"]:
        total += float(pm["pinnata_price"])
    if cfg["fk_einvite_id"] and pm["einvite_price"]:
        total += float(pm["einvite_price"])
    if cfg["photographer_pack"] and cfg["photographer_pack"] != "None" and pm["photographer_price"]:
        total += float(pm["photographer_price"])
    if cfg["json_activity"] and pm["activities_price"]:
        total += float(pm["activities_price"])

    # Apply pack discount slab
    slab = await database.fetch_one(
        """
        SELECT id, discount_pct FROM cart_pack_discount
        WHERE cart_value <= :total AND is_active = TRUE
        ORDER BY cart_value DESC
        LIMIT 1
        """,
        values={"total": total},
    )
    cpd_id = slab["id"] if slab else None
    cpd_pct = float(slab["discount_pct"]) if slab else 0.0
    cpd_amt = round(total * cpd_pct / 100, 2) if cpd_pct else 0.0

    total_payable = round(total - cpd_amt, 2)

    await database.execute(
        """
        UPDATE cart SET
            total_wo_discount        = :total,
            fk_cart_pack_discount_id = :cpd_id,
            fk_cpd_pct               = :cpd_pct,
            fk_cpd_amt               = :cpd_amt,
            total_payable            = :total_payable,
            balance_due              = :total_payable
        WHERE cart_id = :cart_id
        """,
        values={
            "total": total, "cpd_id": cpd_id, "cpd_pct": cpd_pct,
            "cpd_amt": cpd_amt, "total_payable": total_payable,
            "cart_id": cart_id,
        },
    )


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/order/start")
async def start_order(req: OrderStartRequest):
    """
    Creates a new order session:
      1. Upsert client_master
      2. Upsert child_master for each child
      3. Create orders row (status = Lead)
      4. Create cart (status = Active)
      5. Create cart_config (empty — builder fills it step by step)
      6. Link children via client_child
    Returns event_code for all subsequent requests.
    """
    # 1. Client
    client_id = await _get_or_create_client(
        mobile=req.primary_mobile, name=req.parent_name,
        email=req.email, secondary_mobile=req.secondary_mobile,
        city=req.city, pincode=req.pincode,
    )

    # 2. Order (placeholder event_code, updated after we have the PK)
    order_id = await database.execute(
        """
        INSERT INTO orders
            (event_code, client_id, kids_count, event_date,
             event_start_time, event_end_time, venue_type,
             city, pincode, theme, event_status)
        VALUES
            (:event_code, :client_id, :kids_count, :event_date,
             :start_time, :end_time, :venue_type,
             :city, :pincode, :theme, 'Lead')
        RETURNING order_id
        """,
        values={
            "event_code": "TEMP",
            "client_id": client_id,
            "kids_count": req.kids_count,
            "event_date": req.event_date,
            "start_time": req.event_start_time,
            "end_time": req.event_end_time,
            "venue_type": req.venue_type,
            "city": req.city,
            "pincode": req.pincode,
            "theme": req.theme,
        },
    )

    # Generate and set real event_code
    event_code = _generate_event_code(req.city, order_id)
    await database.execute(
        "UPDATE orders SET event_code = :code WHERE order_id = :id",
        values={"code": event_code, "id": order_id},
    )

    # 3. Cart
    cart_id = await database.execute(
        "INSERT INTO cart (order_id) VALUES (:order_id) RETURNING cart_id",
        values={"order_id": order_id},
    )

    # 4. cart_config (empty shell)
    await database.execute(
        "INSERT INTO cart_config (cart_id) VALUES (:cart_id)",
        values={"cart_id": cart_id},
    )

    # 5. Children
    for child in req.children:
        child_id = await _get_or_create_child(client_id, child)
        await database.execute(
            """
            INSERT INTO client_child (order_id, child_id)
            VALUES (:order_id, :child_id)
            ON CONFLICT (order_id, child_id) DO NOTHING
            """,
            values={"order_id": order_id, "child_id": child_id},
        )

    return {
        "event_code": event_code,
        "order_id": order_id,
        "cart_id": cart_id,
        "client_id": client_id,
    }


@router.get("/order/{event_code}")
async def get_order(event_code: str):
    """
    Returns full order state: order + cart + cart_config + linked children.
    """
    order = await database.fetch_one(
        "SELECT * FROM orders WHERE event_code = :code",
        values={"code": event_code},
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_id = order["order_id"]

    cart = await database.fetch_one(
        "SELECT * FROM cart WHERE order_id = :id", values={"id": order_id}
    )
    cart_config = None
    if cart:
        cart_config = await database.fetch_one(
            "SELECT * FROM cart_config WHERE cart_id = :id",
            values={"id": cart["cart_id"]},
        )

    children = await database.fetch_all(
        """
        SELECT cm.child_id, cm.name, cm.dob, cm.gender
        FROM client_child cc
        JOIN child_master cm ON cm.child_id = cc.child_id
        WHERE cc.order_id = :order_id
        """,
        values={"order_id": order_id},
    )

    return {
        "order": dict(order),
        "cart": dict(cart) if cart else None,
        "cart_config": dict(cart_config) if cart_config else None,
        "children": [dict(c) for c in children],
    }


@router.post("/cart/config/update")
async def update_cart_config(req: CartConfigUpdate):
    """
    Updates cart_config with builder step selections.
    Recalculates cart totals after each update.
    """
    order = await database.fetch_one(
        "SELECT order_id FROM orders WHERE event_code = :code",
        values={"code": req.event_code},
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_id = order["order_id"]
    cart = await database.fetch_one(
        "SELECT cart_id FROM cart WHERE order_id = :id", values={"id": order_id}
    )
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart_id = cart["cart_id"]

    # Build SET clause for only provided fields
    updates = {}
    if req.fk_decor_theme_id  is not None: updates["fk_decor_theme_id"]  = req.fk_decor_theme_id
    if req.host_tier           is not None: updates["host_tier"]           = req.host_tier
    if req.dj_tier             is not None: updates["dj_tier"]             = req.dj_tier
    if req.pinata_category     is not None: updates["pinata_category"]     = req.pinata_category
    if req.fk_einvite_id       is not None: updates["fk_einvite_id"]       = req.fk_einvite_id
    if req.photographer_pack   is not None: updates["photographer_pack"]   = req.photographer_pack
    if req.json_giftbundle     is not None: updates["json_giftbundle"]     = json.dumps(req.json_giftbundle)
    if req.json_activity       is not None: updates["json_activity"]       = json.dumps(req.json_activity)

    if updates:
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["cart_id"] = cart_id
        await database.execute(
            f"UPDATE cart_config SET {set_clause} WHERE cart_id = :cart_id",
            values=updates,
        )

    # Update gift delivery details on cart itself
    cart_updates = {}
    if req.gift_delivery_address  is not None: cart_updates["gift_delivery_address"]  = req.gift_delivery_address
    if req.gift_required_by_date  is not None: cart_updates["gift_required_by_date"]  = req.gift_required_by_date
    if cart_updates:
        set_c = ", ".join(f"{k} = :{k}" for k in cart_updates)
        cart_updates["cart_id"] = cart_id
        await database.execute(
            f"UPDATE cart SET {set_c} WHERE cart_id = :cart_id",
            values=cart_updates,
        )

    await _recalculate_cart(cart_id, order_id)

    cart_row = await database.fetch_one(
        "SELECT total_wo_discount, fk_cpd_pct, fk_cpd_amt, total_payable FROM cart WHERE cart_id = :id",
        values={"id": cart_id},
    )
    return {"updated": True, "cart_summary": dict(cart_row) if cart_row else {}}


@router.post("/cart/confirm")
async def confirm_order(req: ConfirmRequest):
    """
    Moves order to 'Awaiting Advance' and auto-generates order_item rows
    from cart_config. Also applies coupon if provided.
    """
    order = await database.fetch_one(
        "SELECT * FROM orders WHERE event_code = :code",
        values={"code": req.event_code},
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["event_status"] != "Lead":
        raise HTTPException(status_code=400, detail=f"Order already at status: {order['event_status']}")

    order_id = order["order_id"]
    cart = await database.fetch_one(
        "SELECT * FROM cart WHERE order_id = :id", values={"id": order_id}
    )
    cfg = await database.fetch_one(
        "SELECT * FROM cart_config WHERE cart_id = :id", values={"id": cart["cart_id"]}
    )

    # Apply coupon if provided
    coupon_amt = 0.0
    coupon_pct = None
    if req.coupon_code:
        coupon = await database.fetch_one(
            """
            SELECT * FROM coupons
            WHERE UPPER(code) = UPPER(:code)
              AND status = 'Active'
              AND is_active = TRUE
              AND valid_from <= CURRENT_DATE
              AND valid_to   >= CURRENT_DATE
              AND (usage_limit IS NULL OR usage_count < usage_limit)
            """,
            values={"code": req.coupon_code},
        )
        if coupon:
            total = float(cart["total_wo_discount"])
            min_val = float(coupon["minimum_cart_value"] or 0)
            if total >= min_val:
                if coupon["discount_pct"]:
                    coupon_pct = float(coupon["discount_pct"])
                    coupon_amt = round(total * coupon_pct / 100, 2)
                    if coupon["max_discount_amt"]:
                        coupon_amt = min(coupon_amt, float(coupon["max_discount_amt"]))
                elif coupon["discount_amt"]:
                    coupon_amt = float(coupon["discount_amt"])

                await database.execute(
                    """
                    UPDATE cart SET
                        fk_coupon_id = :coupon_id,
                        coupon_code  = :code,
                        coupon_pct   = :pct,
                        coupon_amt   = :amt,
                        total_payable = total_payable - :amt,
                        balance_due   = total_payable - :amt
                    WHERE cart_id = :cart_id
                    """,
                    values={
                        "coupon_id": coupon["coupon_id"],
                        "code": req.coupon_code,
                        "pct": coupon_pct,
                        "amt": coupon_amt,
                        "cart_id": cart["cart_id"],
                    },
                )
                # Increment usage count
                await database.execute(
                    "UPDATE coupons SET usage_count = usage_count + 1 WHERE coupon_id = :id",
                    values={"id": coupon["coupon_id"]},
                )

    # Snapshot cart_config → json_booking_snapshot
    await database.execute(
        """
        UPDATE cart_config
        SET json_booking_snapshot = to_jsonb(cart_config.*)
        WHERE cart_id = :cart_id
        """,
        values={"cart_id": cart["cart_id"]},
    )

    # Move order status → Awaiting Advance
    await database.execute(
        "UPDATE orders SET event_status = 'Awaiting Advance' WHERE order_id = :id",
        values={"id": order_id},
    )
    await database.execute(
        "UPDATE cart SET status = 'Confirmed' WHERE cart_id = :id",
        values={"id": cart["cart_id"]},
    )

    # Generate order_item rows from cart_config
    # Pricing sourced from pricing_model for the order's pincode
    pm = await database.fetch_one(
        """
        SELECT pm.*
        FROM mapping_pricing_pincode mpp
        JOIN pricing_models pm ON pm.id = mpp.fk_pricing_model_id
        WHERE mpp.pincode = :pincode AND mpp.is_active = TRUE AND pm.is_active = TRUE
        LIMIT 1
        """,
        values={"pincode": order["pincode"]},
    )
    if not pm:
        cfg_row = await database.fetch_one(
            "SELECT config_value FROM platform_config WHERE config_key = 'default_pricing_model_id'"
        )
        if cfg_row:
            pm = await database.fetch_one(
                "SELECT * FROM pricing_models WHERE id = :id",
                values={"id": int(cfg_row["config_value"])},
            )

    line_items = []
    if pm and cfg:
        if cfg["fk_decor_theme_id"] and pm["decor_theme_price"]:
            line_items.append(("decor", "decor_theme", cfg["fk_decor_theme_id"], 1, pm["decor_theme_price"]))
        if cfg["host_tier"] and pm["host_price"]:
            # Find a host matching the tier for entity reference
            host = await database.fetch_one(
                "SELECT host_id FROM host_master WHERE host_tier = :tier AND is_active = TRUE LIMIT 1",
                values={"tier": cfg["host_tier"]},
            )
            if host:
                line_items.append(("host", "host_master", host["host_id"], 1, pm["host_price"]))
        if cfg["dj_tier"] and cfg["dj_tier"] != "None" and pm["dj_price"]:
            line_items.append(("dj", "dj_master", 0, 1, pm["dj_price"]))
        if cfg["pinata_category"] and cfg["pinata_category"] != "None" and pm["pinnata_price"]:
            line_items.append(("pinata", "pinata_master", 0, 1, pm["pinnata_price"]))
        if cfg["fk_einvite_id"] and pm["einvite_price"]:
            line_items.append(("einvite", "einvite_master", cfg["fk_einvite_id"], 1, pm["einvite_price"]))
        if cfg["photographer_pack"] and cfg["photographer_pack"] != "None" and pm["photographer_price"]:
            line_items.append(("photographer", "photographer_master", 0, 1, pm["photographer_price"]))
        if cfg["json_activity"] and pm["activities_price"]:
            activities = cfg["json_activity"] if isinstance(cfg["json_activity"], list) else []
            for act in activities:
                line_items.append(("activity", "activities_master",
                                   act.get("activity_id", 0), act.get("qty", 1),
                                   pm["activities_price"]))

    for (type_, entity_table, entity_id, qty, price) in line_items:
        await database.execute(
            """
            INSERT INTO order_item
                (order_id, type, entity_table, fk_entity_id, quantity, display_price)
            VALUES
                (:order_id, :type, :entity_table, :entity_id, :qty, :price)
            """,
            values={
                "order_id": order_id, "type": type_, "entity_table": entity_table,
                "entity_id": entity_id, "qty": qty, "price": price,
            },
        )

    # Compute advance amount
    adv_cfg = await database.fetch_one(
        "SELECT config_value FROM platform_config WHERE config_key = 'advance_pct'"
    )
    adv_pct = float(adv_cfg["config_value"]) / 100 if adv_cfg else 0.5
    final_cart = await database.fetch_one(
        "SELECT total_payable FROM cart WHERE cart_id = :id",
        values={"id": cart["cart_id"]},
    )
    advance_due = round(float(final_cart["total_payable"]) * adv_pct, 2) if final_cart else 0.0

    return {
        "confirmed": True,
        "event_code": req.event_code,
        "event_status": "Awaiting Advance",
        "advance_due": advance_due,
        "order_items_created": len(line_items),
    }
