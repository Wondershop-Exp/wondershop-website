"""
Grand Total for the admin booking page.

2026-09-24, per Shruti (rewrite from scratch): "the earlier logic ... was
good where it was the total of all activities selected minus the discount.
that's how it should be irrespective of the source of lead creation ...
look at the code from scratch and fix this."

WHY THIS WAS REWRITTEN — the previous design (2026-09-21 → 2026-09-23)
priced every admin change as a DIFFERENCE from `leads.builder_snapshot`
(what was booked at checkout), so Grand Total = client_budget + (sum of
deltas). That only works when builder_snapshot faithfully records exactly
what was priced in at checkout — true for website (BAB) orders, but
sales-originated bookings never reliably populate it the same way:
  - Missing entirely -> every admin override looked like a brand new
    addition on top of the checkout total (double-counting, 2026-09-24
    "why is the total so different" — Rs.1,03,500 instead of Rs.86,000).
  - Backfilled from a booking's CURRENT overrides (an attempted one-off
    fix) -> anything added on the admin page after conversion got
    silently treated as if it had already been priced in at checkout, so
    it dropped OUT of the total instead (under-counting, "activities
    should be 67500 ... it's not adding up").
Both failures trace back to the same root cause: using a DIFF against a
snapshot that may not describe the truth. The fix is to stop diffing
against anything and price the booking fresh, every time, from whatever
is actually selected right now.

NEW DESIGN — no more snapshot, no more deltas:

  Total MRP   = sum of the catalogue price of every CURRENTLY selected
                service / add-on / activity / gift (the admin override if
                there is one, otherwise whatever the customer originally
                submitted) — using the exact same catalogue prices the
                public site and this admin page's own dropdowns show.
  Discount    = Total MRP x Discount % (Discount % is just another
                overridable field on the page, unchanged — a website
                order's % comes from the site's own discount slabs at
                checkout, a sales order's % is whatever was negotiated
                and typed in; the formula applying it is identical for
                both, which is the whole point — "that's how it should be
                irrespective of the source of lead creation").
  Grand Total = (Total MRP − Discount) + non-discounted extra fees
                (Gift Packaging / Thank-you Note / Cash Collection Fee —
                these are charged on top at checkout too, never
                discounted, so they stay outside the discountable MRP).

There is nothing left to fall out of sync: change a service on the admin
page and its new catalogue price is simply summed in on the next load, no
matter what (if anything) `builder_snapshot` says.

A field with no catalogue price match at all (legacy free text, a custom
name that doesn't match today's catalogue) is listed in "unpriced" so the
admin page can flag it instead of silently mispricing it, rather than
being guessed at.

`compute_adjustments()` below (the OLD delta-vs-snapshot calculation) is
kept, UNCHANGED, purely to annotate the invoice PDF with "what changed
since checkout" line items — a cosmetic, secondary use that was never the
source of the Grand Total bug (see send_booking_invoice() in admin.py).
It is no longer used to derive Grand Total itself.

Pure functions, no database access, so they can be unit-tested directly.
"""
from typing import Optional

import catalogue_data as cat

# Mirrors builder.html (PACKAGING_UNIT_PRICE / TAG_NOTE_* / add-on prices) —
# keep in sync by hand, same convention as catalogue_data.py.
PACKAGING_UNIT_PRICE = {"paper-bag": 35, "wrap": 30, "both": 60}
TAG_NOTE_UNIT_PRICE = 10
TAG_NOTE_MIN_QTY = 15
DJ_LIGHTS_PRICE = 1500
DJ_SMOKE_PRICE = 2000
# 2026-09-22, per Shruti — Piñata Bags admin dropdown (Add-ons section):
# flat per-bag rate, deliberately no MOQ/tiering ("don't add an MOQ, just
# give per bag pricing"). Not yet priced into Total MRP below — the admin
# field for it is a free-text "Assign..." box with no quantity captured
# anywhere, same as before this rewrite.
PINATA_BAG_PRICE = 15
# Mirrors leads.py's _COLLECTION_FEE (Rs.100 flat surcharge for "Cash
# Collection at Venue") — kept in sync by hand.
COLLECTION_FEE = 100
# 2026-09-24, per Shruti test booking ("so is the invite for Rs. 500") —
# E-Invite pricing is genuinely DB-driven site-side (einvite_master has no
# static price; the real charge comes from a per-order pricing_matrix
# lookup cart.py does live), so there's no catalogue table this pure
# function can look up by design name. This mirrors platform_config's own
# 'einvite_charge' seed value (see migrations/001_initial_schema.sql) — a
# flat charge whenever a design is picked. Good enough to price a normal
# E-Invite selection correctly; a future pass could look the real price up
# from einvite_master/pricing_matrix if Shruti needs per-design accuracy.
EINVITE_FLAT_CHARGE = 500

