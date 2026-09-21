"""
Live Grand Total for the admin booking page (2026-09-21, per Shruti: "grand
total not changing even after making changes at the admin side — changing
the category of the host, adding music, changing the discount %, adding
gifts").

What the customer paid at checkout is fixed in `leads` (client_budget =
payable total, order_grand_total = cart subtotal BEFORE discount, the
builder_snapshot = the services and the prices actually charged). When an
admin then changes something on the booking page — a service tier, an
add-on, the activities or gifts list, the Discount % — this module works out
how far that moves the total, so Grand Total (and Balance Due, which is
Grand Total − Advance) follows the changes.

Rules, kept deliberately simple and explained on the page:

  * Every change is priced as the DIFFERENCE from what was booked. Anything
    the admin has not touched keeps exactly the price the customer was
    charged — so an untouched booking always shows exactly its checkout total.
  * The discount stays the same rupee amount as at checkout (the site's
    discount slabs are flat rupee amounts), unless the admin edits Discount %,
    in which case the new % is applied to the new subtotal. Freebies unlocked
    at checkout (e.g. the free Tattoo Station) stay free.
  * Packaging / thank-you-note fees are not discounted (same as checkout) and
    follow the number of return gifts.
  * Prices for things newly added here come from catalogue_data.py — the same
    list the admin dropdowns show.

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
        for tier in theme["tierPhotos"].keys():
            out[f'{theme["n"]} - {tier}'] = cat.DECOR_TIER_META[tier]["price"]
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


# ─── the calculation ───────────────────────────────────────────────────────

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


def recompute_grand_total(lead: dict, snap: dict, cur: dict, removed: set,
                          orig_discount_pct: Optional[float], new_discount_pct: Optional[float]) -> Optional[dict]:
    """Returns None when the booking has no checkout figures to build on;
    otherwise {"grand_total", "subtotal", "checkout_total", "adjustments":
    [{"label","amount"}], "unpriced": [...]}."""
    client_budget = money(lead.get("client_budget"))
    sub_old = money(lead.get("order_grand_total"))
    if client_budget is None or sub_old is None:
        return None

    adj = compute_adjustments(lead, snap, cur, removed)
    d_sub = sum(a for _l, a in adj["sub"])
    d_extra = sum(a for _l, a in adj["extra"])
    sub_new = max(0.0, sub_old + d_sub)

    adjustments = [{"label": l, "amount": a} for l, a in adj["sub"] + adj["extra"]]
    d_discount = 0.0   # D_old − D_new, added to the total

    # Fees charged on top of the discounted subtotal at checkout.
    snap = snap or {}
    extras_old = ((100.0 if lead.get("payment_method") == "collect" else 0.0)
                  + (money(snap.get("gift_packaging_cost")) or 0.0)
                  + (money(snap.get("gift_thank_you_fee")) or 0.0))
    d_old = sub_old - (client_budget - extras_old)      # rupee discount actually given at checkout
    if not (-0.5 <= d_old <= sub_old + 0.5):             # figures don't reconcile — fall back to the rounded %
        d_old = sub_old * (orig_discount_pct or 0.0) / 100.0

    if (orig_discount_pct is not None and new_discount_pct is not None
            and abs(new_discount_pct - orig_discount_pct) > 1e-9):
        d_new = sub_new * new_discount_pct / 100.0
        d_discount = d_old - d_new
        if abs(d_discount) > 0.001:
            adjustments.append({
                "label": f"Discount {orig_discount_pct:g}% → {new_discount_pct:g}%",
                "amount": round(d_discount, 2),
            })

    grand = max(0.0, client_budget + d_sub + d_extra + d_discount)
    return {
        "grand_total": round(grand, 2),
        "subtotal": round(sub_new, 2),
        # rupee discount shown on the invoice: subtotal + on-top fees − grand total
        "discount_amt": round(max(0.0, sub_new + extras_old + d_extra - grand), 2),
        "checkout_total": client_budget,
        "adjustments": adjustments,
        "unpriced": adj["unpriced"],
    }