# Admin dropdown label  <->  builder key for Gift Packaging.
PACKAGING_LABEL_TO_KEY = {
    "Paper Gift Bag": "paper-bag",
    "Gift Wrap": "wrap",
    "Gift Wrap + Paper Bag": "both",
    "No packaging": None,
}
PACKAGING_KEY_TO_LABEL = {v: k for k, v in PACKAGING_LABEL_TO_KEY.items() if v}

_STD_DECOR_NAMES = {
    "Classic": "Classic Balloon Arch", "Premium": "Premium Decor",
    "Luxury": "Luxury Decor", "Signature": "Signature Decor",
}


def _decor_prices() -> dict:
    out = {}
    for theme in cat.THEMES:
        overrides = theme.get("tierOverrides") or {}
        for tier in theme["tierPhotos"].keys():
            # A theme+tier can override the shared DECOR_TIER_META price
            # (e.g. Frozen's Classic at ₹9000, Paw Patrol's Classic at
            # ₹4500) — added 2026-09-26, mirrors builder.html's THEME_TIERS
            # price = ov.price ?? tier default logic. Without this, any
            # overridden theme+tier priced here at the plain tier default
            # would silently disagree with what the customer actually paid.
            tier_override = overrides.get(tier) or {}
            price = tier_override.get("price", cat.DECOR_TIER_META[tier]["price"])
            out[f'{theme["n"]} - {tier}'] = price
    for tier, name in _STD_DECOR_NAMES.items():
        out[name] = cat.DECOR_TIER_META[tier]["price"]
    return out


DECOR_PRICES = _decor_prices()
ACTIVITY_PRICES = {n: (p, flat) for _id, n, p, flat in cat.ACTIVITIES}
GIFT_PRICES = {n: p for _id, n, _img, p in cat.GIFTS}


# ─── small helpers ─────────────────────────────────────────────────────────

def money(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("₹", "").replace("Rs.", "").strip())
    except ValueError:
        return None


def parse_csv(s: Optional[str], with_qty: bool = False) -> list:
    """'A, B x2' -> [(name, qty)] — the same format the admin multi-picker saves."""
    import re
    out = []
    for seg in (s or "").split(","):
        seg = seg.strip()
        if not seg:
            continue
        qty = 1
        if with_qty:
            m = re.match(r"^(.*)\s+x(\d+)$", seg, flags=re.I)
            if m:
                seg, qty = m.group(1).strip(), int(m.group(2)) or 1
        out.append((seg, qty))
    return out


def freebie_activity_names(snap: dict) -> list:
    """Activities the customer got FREE at checkout (the Tattoo Station unlocked
    by the discount slabs is saved in the snapshot with id a15 and price 0)."""
    names = []
    for a in (snap or {}).get("activities") or []:
        if a.get("id") == "a15" and (money(a.get("p")) or 0) == 0 and a.get("n"):
            names.append(a["n"])
    return names


def _swap_delta(paid, orig_cat, cur_cat):
    """Price change for swapping one tiered service for another. Normally
    (customer paid the catalogue price) that is new − old. If the customer got
    a special price at checkout (included in a package, discounted…), only
    count an increase so the swap never refunds money that was never charged."""
    paid = paid or 0.0
    if orig_cat is not None and abs(paid - orig_cat) < 0.5:
        return cur_cat - orig_cat
    return max(0.0, cur_cat - (orig_cat if orig_cat is not None else paid))


# ─── OLD delta-vs-checkout calculation — kept only for the invoice's ──────
# "what changed since checkout" annotations (send_booking_invoice() in
# admin.py). No longer used to derive Grand Total — see module docstring.

def compute_adjustments(lead: dict, snap: dict, cur: dict, removed: set) -> dict:
    """cur: field_key -> current value string (override, else the original);
    removed: field keys the admin marked removed.

    Returns {"sub": [(label, amount)...], "extra": [(label, amount)...],
             "unpriced": [label...]} — sub = changes to the pre-discount
    subtotal, extra = changes to the un-discounted fees (packaging / note)."""
    snap = snap or {}
    sub, extra, unpriced = [], [], []
    kids = int(lead.get("kids_count") or snap.get("kids_count") or 0)

    def add(bucket, label, amount):
        if amount and abs(amount) > 0.001:
            bucket.append((label, round(float(amount), 2)))

    # ── tiered single-choice services ─────────────────────────────────────
    def tiered(key, label, snap_key, orig_name_field, cat_price):
        s = snap.get(snap_key) or None
        orig_name = (s or {}).get(orig_name_field) if s else None
        paid = money((s or {}).get("p")) if s else 0.0
        now = None if key in removed else (cur.get(key) or orig_name)
        if key in removed and orig_name:
            add(sub, f"{label} removed ({orig_name})", -(paid or 0.0))
            return
        if not now or now == orig_name:
            return
        new_p = cat_price(now)
        if new_p is None:
            unpriced.append(f"{label}: {now}")
            return
        if not orig_name:
            add(sub, f"{label} added ({now})", new_p)
        else:
            add(sub, f"{label}: {orig_name} → {now}",
                _swap_delta(paid, cat_price(orig_name), new_p))

    tiered("svc_decor", "Decor", "decor", "n", lambda n: DECOR_PRICES.get(n))
    tiered("svc_host", "Host", "host", "tier", lambda n: cat.HOST_TIER_PRICES.get(n))
    tiered("svc_dj", "Music", "dj", "tier", lambda n: cat.DJ_TIER_PRICES.get(n))
    tiered("svc_photo", "Photography", "photo", "tier", lambda n: cat.PHOTO_TIER_PRICES.get(n))
    tiered("svc_pinata", "Piñata", "pinata", "n", lambda n: cat.PINATA_TIER_PRICES.get(n))

    # ── music add-ons ─────────────────────────────────────────────────────
    addons = snap.get("dj_addons") or {}
    for key, label, was_on, price in (
        ("addon_dj_lights", "Music lights", bool(addons.get("lights")), DJ_LIGHTS_PRICE),
        ("addon_dj_smoke", "Smoke machine", bool(addons.get("smoke")), DJ_SMOKE_PRICE),
    ):
        val = "No" if key in removed else cur.get(key)   # a removed add-on row = switched off
        if val not in ("Yes", "No"):
            continue
        now_on = val == "Yes"
        if now_on and not was_on:
            add(sub, f"{label} added", price)
        elif was_on and not now_on:
            add(sub, f"{label} removed", -price)

    # ── activities ────────────────────────────────────────────────────────
    orig_acts = {a["n"]: (money(a.get("p")) or 0.0) for a in (snap.get("activities") or []) if a.get("n")}
    cur_names = [] if "svc_activities" in removed else [n for n, _q in parse_csv(cur.get("svc_activities"))]
    if cur.get("svc_activities") or "svc_activities" in removed:
        for name in cur_names:
            if name not in orig_acts:
                p_flat = ACTIVITY_PRICES.get(name)
                if p_flat is None:
                    unpriced.append(f"Activity: {name}")
                    continue
                p, flat = p_flat
                add(sub, f"Activity added: {name}", p if flat else p * kids)
        for name, paid in orig_acts.items():
            if name not in cur_names:
                add(sub, f"Activity removed: {name}", -paid)

    # ── gifts (+ the fees that follow their quantity) ─────────────────────
    orig_gifts = {g["n"]: (money(g.get("unit")) or 0.0, int(g.get("qty") or 0)) for g in (snap.get("gifts") or []) if g.get("n")}
    orig_qty = sum(q for _u, q in orig_gifts.values())
    if "svc_gifts" in removed:
        cur_gifts = []
    else:
        cur_gifts = parse_csv(cur.get("svc_gifts"), with_qty=True) if cur.get("svc_gifts") else [(n, q) for n, (_u, q) in orig_gifts.items()]
    cur_qty = sum(q for _n, q in cur_gifts)
    gifts_changed = False
    seen = set()
    for name, qty in cur_gifts:
        seen.add(name)
        if name in orig_gifts:
            unit, oq = orig_gifts[name]
            if qty != oq:
                gifts_changed = True
                add(sub, f"Gift {name}: {oq} → {qty}", unit * (qty - oq))
        else:
            unit = GIFT_PRICES.get(name)
            gifts_changed = True
            if unit is None:
                unpriced.append(f"Gift: {name}")
            else:
                add(sub, f"Gift added: {name} × {qty}", unit * qty)
    for name, (unit, oq) in orig_gifts.items():
        if name not in seen:
            gifts_changed = True
            add(sub, f"Gift removed: {name} × {oq}", -unit * oq)

    # packaging fee = per-gift rate × total gift quantity
    orig_pack_key = snap.get("gift_packaging") or None
    orig_pack_cost = money(snap.get("gift_packaging_cost")) or 0.0
    val = "No packaging" if "addon_gift_packaging" in removed else cur.get("addon_gift_packaging")
    pack_key = PACKAGING_LABEL_TO_KEY.get(val, orig_pack_key) if val else orig_pack_key
    if pack_key != orig_pack_key or (gifts_changed and pack_key):
        new_cost = PACKAGING_UNIT_PRICE.get(pack_key, 0) * cur_qty if pack_key else 0.0
        label = "Packaging: " + (cat.PACKAGING_LABELS.get(pack_key) or "none")
        add(extra, label, new_cost - orig_pack_cost)

    # thank-you note fee: 10 per gift, minimum 15 gifts billed
    orig_note_fee = money(snap.get("gift_thank_you_fee")) or 0.0
    orig_note_on = bool(snap.get("gift_thank_you_note"))
    val = "No" if "addon_gift_note" in removed else cur.get("addon_gift_note")
    note_on = (val == "Yes") if val in ("Yes", "No") else orig_note_on
    if note_on != orig_note_on or (gifts_changed and note_on):
        new_fee = max(TAG_NOTE_MIN_QTY, cur_qty) * TAG_NOTE_UNIT_PRICE if (note_on and cur_qty > 0) else 0.0
        add(extra, "Thank-you note" + (" fee" if note_on else " removed"), new_fee - orig_note_fee)

    return {"sub": sub, "extra": extra, "unpriced": unpriced}


# ─── NEW: from-scratch calculation (drives Grand Total everywhere) ───────

def _resolved(cur: dict, key: str, removed: set) -> Optional[str]:
    """The value actually in effect for this field right now — None if the
    admin removed it or nothing is selected."""
    if key in removed:
        return None
    v = cur.get(key)
    return v if v not in (None, "") else None


def _price_activities(names_csv: Optional[str], kids: int):
    """Every currently-selected activity, priced off the same catalogue the
    admin's own picker shows (ACTIVITY_PRICES: price + whether it's flat or
    per-child) — exactly what Shruti described: "1500 x 45" for a per-child
    activity, no snapshot involved at all."""
    items, unpriced = [], []
    for name, _qty in parse_csv(names_csv):
        p_flat = ACTIVITY_PRICES.get(name)
        if p_flat is None:
            unpriced.append(f"Activity: {name}")
            continue
        p, flat = p_flat
        amount = p if flat else p * max(kids, 1)
        detail = "" if flat else f" ({kids} kids × ₹{p:g})"
        items.append((f"Activity: {name}{detail}", amount))
    return items, unpriced


def _price_gifts(gifts_csv: Optional[str], snap: dict):
    """Prefers the unit price actually billed at checkout (from the
    snapshot, when that exact gift is still selected) so an untouched
    gift's price never drifts if the catalogue price changes later;
    anything else (a gift added here, or no snapshot at all) falls back to
    today's catalogue price."""
    orig_units = {g["n"]: money(g.get("unit")) for g in (snap.get("gifts") or []) if g.get("n")}
    items, unpriced = [], []
    total_qty = 0
    for name, qty in parse_csv(gifts_csv, with_qty=True):
        total_qty += qty
        unit = orig_units.get(name)
        if unit is None:
            unit = GIFT_PRICES.get(name)
        if unit is None:
            unpriced.append(f"Gift: {name}")
            continue
        items.append((f"Gift: {name} × {qty}", unit * qty))
    return items, unpriced, total_qty


def compute_billing(lead: dict, snap: dict, cur: dict, removed: set,
                     discount_pct: Optional[float], discount_type: Optional[str] = None,
                     discount_value: Optional[float] = None) -> Optional[dict]:
    """The whole Billing & Rewards picture, computed fresh from whatever is
    currently selected — no diffing against anything. Returns None only
    when this lead has never reached checkout (no client_budget at all —
    same gate the old code used, kept so plain not-yet-booked leads don't
    show a Grand Total out of nowhere).

    Returns {"total_mrp", "discount_pct", "discount_amt", "extra_total",
    "grand_total", "items": [{"label","amount"}...] (the services that make
    up Total MRP), "extra_items": [...] (non-discounted fees), "unpriced":
    [...], plus "subtotal"/"checkout_total" — legacy-named aliases kept so
    send_booking_invoice() doesn't need its own copy of these numbers}."""
    if money(lead.get("client_budget")) is None:
        return None

    snap = snap or {}
    kids = int(lead.get("kids_count") or snap.get("kids_count") or 0)
    items: list = []
    unpriced: list = []

    def add(label, amount):
        if amount:
            items.append((label, round(float(amount), 2)))

    # ── tiered single-choice services ─────────────────────────────────────
    def tiered(key, label, cat_price):
        val = _resolved(cur, key, removed)
        if not val:
            return
        p = cat_price(val)
        if p is None:
            unpriced.append(f"{label}: {val}")
        else:
            add(f"{label}: {val}", p)

    tiered("svc_decor", "Decor", lambda n: DECOR_PRICES.get(n))
    tiered("svc_host", "Host", lambda n: cat.HOST_TIER_PRICES.get(n))
    tiered("svc_dj", "Music", lambda n: cat.DJ_TIER_PRICES.get(n))
    tiered("svc_photo", "Photography", lambda n: cat.PHOTO_TIER_PRICES.get(n))
    tiered("svc_pinata", "Piñata", lambda n: cat.PINATA_TIER_PRICES.get(n))

    if _resolved(cur, "addon_dj_lights", removed) == "Yes":
        add("Music lights", DJ_LIGHTS_PRICE)
    if _resolved(cur, "addon_dj_smoke", removed) == "Yes":
        add("Smoke machine", DJ_SMOKE_PRICE)

    einvite = _resolved(cur, "svc_einvite", removed)
    if einvite and einvite != "No selection":
        add(f"E-Invite: {einvite}", EINVITE_FLAT_CHARGE)

    act_items, act_unpriced = _price_activities(_resolved(cur, "svc_activities", removed), kids)
    for label, amt in act_items:
        add(label, amt)
    unpriced += act_unpriced

    gift_items, gift_unpriced, gift_qty = _price_gifts(_resolved(cur, "svc_gifts", removed), snap)
    for label, amt in gift_items:
        add(label, amt)
    unpriced += gift_unpriced

    total_mrp = round(sum(a for _l, a in items), 2)

    # ── extra fees: charged on top of the discounted total, never
    # discounted (same as at checkout) ─────────────────────────────────────
    extra_items: list = []

    def add_extra(label, amount):
        if amount:
            extra_items.append((label, round(float(amount), 2)))

    pack_val = _resolved(cur, "addon_gift_packaging", removed)
    pack_key = PACKAGING_LABEL_TO_KEY.get(pack_val) if pack_val else None
    if pack_key:
        add_extra(f"Packaging ({PACKAGING_KEY_TO_LABEL.get(pack_key, pack_key)})",
                   PACKAGING_UNIT_PRICE.get(pack_key, 0) * gift_qty)

    if _resolved(cur, "addon_gift_note", removed) == "Yes" and gift_qty > 0:
        add_extra("Thank-you note", max(TAG_NOTE_MIN_QTY, gift_qty) * TAG_NOTE_UNIT_PRICE)

    if lead.get("payment_method") == "collect":
        add_extra("Cash Collection Fee", COLLECTION_FEE)

    extra_total = round(sum(a for _l, a in extra_items), 2)

    # 2026-09-25, per Shruti — "give an option for a value discount or %
    # discount ... give user option to choose from either." bill_discount_type
    # (admin.py FIELD_CATALOG) picks which of these two the admin is
    # editing; discount_value is a flat rupee amount, discount_pct a
    # percentage of Total MRP — same as before when discount_type is
    # unset (every booking before this feature existed) or still "%".
    # A flat discount is capped at Total MRP so it can never push the
    # Grand Total negative, then back-computed to an equivalent % purely
    # for display/consumers that still read discount_pct (the invoice
    # PDF's "Discount X%" line) — the % shown there is descriptive, not
    # the source of truth, when discount_type is "value".
    if discount_type == "value" and discount_value is not None:
        discount_amt = round(min(max(0.0, discount_value), total_mrp), 2)
        pct = round((discount_amt / total_mrp * 100.0), 2) if total_mrp else 0.0
    else:
        pct = discount_pct if discount_pct is not None else 0.0
        discount_amt = round(total_mrp * pct / 100.0, 2)
    grand_total = max(0.0, round(total_mrp - discount_amt + extra_total, 2))

    return {
        "total_mrp": total_mrp,
        "discount_pct": pct,
        "discount_amt": discount_amt,
        "extra_total": extra_total,
        "grand_total": grand_total,
        "items": [{"label": l, "amount": a} for l, a in items],
        "extra_items": [{"label": l, "amount": a} for l, a in extra_items],
        "unpriced": unpriced,
        # legacy-named aliases — send_booking_invoice() in admin.py reads
        # these exact keys, unchanged since before this rewrite.
        "subtotal": total_mrp,
        "checkout_total": money(lead.get("client_budget")),
    }
