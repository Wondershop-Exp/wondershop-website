"""
Static mirror of the site's product catalogue (decor themes/tiers,
photographer tiers, e-invite templates, pinatas, return gifts) — kept in
sync by hand with the equivalent JS arrays in builder.html. Used only to
resolve a booking's chosen item back to its reference photo / inclusion
list for the order execution form. If a booking's decor/e-invite/pinata id
doesn't match anything here (e.g. a customer picked "Custom Design", or a
package hand-off used a non-catalogue id), the resolver returns None and
the order form simply leaves that spot blank — never fabricates a photo.

Source of truth is builder.html; if the catalogue changes there, mirror
the change here too. Last synced: 2026-08-12.
"""
import re
from typing import Optional

SITE_BASE_URL = "https://www.wondershopexperiences.com"

# ─── Decor ──────────────────────────────────────────────────────────────

DECOR_TIER_META = {
    "Classic": {
        "price": 6500,
        "spec": [
            ("Panels", "NA", True),
            ("Balloons", "Up to 200", False),
            ("Balloon Colours", "Up to 2", False),
            # 2026-09-13, per Shruti — split out of the old combined "Happy
            # Birthday, Name & Age" row: generic HBD bunting + age balloon
            # stay included, but the child's actual NAME on the bunting is
            # now a separate ₹200 add-on (see decor_name_bunting_fee in
            # leads.py) — mirrors the same split in builder.html's
            # DECOR_TIER_META.
            ("Happy Birthday & Age", "Paper bunting (HBD), foil balloon (age)", False),
            ("Name on Bunting", "Not included — add for ₹200", True),
            ("Cutouts", "Not included", True),
            ("Welcome Decor", "Not included", True),
            ("Cake Table", "Not included", True),
            ("Decor Width", "5-6 ft", False),
        ],
    },
    "Premium": {
        "price": 11000,
        "spec": [
            ("Panels", "1", False),
            ("Balloons", "Up to 300", False),
            ("Balloon Colours", "Up to 3", False),
            ("Happy Birthday, Name & Age", "Flex print or LED light (HBD & name), foil balloon (age)", False),
            ("Cutouts", "As per reference photo", False),
            ("Welcome Decor", "Not included", True),
            ("Cake Table", "Not included", True),
            ("Decor Width", "5-6 ft", False),
        ],
    },
    "Luxury": {
        "price": 18000,
        "spec": [
            ("Panels", "2", False),
            ("Balloons", "Up to 400", False),
            ("Balloon Colours", "__THEME__", False),
            ("Happy Birthday, Name & Age", "Flex print or LED light (HBD & name), 3ft age light", False),
            ("Cutouts", "As per reference photo", False),
            ("Welcome Decor", "Welcome board", False),
            ("Cake Table", "Included", False),
            ("Decor Width", "8-9 ft", False),
        ],
    },
    "Signature": {
        "price": 25000,
        "spec": [
            ("Panels", "3", False),
            ("Balloons", "Up to 500", False),
            ("Balloon Colours", "__THEME__", False),
            ("Happy Birthday, Name & Age", "Flex print or LED light (HBD & name), 3ft age light", False),
            ("Cutouts", "As per reference photo", False),
            ("Welcome Decor", "Welcome board + welcome arch", False),
            ("Cake Table", "As per reference photo", False),
            ("Decor Width", "12-14 ft", False),
        ],
    },
}
_PRICE_TO_TIER = {v["price"]: k for k, v in DECOR_TIER_META.items()}

# id, name, balloon-colour source field, tier->reference-photo map
THEMES = [
    {"id": "uni", "n": "Unicorn Magic", "b": "150 (Pink, Purple, White)",
     "tierPhotos": {"Classic": "Decor/decor-uni-arch.jpg", "Premium": "Decor/decor-uni-1panel.jpg",
                    "Luxury": "Decor/decor-uni-2panel.jpg", "Signature": "Decor/decor-uni-3panel.jpg"}},
    {"id": "jungle", "n": "Jungle Safari", "b": "200 (Green, Yellow, Orange)",
     "tierPhotos": {"Signature": "Decor/decor-jungle-3panel.jpg"}},
    {"id": "hero", "n": "Superhero", "b": "150 (Red, Blue, Yellow)",
     "tierPhotos": {"Classic": "Decor/decor-hero-arch.jpg", "Premium": "Decor/decor-hero-1panel.jpg",
                    "Luxury": "Decor/decor-hero-2panel.jpg", "Signature": "Decor/decor-hero-extra1.jpg"}},
    {"id": "space", "n": "Space Explorer", "b": "180 (Blue, Purple, Silver)",
     "tierPhotos": {"Classic": "Decor/decor-space-arch.jpg", "Premium": "Decor/decor-space-1panel.jpg"}},
    {"id": "spy", "n": "Mystery & Spy", "b": "120 (Black, Gold, Red)",
     "tierPhotos": {"Classic": "Decor/decor-spy-arch.jpg", "Premium": "Decor/decor-spy-1panel.jpg",
                    "Luxury": "Decor/decor-spy-2panel.jpg", "Signature": "Decor/decor-spy-3panel.jpg"}},
    {"id": "kpop", "n": "K-Pop Party", "b": "180 (Purple, Pink, Black)",
     "tierPhotos": {"Classic": "Decor/decor-kpop-arch.jpg", "Premium": "Decor/decor-kpop-1panel.jpg",
                    "Luxury": "Decor/decor-kpop-luxury.png", "Signature": "Decor/decor-kpop-3panel.jpg"}},
    {"id": "hp", "n": "Harry Potter", "b": "180 (Black, Gold, Red)",
     "tierPhotos": {"Classic": "Decor/decor-hp-arch.jpg", "Premium": "Decor/decor-hp-1panel.jpg", "Signature": "Decor/decor-hp-3panel.jpg"},
     "retiredTiers": ["Signature"]},   # no longer on the website (kept for older bookings)
    {"id": "art", "n": "Art & Paint Party", "b": "150 (Colorful mix)",
     "tierPhotos": {"Classic": "Decor/decor-art-classic.png", "Premium": "Decor/decor-art-1panel.jpg", "Luxury": "Decor/decor-art-2panel.jpg"}},
    {"id": "science", "n": "Science Party", "b": "150 (Blue, Green, White)",
     "tierPhotos": {"Premium": "Decor/decor-science-1panel.jpg"}},
    {"id": "racing", "n": "Race Track & Cars", "b": "150 (Black, Red, Yellow)",
     "tierPhotos": {"Luxury": "Decor/decor-racing-2panel.jpg"}},
    {"id": "football", "n": "Football Party", "b": "150 (Green, Black, White)",
     "tierPhotos": {"Classic": "Decor/decor-football-arch.jpg", "Premium": "Decor/decor-football-1panel.jpg",
                    "Luxury": "Decor/decor-football-2panel.jpg", "Signature": "Decor/decor-football-3panel.jpg"}},
    {"id": "craftbazaar", "n": "Indian Craft Bazaar", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-craftbazaar-3panel.jpg"}},
    {"id": "indianpalace", "n": "Indian Palace", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-indianpalace-3panel.jpg"}},
    {"id": "railways", "n": "Indian Railways", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-railways-3panel.jpg"}},
    {"id": "katseye", "n": "Katseye", "b": "150 (mixed colours)",
     "tierPhotos": {"Classic": "Decor/decor-katseye-classic.png", "Signature": "Decor/decor-katseye-3panel.jpg"},
     "tierOverrides": {"Signature": {"price": 30000, "extraSpec": [("Floor Flex", "Included", False), ("Neon Light Strip", "Included", False)]}}},
    {"id": "stitch", "n": "Lilo & Stitch", "b": "150 (Blue, Turquoise, White)",
     "tierPhotos": {"Premium": "Decor/decor-stitch-1panel.jpg"},
     "tierOverrides": {"Premium": {"price": 18000}}},
    {"id": "malgudi", "n": "Malgudi Days", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-malgudi-3panel.jpg"}},
    {"id": "mithai", "n": "Mithai Theme", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-mithai-3panel.jpg"}},
    {"id": "nanighar", "n": "Nani ka Ghar", "b": "150 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-nanighar-3panel.jpg"}},
    {"id": "treasure", "n": "The Great Ancient Indian Treasure", "b": "200 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-treasure-3panel.jpg"}},
    # The following three were missing from this backend mirror even though
    # they're live on builder.html — each theme+tier's real price is
    # DECOR_TIER_META's shared default UNLESS a tierOverrides entry below
    # says otherwise (mirrors builder.html's THEME_TIERS tierOverrides).
    # Added 2026-09-26 while wiring in Shruti's new Cricket/Paw-Patrol-Classic
    # photos — without an entry here, DECOR_PRICES (booking_pricing.py)
    # has no price for these themes' tiers, so admin's Grand Total shows
    # them under "Not priced automatically" instead of pricing them.
    {"id": "frozen", "n": "Frozen", "b": "150 (Blue, White, Silver)",
     "tierPhotos": {"Classic": "Decor/decor-frozen-classic-net.png"},
     "tierOverrides": {"Classic": {"price": 9000, "extraSpec": [("Backdrop", "Light-up net with fairy lights", False)]}}},
    {"id": "pawpatrol", "n": "Paw Patrol", "b": "200 (Blue, Red, Yellow, White)",
     "tierPhotos": {"Classic": "Decor/decor-pawpatrol-classic.png", "Premium": "Decor/decor-pawpatrol-premium.png"},
     "tierOverrides": {"Classic": {"price": 4500, "extraSpec": [("Decor Style", "Wall-mounted balloon cluster (no arch/panel)", False)]}}},
    {"id": "cricket", "n": "Cricket Party", "b": "200 (Green, White, Maroon, Gold)",
     "tierPhotos": {"Classic": "Decor/decor-cricket-classic.png"}},
    # Sustainable LED Decor (2026-10-08, per Shruti) — works with any theme
    # (anyTheme: not offered as a party theme); its own inclusions replace
    # the shared Signature spec. Mirrors builder.html.
    {"id": "ledscreen", "n": "Sustainable LED Decor", "b": "As per theme", "anyTheme": True,
     "tierPhotos": {"Signature": "Decor/decor-sustainable-led-signature.jpg"},
     "tierOverrides": {"Signature": {"price": 25000, "spec": [
         ("Backdrop", "6 × 6 ft LED screen mounted on a platform — your theme & the birthday child's name on screen", False),
         ("Welcome Decor", "Balloon welcome arch + A3 welcome board", False),
         ("Cutouts", "Theme-based cutouts", False),
         ("Sustainable", "No flex printing — the design is shown on a reusable LED screen", False),
         ("Needed from you", "1 table and an electrical plug point", False),
     ]}}},
]
# More photos of a design (builder.html tierExtraPhotos) — shown on the
# decor options page (decor-options.html, 2026-10-08).
TIER_EXTRA_PHOTOS = {
    "spy": {
        "Premium": [
            "Decor/decor-spy-premium-2.png",
            "Decor/decor-spy-premium-3.jpeg",
            "Decor/decor-spy-premium-4.jpg"
        ],
        "Classic": [
            "Decor/decor-spy-classic-sustainable.png"
        ],
        "Signature": [
            "Decor/decor-spy-kpop-3panel.jpg"
        ]
    },
    "racing": {
        "Luxury": [
            "Decor/decor-racing-luxury-alt.png"
        ]
    },
    "craftbazaar": {
        "Signature": [
            "Decor/decor-craftbazaar-3panel-alt.jpg"
        ]
    },
    "malgudi": {
        "Signature": [
            "Decor/decor-malgudi-3panel-alt.jpg"
        ]
    }
}
for _t in THEMES:
    _t["tierExtraPhotos"] = TIER_EXTRA_PHOTOS.get(_t["id"], {})
_THEMES_BY_ID = {t["id"]: t for t in THEMES}

# Theme-preference-only themes (2026-10-02, per Shruti — "add among us and
# imposter in themes on page 0 of BAB"): offered in builder.html's Theme
# Preference dropdown (PREF_ONLY_THEMES there) but they have no decor
# designs yet, so they are NOT decor THEMES above. Used for theme labels in
# emails and the theme pickers in admin / the sales module.
PREF_ONLY_THEMES = [{"id": "among-us", "n": "Among Us"}, {"id": "imposter", "n": "Imposter"}]
# Every theme a customer can pick as their party theme, by display name.
THEME_PREFERENCE_NAMES = sorted([t["n"] for t in THEMES if not t.get("anyTheme")] + [t["n"] for t in PREF_ONLY_THEMES], key=str.lower)

STD_META = {
    "Classic": "Decor/Standard Classic Balloon Arch.jpg",
    "Premium": "Decor/Standard - Premium 1 panel decor.jpg",
    "Luxury": "Decor/Standard - Luxury 2 panel decor.jpg",
    "Signature": "Decor/Standard Signature 3 Panel Decor.jpg",
}


def _extract_colors(b: Optional[str]) -> str:
    if not b:
        return "As per theme"
    m = re.search(r"\(([^)]+)\)", b)
    return m.group(1) if m else "As per theme"


def resolve_decor(decor_id: Optional[str], decor_price: Optional[float]) -> Optional[dict]:
    """Matches a booking's decor id (and, as a fallback, its price) back to
    a reference photo + included/not-included spec list. Returns None if
    nothing matches confidently — the form leaves the spot blank rather
    than showing a possibly-wrong photo."""
    if not decor_id:
        return None
    decor_id = str(decor_id)
    price_tier = _PRICE_TO_TIER.get(int(decor_price)) if decor_price else None

    theme = None
    tier = None

    if decor_id.startswith("std"):
        tier = decor_id.split("-", 1)[1].capitalize() if "-" in decor_id else price_tier
        tier = tier if tier in STD_META else price_tier
        if tier and tier in STD_META:
            return {
                "image_path": f"img/{STD_META[tier]}",
                "spec": _spec_for("Standard Decor", tier, colors="As per theme"),
                "reference": True,   # a standard-decor photo, not this design
            }
        return None

    # Try "<themeId>-<tier>" split (main BAB flow + spy/turf package hand-off)
    if "-" in decor_id:
        prefix, suffix = decor_id.rsplit("-", 1)
        if prefix in _THEMES_BY_ID and suffix.capitalize() in DECOR_TIER_META:
            theme, tier = _THEMES_BY_ID[prefix], suffix.capitalize()

    # Bare theme id (e.g. unicorn/jungle package hand-off) — tier comes from price
    if theme is None and decor_id in _THEMES_BY_ID:
        theme = _THEMES_BY_ID[decor_id]
        tier = price_tier

    if theme is None:
        return None

    photo = theme["tierPhotos"].get(tier) if tier else None
    if not photo and len(theme["tierPhotos"]) == 1:
        # Only one tier ever had a photo for this theme — safe to assume it.
        tier = next(iter(theme["tierPhotos"]))
        photo = theme["tierPhotos"][tier]
    if not photo:
        return None

    return {
        "image_path": f"img/{photo}",
        "spec": _spec_for(theme["n"], tier, colors=_extract_colors(theme["b"]), theme=theme),
        "reference": False,   # the chosen design's own photo
    }


def _spec_for(label: str, tier: str, colors: str, theme: Optional[dict] = None) -> list:
    own = (((theme or {}).get("tierOverrides") or {}).get(tier) or {}).get("spec")
    if own:   # a design with its own inclusions (Sustainable LED Decor)
        return list(own)
    meta = DECOR_TIER_META.get(tier)
    if not meta:
        return []
    out = []
    for l, v, na in meta["spec"]:
        if v == "__THEME__":
            v = colors
        out.append((l, v, na))
    extra = (((theme or {}).get("tierOverrides") or {}).get(tier) or {}).get("extraSpec") or []
    return out + [tuple(x) for x in extra]


# ─── Photographer ───────────────────────────────────────────────────────

PHOTO_TIER_FEATURES = {
    "Classic": ["1 photographer", "Output: Edited photos over drive link"],
    "Premium": ["1 photographer", "Photo + video content shoot",
                "Output: Edited photos, candid photos"],
    "Signature": ["1 photographer + 1 videographer", "Photo + video content shoot",
                  "Output: Edited photos, full event video (captured moments), candid photos"],
}

# ─── Tier pricing (Host / Music / Photographer / Piñata) ──────────────────
# Mirrors the tier-card prices hardcoded in builder.html's static HTML
# (id="hostCards"/"djCards"/Photographer step) and the PINATAS JS array —
# used only to show "Tier - Rs. Price" in the admin dropdowns (2026-08-18,
# per Shruti). Keep in sync by hand if those prices ever change.
HOST_TIER_PRICES = {"Premium": 10000, "Signature": 15000}   # simplified from 3 tiers to 2, 2026-08-19 per Shruti (old 'Classic'/'Premium'/'Signature' -> 'Premium'/'Signature')
DJ_TIER_PRICES = {"Classic": 7000, "Premium": 11000}   # Music has no Signature tier
PHOTO_TIER_PRICES = {"Classic": 6000, "Premium": 10000, "Signature": 18000}
PINATA_TIER_PRICES = {
    "Square Pinata": 2000, "Circle Pinata": 2100, "Number Pinata": 2400,
    "Readymade Pinata": 500,   # "Custom Design" has no fixed price — quoted separately
}


# ─── E-Invite ────────────────────────────────────────────────────────────

# Video invite tier pricing (2026-09-17, per Shruti — sales module e-invite
# section). Not part of the main builder.html gallery flow (that's flat
# ₹500/design + a ₹1,000 Custom Design tier); mirrors the two-tier system
# used on the standalone theme pages instead (unicorn-basic.html /
# spy-basic.html / turf-basic.html's EINVITE_TIERS), since that is what
# actually offers a video option. Keep in sync by hand if those change.
EINVITE_TIER_PRICES = {"Static": 500, "Video + Reminder": 2000}
# 2026-10-01, per Shruti — "einvite and save the date, by default show 500
# rs." Save the Date's list price (was quoted per lead with no list price).
SAVE_THE_DATE_PRICE = 500


def host_tier_for_quote(cost):
    """2026-10-01, per Shruti — "host - match to the upper tier. example -
    12k to be matched to signature quote 15k ... for quotes above 15, keep
    the mrp as blank and add the sales quote figure in the mrp total."
    The cheapest tier whose list price is >= the quoted cost (<=10k ->
    Premium 10k, up to 15k -> Signature 15k). None when the quote is above
    every tier — the quote itself is then the MRP. Used by the sales panel's
    breakup AND when the booking is created, so both price the host alike."""
    try:
        c = float(cost)
    except (TypeError, ValueError):
        return None
    fits = [(p, t) for t, p in HOST_TIER_PRICES.items() if p >= c]
    return min(fits)[1] if fits else None


def custom_host_label(cost) -> str:
    """Booking value for a host quoted above every tier, e.g. 'Custom (₹18,000)'.
    booking_pricing reads the rupee figure back out of it as the MRP."""
    c = float(cost)
    return f"Custom (₹{int(c):,})" if c == int(c) else f"Custom (₹{c:,.2f})"

INVITES = [
    ("i1", "Art Party", "art-party.jpg"), ("i2", "Frozen (Elsa)", "frozen-elsa.jpg"),
    ("i3", "Frozen (Anna)", "frozen-anna.jpg"), ("i4", "Ramayana", "ramayana.jpg"),
    ("i5", "Little Singham", "little-singham.png"), ("i6", "Spy × K-Pop", "spy-kpop.jpg"),
    ("i7", "Spy Detective", "spy-detective.jpg"), ("i8", "Spy Party (Classic)", "spy-party-classic.jpg"),
    ("i9", "Spy Squad", "spy-squad.jpg"), ("i10", "Unicorn", "unicorn.jpg"),
    ("i11", "Superhero (3D)", "superhero-3d.jpg"), ("i12", "Superhero (Pop Art)", "superhero-popart.jpg"),
    ("i13", "Football × Spy Mission", "football-spy.jpg"),
    ("i14", "Football × Spy Mission (Alt)", "football-spy-alt.jpg"),
    ("i15", "Harry Potter", "harry-potter.jpg"), ("i16", "Imposter Mission", "imposter-mission.jpg"),
    ("i17", "Imposter Mission (Alt)", "imposter-mission-alt.jpg"),
    ("i18", "K-Pop Idol Collage", "kpop-idol-collage.jpg"), ("i19", "K-Pop Bestie", "kpop-bestie.jpg"),
    ("i20", "K-Pop Girl Group (Red)", "kpop-girlgroup-red.jpg"),
    ("i21", "K-Pop Girl Group (Green)", "kpop-girlgroup-green.jpg"),
    ("i22", "Lilo & Stitch", "lilo-stitch.jpg"), ("i23", "Movie Night (Gold)", "movie-night-gold.jpg"),
    ("i24", "Movie Night (Classic)", "movie-night-classic.jpg"),
    ("i25", "Nani ka Ghar (Photoreal)", "nanighar-photoreal.png"),
    ("i26", "Nani ka Ghar (Phone Call)", "nanighar-phonecall.jpg"),
]
_INVITES_BY_ID = {i[0]: i for i in INVITES}


def resolve_einvite_image(einvite_id: Optional[str]) -> Optional[str]:
    """Only resolves ids from the main e-invite catalogue (i1..i26) — package
    hand-off ids (uni-e2, spy-e1, etc.) aren't in the general catalogue, so
    they're left blank rather than guessed.

    Returns a path relative to SITE_BASE_URL directly (NOT under img/) since
    the einvites/ folder lives at the repo root, unlike decor/pinata/gift
    images which live under img/ (2026-08-14, per Shruti — this mismatch was
    why e-invite thumbnails 404'd in emails/order forms: the URL builders in
    leads.py/order_form_builder.py were prepending "/img/" to every
    image_path, which is correct for decor/pinata/gift but wrong here)."""
    if not einvite_id:
        return None
    inv = _INVITES_BY_ID.get(str(einvite_id))
    return f"einvites/{inv[2]}" if inv else None


# ─── Pinata ──────────────────────────────────────────────────────────────

PINATAS = {
    "square": "pin-square-1.jpg",
    "circle": "pin-circle-1.jpg",
    "number": "pin-number-1.jpg",
    # "readymade" (Readymade Pinata, added 2026-08-14 in builder.html) is
    # deliberately NOT mapped here yet — no real photo exists, so
    # resolve_pinata_image() below correctly returns None and emails/order
    # forms just skip its thumbnail. Add "readymade": "<filename>.jpg" once
    # Shruti sends the real image and it's placed in img/.
}


def resolve_pinata_image(pinata_id: Optional[str]) -> Optional[str]:
    if not pinata_id or pinata_id == "custom":
        return None
    fname = PINATAS.get(str(pinata_id))
    return f"img/{fname}" if fname else None


# ─── Activities ─────────────────────────────────────────────────────────
# (id, name, reference price, is_flat) — mirrors builder.html's ACTS array.
# `price` is the r1 band (≤12 kids) for per-child activities, or the flat
# rate for flat=True ones; it's only used to show "Name - Rs. Price" in the
# admin Activities dropdown (2026-08-18, per Shruti) — the real per-booking
# total (which can differ by group size) is still computed live in
# builder.html's actPrice(), never here. Keep in sync by hand.
ACTIVITIES = [
    ("a1", "Canvas Painting", 850, False),
    ("a2", "Tote Bag Painting", 750, False),
    ("a4", "Texture Art", 900, False),
    ("a5", "Mosaic Art", 950, False),
    ("a6", "Tie & Dye", 950, False),
    ("a7", "Mandala Art", 650, False),
    ("a8", "Cupcake Decoration", 200, False),
    ("a9", "Cap Decoration", 850, False),
    ("a10", "Soft Toy Making", 1000, False),
    ("a11", "Jacket Decoration", 1150, False),
    ("a12", "Dreamcatcher", 350, False),
    ("a13", "DIY Clock", 850, False),
    ("a15", "Tattoo Station", 2500, True),
    ("a16", "Mini Art Station", 5000, True),
    ("a18", "Pottery Station", 5000, True),
    ("a21", "Nail Art Station", 3500, True),
    ("hair-styling", "Hair Styling for Boys", 4500, True),
    ("hair-styling-girls", "Hair Styling for Girls", 3500, True),
    ("glitter", "Glitter Station", 4000, True),
    ("a22", "Sunglasses Decor", 350, False),
    ("a23", "Fridge Magnet Making", 175, False),
    ("a24", "Coaster Making", 420, False),
    ("eng90", "90 Min Sports Engagement", 24500, True),
    ("eng120", "120 Min Sports Engagement", 32000, True),
    ("zorb", "Body Zorbing", 9500, True),
    ("gym", "Gymnastics", 11800, True),
    ("a26", "Laser Tunnel", 4000, True),
    ("a27", "Dark Room", 25000, True),   # 2026-10-05, per Shruti (was 15,000)
    ("a28", "Spy Treasure Hunt", 1500, False),
    ("hit-the-cans", "Hit the Cans", 5000, True),   # 2026-10-02, BAB + Unicorn
    # 2026-10-03 — package-page activities now also in Build-a-Birthday.
    # Banded ones are listed at their base (smallest-group) price.
    ("face-painting", "Face Painting", 4500, True),
    ("a25", "Colouring Station", 4500, True),
    ("slime", "Slime Making", 400, False),   # min bill Rs 6,000
    ("jelly-swimbags", "Personalized Jelly Tote Bags", 450, False),
    ("bracelet", "Bracelet Making", 350, False),   # min bill Rs 5,000
    ("hairbrush-decor", "Hairbrush Decoration", 400, False),
    ("photoframe-decor", "Photo Frame Decoration", 400, False),
    ("mirror-decor", "Mirror Decoration", 750, False),
    ("spy-badge", "MDF Spy Badge", 9000, True),
    ("snatch-game", "Snatch Game", 13000, True),
    ("street-fighter", "Street Fighter", 13000, True),
    ("catch-the-stick", "Catch the Stick", 13000, True),
    ("air-hockey", "Air Hockey", 13000, True),
    ("buzz-wire", "Buzz Wire", 13000, True),
    ("spin-art", "Spin Art", 13000, True),
    # Price on request — confirmed by the party lead post order confirmation.
    ("inflatable-3-row", "Inflatable 3-Row Jumping (24 × 16 ft)", 0, True),
    ("inflatable-rock-climb", "Inflatable Rock Climb (20 × 20 ft)", 0, True),
    ("inflatable-lion", "Inflatable Lion 2-Row (16 × 12 ft)", 0, True),
    ("inflatable-castle", "Inflatable Castle 2-Row (14 × 12 ft)", 0, True),
    ("jumping-2in1", "Inflatable 2-in-1 Jumping (15 × 10 ft)", 0, True),
    ("balloon-house", "Inflatable Balloon House (14 × 10 ft)", 0, True),
    ("play-area", "Play Area", 0, True),
    ("trampoline", "Trampoline", 0, True),
    ("toy-train", "Toy Train (Mini Train)", 0, True),
    ("ball-pool", "Inflatable Ball Pool (10 × 10 ft)", 0, True),
    ("cotton-candy", "Cotton Candy Stall", 0, True),
    ("chocolate-fondue", "Chocolate Fondue", 0, True),
    ("popcorn", "Live Popcorn Station", 0, True),
    # 2026-09-25, per Shruti — "Experiences like Magic show, bubble show,
    # science show should come in the dropdown for activities in sales."
    # These already exist on the website (builder.html's ACTS array,
    # ids science-show/bubble-show/magic-show) but were missing from this
    # mirrored list, so the sales panel's Activities dropdown never
    # offered them. Prices match builder.html's r1/r2/r3 (flat) exactly.
    ("science-show", "Science Show", 20000, True),
    ("bubble-show", "Bubble Show", 8500, True),
    ("magic-show", "Magic Show", 8500, True),
]

# 2026-10-08, per Shruti — inflatables renamed: "Inflatable …" + size in the
# name. Old name -> new name; db_ensure.rename_activities() updates bookings
# and sales leads saved under the old names (idempotent).
ACTIVITY_RENAMES = {
    "Inflatable 3-Row Jumping": "Inflatable 3-Row Jumping (24 × 16 ft)",
    "Inflatable Rock Climb": "Inflatable Rock Climb (20 × 20 ft)",
    "Inflatable Lion (2-Row)": "Inflatable Lion 2-Row (16 × 12 ft)",
    "Inflatable Castle (2-Row)": "Inflatable Castle 2-Row (14 × 12 ft)",
    "2-in-1 Jumping": "Inflatable 2-in-1 Jumping (15 × 10 ft)",
    "Balloon House": "Inflatable Balloon House (14 × 10 ft)",
    "Ball Pool": "Inflatable Ball Pool (10 × 10 ft)",
}

# 2026-09-23, per Shruti — "spy themed should be spy in the activities...
# theme can be anything." The `leads.theme` field is no longer a reliable
# "is this a Spy booking" signal (a customer can now pick Spy-category
# activities regardless of which decor theme they chose — see builder.html's
# visibleActs()), so Spy Agent Registration eligibility (admin.py's
# get_booking_detail) is instead keyed off the ACTUAL Spy activities/package
# on the booking, checked consistently across all three places they can be
# entered — the website builder (BAB), the sales panel, and a manual admin
# edit:
#   - by id, wherever activities are stored as {id, name, ...} objects
#     (builder_snapshot.activities for BAB, lead_sales_playbook.activities
#     for the sales panel)
#   - by name, for the admin's own free-text override of the Activities
#     field (booking_field_overrides only ever stores names, never ids)
# 'spy-mission' is the package-only "N Mission Stations (K kids)" line item
# builder.html adds when a Spy Adventure homepage package (spy-basic.html)
# is carried into checkout — it's not in the catalogue above (it's not a
# standalone BAB activity, only ever created by that package hand-off), so
# it's listed here explicitly rather than by id-in-ACTIVITIES.
SPY_ACTIVITY_IDS = {"a26", "a27", "a28", "spy-mission"}

# Venue notes shown with an activity wherever it's quoted (sales panel,
# quotation PDF, booking emails) — 2026-10-05, per Shruti, for the popcorn
# station. builder.html carries the same text in that activity's `req`.
ACTIVITY_VENUE_NOTES = {
    "play-area": "Needs a minimum of 15 × 15 ft of open space.",   # 2026-10-05, per Shruti
    "popcorn": "Needs a spacious, well-ventilated venue — the popcorn machine gives off heat and some smoke, so it isn't suitable for a home setup.",
}


def activity_venue_note(aid=None, name=None) -> Optional[str]:
    if aid in ACTIVITY_VENUE_NOTES:
        return ACTIVITY_VENUE_NOTES[aid]
    for i, n, _p, _f in ACTIVITIES:
        if n == name and i in ACTIVITY_VENUE_NOTES:
            return ACTIVITY_VENUE_NOTES[i]
    return None
SPY_ACTIVITY_NAMES = {"Laser Tunnel", "Dark Room", "Spy Treasure Hunt"}
# The "N Mission Stations (K kids)" name is built dynamically (N and K vary
# per booking), so it's matched by this substring rather than an exact name.
SPY_MISSION_NAME_HINT = "mission station"

# 2026-10-05, per Shruti — "for spy activity, we have host included in the
# pricing. if the user selects spy in sales module or bab, in both places, a
# premium category [host] should show autoselected  (tier: see below) with no additional cost"
# (the spy THEME doesn't count — a spy-themed party may only do tattoos).
# The Spy Treasure Hunt (and the Spy package's mission stations) is the spy
# activity that's run by a host; Laser Tunnel / Dark Room are set pieces
# added on top, so on their own they don't bring a host. Used by the sales
# panel breakup + quotation PDF (sales_leads.py, twin in sales-leads.html),
# the booking's Total MRP (booking_pricing.compute_billing), the admin
# booking page and the summary email.
SPY_HOST_INCLUDED_IDS = {"a28", "spy-mission"}
SPY_HOST_INCLUDED_NAMES = {"Spy Treasure Hunt"}
# 2026-10-05, per Shruti — "host tiers should be same in both [BAB and
# sales/bookings]. we have 2 tiers - so choose the higher one": Signature,
# same as the Spy package hand-off in builder.html (S.host={tier:'Signature',p:0}).
SPY_INCLUDED_HOST_TIER = "Signature"


def spy_host_included_by(activities) -> Optional[str]:
    """Name of the spy activity that brings a free Signature host, else None.
    activities: dicts ({id, name} / {id, n}) or plain names, or a
    comma-separated string of names (the admin Activities field)."""
    if not activities:
        return None
    if isinstance(activities, str):
        activities = [x for x in activities.split(",")]
    for a in activities:
        if isinstance(a, dict):
            aid, name = a.get("id"), (a.get("name") or a.get("n") or "")
        else:
            aid, name = None, str(a or "")
        name = re.sub(r"\s*\(.*\)\s*$", "", name.strip())   # "Spy Treasure Hunt (70)" -> name
        if aid == "spy-mission" or SPY_MISSION_NAME_HINT in name.lower():
            return "Spy Mission"
        if aid in SPY_HOST_INCLUDED_IDS or name in SPY_HOST_INCLUDED_NAMES:
            return "Spy Treasure Hunt"
    return None

# ─── Return Gifts ────────────────────────────────────────────────────────
# (id, name, image path, catalogue unit price — the unit price actually
# billed on the booking is read from the booking snapshot itself; this
# catalogue is only used as a fallback and for the reference image.)

GIFTS = [
    ("g1", "3D Printed Personalized FIFA World Cup", "return-gifts/fifa-world-cup-3d.jpg", 850),
    ("g2", "900ml Tumbler", "return-gifts/tumbler-900ml.jpg", 750),
    ("g3", "Baby Frost Pouch", "return-gifts/baby-frost-pouch.jpg", 245),
    ("g4", "Codenames (Board Game)", "return-gifts/board-game-codenames.jpg", 475),
    ("g5", "Neon Chest Bag", "return-gifts/chest-bag-neon.jpg", 275),
    ("g6", "Foam Duffle Bag", "return-gifts/foam-duffle-bag.jpg", 300),
    ("g7", "Jelly Tote Bag", "return-gifts/jelly-tote-bag.jpg", 500),
    ("g8", "Jewellery Organizer with Initial", "return-gifts/jewellery-organizer-initial.jpg", 500),
    ("g9", "Kids Travel Trolley", "return-gifts/kids-travel-trolley.jpg", 1200),
    ("g10", "LCD Compass Box with Calculator", "return-gifts/lcd-compass-calculator.jpg", 210),
    ("g11", "Mafia (Board Game)", "return-gifts/board-game-mafia.jpg", 300),
    ("g12", "Magic Water Painting Book", "return-gifts/magic-water-painting-book.jpg", 375),
    ("g13", "Neon Bag with Double Packet", "return-gifts/neon-bag-double-packet.jpg", 400),
    ("g14", "Neon Duffle Bag", "return-gifts/neon-duffle-bag.jpg", 350),
    ("g15", "Personalized Drawstring Pouch", "return-gifts/personalized-drawstring-pouch.jpg", 500),
    ("g16", "Personalized Drawstring Bag & Pouch Combo", "return-gifts/personalized-drawstring-combo.jpg", 750),
    ("g17", "Personalized Duffle Bag", "return-gifts/personalized-duffle-bag.jpg", 650),
    ("g18", "Personalized Football", "return-gifts/personalized-football-1.jpg", 600),
    ("g19", "Personalized Pouch", "return-gifts/personalized-pouch.jpg", 325),
    ("g20", "Space Rocket Piggy Bank with Password", "return-gifts/space-rocket-piggy-bank.jpg", 410),
    ("g21", "Theme Based Penstand", "return-gifts/theme-penstand.jpg", 450),
    ("g22", "Toy Storage Box", "return-gifts/toy-storage-box.jpg", 375),
    ("g23", "Train Night Lamp", "return-gifts/train-night-lamp.jpg", 300),
    ("g24", "5 Pcs Steel Straw Set", "return-gifts/steel-straw-set.jpg", 190),
    ("g25", "Personalized Cap", "return-gifts/personalized-cap.png", 500),
    ("g26", "Live T-shirt Printing", "return-gifts/live-tshirt-printing.png", 550),
    ("g27", "Squishy Dumpling", "return-gifts/squishy-dumpling-plain-1.jpg", 199),
    ("g28", "Bath Bomb", "return-gifts/bath-bombs-small.jpg", 85),
    # Harry Potter & K-pop range, added 2026-10-02 per Shruti.
    ("g29", "Insulated Steel Lunch Box", "return-gifts/hp-kpop-steel-lunch-box.jpg", 546),
    ("g30", "Steel Mug", "return-gifts/hp-kpop-steel-mug.jpg", 440),
    ("g31", "Insulated Steel Flask (approx. 260 ml)", "return-gifts/hp-kpop-steel-flask-260ml.jpg", 580),
    ("g32", "Harry Potter Bluetooth Headphones", "return-gifts/hp-bluetooth-headphones.jpg", 700),
    ("g33", "K-pop Bluetooth Headphones", "return-gifts/kpop-bluetooth-headphones.jpg", 700),
    ("g34", "LED Alarm Clock", "return-gifts/hp-kpop-led-alarm-clock.jpg", 420),
    ("g35", "Harry Potter Karaoke Speaker Set", "return-gifts/hp-karaoke-speaker-set.jpg", 600),
    ("g36", "K-pop Chest Bag (Leather Finish)", "return-gifts/kpop-chest-bag.jpg", 380),
    ("g37", "Harry Potter Chest Bag (Leather Finish)", "return-gifts/hp-chest-bag.jpg", 380),
    ("g38", "Harry Potter Backpack (Leather Finish)", "return-gifts/hp-backpack.jpg", 570),
    ("g39", "K-pop Backpack (Leather Finish)", "return-gifts/kpop-backpack.jpg", 570),
    ("g40", "Harry Potter A4 Folder (4 designs)", "return-gifts/hp-a4-folder.jpg", 270),
    ("g41", "K-pop A4 Folder (4 designs)", "return-gifts/kpop-a4-folder.jpg", 270),
    ("g42", "Harry Potter Pencil Pouch", "return-gifts/hp-pencil-pouch.jpg", 200),
    # Budget range (under Rs 250), added 2026-10-02 per Shruti.
    ("g43", "UNO Cards", "return-gifts/uno-cards.jpg", 90),
    ("g44", "Wooden Car Pen Stand", "return-gifts/wooden-car-pen-stand.jpg", 110),
    ("g45", "Minion Sketch Pen Set", "return-gifts/minion-sketch-pen-set.jpg", 100),
    ("g46", "Silicone Coin Pouch", "return-gifts/silicone-coin-pouch.jpg", 100),
    ("g47", "Fruit Pencil Pouch", "return-gifts/fruit-pencil-pouch.jpg", 100),
    ("g48", "Labubu Bag Charm / Keychain", "return-gifts/labubu-bag-charm.jpg", 80),
    ("g49", "Cube Scale (20 cm)", "return-gifts/cube-scale-20cm.jpg", 100),
    ("g50", "Kaleidoscope", "return-gifts/kaleidoscope.jpg", 110),
    ("g51", "Kids Folder", "return-gifts/kids-folder.jpg", 160),
    ("g52", "Lego Band", "return-gifts/lego-band.jpg", 140),
    ("g53", "Lego Pencil Set", "return-gifts/lego-pencil-set.jpg", 130),
    ("g54", "Kids Lunch Bag (assorted prints)", "return-gifts/kids-lunch-bag.jpg", 120),
    ("g55", "Magnetic Planner with Whiteboard Marker", "return-gifts/magnetic-planner.jpg", 130),
    ("g56", "Binoculars", "return-gifts/binoculars.jpg", 120),
    ("g57", "Pinball Game", "return-gifts/pinball-game.jpg", 210),
    ("g58", "Swimming Goggles (assorted designs)", "return-gifts/swimming-goggles.jpg", 200),
    ("g59", "Rechargeable Mini Fan", "return-gifts/rechargeable-mini-fan.jpg", 200),
    # Rs 200-1200 range, added 2026-10-02 per Shruti.
    ("g60", "Habit Tracker", "return-gifts/habit-tracker.jpg", 320),
    ("g61", "Digital Alarm Clock", "return-gifts/digital-alarm-clock.jpg", 300),
    ("g62", "DIY Decorate-your-own Mug", "return-gifts/diy-decorate-your-own-mug.jpg", 320),
    ("g63", "Mini Pocket Wireless Speaker", "return-gifts/mini-pocket-wireless-speaker.jpg", 270),
    ("g64", "Gobble Game", "return-gifts/gobble-game.jpg", 280),
    ("g65", "Solo Practice Ball Game", "return-gifts/solo-practice-ball-game.jpg", 300),
    ("g66", "Metal Book Reading Stand", "return-gifts/metal-book-reading-stand.jpg", 380),
    ("g67", "12-compartment Folder", "return-gifts/12-compartment-folder.jpg", 300),
    ("g68", "Dobble Game", "return-gifts/dobble-game.jpg", 300),
    ("g69", "K-pop Multipurpose Pouch", "return-gifts/k-pop-pouch.jpg", 220),
    ("g70", "Harry Potter Multipurpose Pouch", "return-gifts/harry-potter-pouch.jpg", 220),
    ("g71", "Harry Potter Diary", "return-gifts/harry-potter-diary.jpg", 500),
    ("g72", "LED Neon Drawing Board", "return-gifts/led-neon-drawing-board.jpg", 400),
    ("g73", "Soup Cup Lunch Box", "return-gifts/soup-cup-lunch-box.jpg", 530),
    ("g74", "Password Compass Box", "return-gifts/password-compass-box.jpg", 600),
    ("g75", "Science 61 Experiment Kit", "return-gifts/science-61-experiment-kit.jpg", 600),
    ("g76", "Lunch Bag (assorted prints)", "return-gifts/lunch-bag-many-prints.jpg", 630),
    ("g77", "Pickleball Set", "return-gifts/pickleball-set.jpg", 770),
    ("g78", "Retro Handheld Game (400 games)", "return-gifts/retro-handheld-game-400-games.jpg", 525),
    ("g79", "Glow-in-the-dark Blanket (assorted designs)", "return-gifts/glow-in-the-dark-blanket-many-designs.jpg", 672),
    ("g80", "Calligraphy Pen Set with Wax Seal", "return-gifts/calligraphy-pen-set-with-wax-seal.jpg", 840),
    ("g81", "Lego Photo Frame", "return-gifts/lego-photo-frame.jpg", 532),
    ("g82", "3D Pen", "return-gifts/3d-pen.jpg", 630),
    ("g83", "Insulated Food Jar Lunch Box", "return-gifts/insulated-food-jar-lunch-box.jpg", 672),
    ("g84", "Steel Sipper Tumbler", "return-gifts/fancy-steel-sipper-tumbler.jpg", 700),
    ("g85", "Pastel Calculator", "return-gifts/pastel-calculator.jpg", 700),
    ("g86", "Insulated Ice Flask (500 ml)", "return-gifts/insulated-ice-flask-500ml.jpg", 840),
    ("g87", "Charm Tote Bag (assorted colours)", "return-gifts/charm-tote-bag.jpg", 700),
    ("g88", "Cluedo Board Game", "return-gifts/cluedo-board-game.jpg", 770),
    ("g89", "Controller Video Game (520 games)", "return-gifts/controller-video-game-520-games.jpg", 770),
    ("g90", "Kids Bluetooth Headphones (assorted themes)", "return-gifts/kids-bluetooth-headphones-many-themes.jpg", 672),
    ("g91", "Taboo Game", "return-gifts/taboo-game.jpg", 630),
    ("g92", "Astronaut Galaxy Projector", "return-gifts/astronaut-galaxy-projector.jpg", 770),
    ("g93", "Kids Lunch Box (assorted prints)", "return-gifts/kids-lunch-box-many-prints.jpg", 595),
    ("g94", "Kids Bento Box", "return-gifts/kids-bento-box.jpg", 511),
]
_GIFTS_BY_ID = {g[0]: g for g in GIFTS}

# Gifts no longer offered (2026-10-02, per Shruti). They stay in GIFTS so
# existing bookings keep their price/image; pickers use ACTIVE_GIFTS.
RETIRED_GIFT_IDS = {"g1", "g9", "g10", "g12", "g13", "g15", "g16", "g17", "g19", "g21", "g23"}
ACTIVE_GIFTS = [g for g in GIFTS if g[0] not in RETIRED_GIFT_IDS]


def resolve_gift(gift_id: Optional[str]) -> Optional[dict]:
    """Package hand-off gifts (prop-*, uni-craftset, etc.) aren't in the
    general catalogue and resolve to None — no image, price stays whatever
    was captured on the booking itself."""
    if not gift_id:
        return None
    g = _GIFTS_BY_ID.get(str(gift_id))
    if not g:
        return None
    return {"image_path": f"img/{g[2]}", "catalogue_unit": g[3]}


PACKAGING_LABELS = {
    "paper-bag": "Paper Gift Bag",
    "wrap": "Gift Wrap",
    "both": "Gift Wrap + Paper Bag",
}


# ─── Reference photos for the sales quotation PDF (2026-10-03) ───────────
# Used only by quotation_builder.py (via routers/sales_leads.py) to put a
# picture next to each quoted item. Paths are relative to SITE_BASE_URL,
# same convention as the resolvers above. Activity photos mirror the
# img/... path builder.html's ACTS array shows for each id ('img/' + img +
# '.jpg'); ids with no real photo on the site (Mallakhamb) are
# left out, so the PDF shows no picture rather than a wrong one. Keep in
# sync by hand with builder.html, like everything else in this file.
ACTIVITY_IMAGES = {
    "a1": "img/act-canvas-painting.jpg",
    "a2": "img/activity/act-tote-bag-painting.jpg",
    "a4": "img/activity/act-texture-art.jpg",
    "a5": "img/activity/act-mosaic-art.jpg",
    "a6": "img/activity/act-tie-dye.jpg",
    "a7": "img/activity/act-mandala-art.jpg",
    "a8": "img/activity/act-cupcake-decor.jpg",
    "a9": "img/activity/act-cap-decoration.jpg",
    "a10": "img/activity/act-soft-toy-making-v2.jpg",
    "a11": "img/activity/act-jacket-decoration.jpg",
    "a12": "img/activity/act-dreamcatcher.jpg",
    "a13": "img/activity/act-diy-clock.jpg",
    "tshirt-printing": "img/activity/act-tshirt-printing.jpg",
    "a15": "img/activity/act-tattoo-station.jpg",
    "a16": "img/activity/act-mini-art-station.jpg",
    "a18": "img/activity/act-pottery.jpg",
    "a21": "img/activity/act-nail-art.jpg",
    "hair-styling": "img/activity/act-boys-hair-styling.jpg",
    "hair-styling-girls": "img/activity/act-hair-styling-girls.jpg",
    "glitter": "img/activity/act-glitter.jpg",
    "science-show": "img/activity/act-science-show-card.jpg",
    "bubble-show": "img/activity/act-bubble-show-card.jpg",
    "magic-show": "img/activity/act-magic-show-card.jpg",
    "chitrakathi-show": "img/activity/act-chitrakathi-puppets-card.jpg",
    "bhajan-jamming": "img/activity/act-bhajan-jamming-card.jpg",
    "a22": "img/activity/act-sunglasses-decor.jpg",
    "a23": "img/activity/act-fridge-magnet.jpg",
    "a24": "img/activity/act-coaster-making.jpg",
    "eng90": "img/activity/act-90-min-engagement.jpg",
    "eng120": "img/activity/act-120-min-engagement.jpg",
    "zorb": "img/activity/act-body-zorbing.jpg",
    "gym": "img/activity/act-gymnastics.jpg",
    "a26": "img/packages/spy/spy-laser-tunnel.jpg",
    "a27": "img/packages/spy/act-dark-room.jpg",
    "a28": "img/packages/spy/maze.jpg",
    "hit-the-cans": "img/activity/act-hit-the-cans-v2.jpg",
    "face-painting": "img/activity/act-face-painting-v2.jpg",
    "a25": "img/activity/act-colouring-station.jpg",
    "slime": "img/activity/act-slime.jpg",
    "jelly-swimbags": "img/activity/act-jelly-tote-bag.jpg",
    "hairbrush-decor": "img/act-hairbrush-decor.jpg",
    "photoframe-decor": "img/activity/act-photo-frame.jpg",
    "mirror-decor": "img/activity/act-mirror-decoration.jpg",
    "bracelet": "img/activity/act-bracelet-making.jpg",
    "spy-badge": "img/packages/spy/spy-badge-mdf-sq.jpg",
    "snatch-game": "img/activity/act-snatch-game.jpg",
    "street-fighter": "img/activity/act-street-fighter.jpg",
    "catch-the-stick": "img/activity/act-catch-the-stick.jpg",
    "air-hockey": "img/activity/act-air-hockey.jpg",
    "buzz-wire": "img/activity/act-buzz-wire.jpg",
    "spin-art": "img/activity/act-spin-art.jpg",
    "inflatable-3-row": "img/activity/act-inflatable-3-row.jpg",
    "inflatable-rock-climb": "img/activity/act-inflatable-rock-climb.jpg",
    "inflatable-lion": "img/activity/act-inflatable-lion.jpg",
    "inflatable-castle": "img/activity/act-inflatable-castle.jpg",
    "jumping-2in1": "img/activity/act-2in1-jumping.jpg",
    "balloon-house": "img/activity/act-balloon-house.jpg",
    "play-area": "img/activity/act-play-area.jpg",
    "ball-pool": "img/activity/act-ball-pool.jpg",   # 2026-10-07, from "Ball Pool 10x10.png"
    "trampoline": "img/activity/act-trampoline.jpg",
    "toy-train": "img/activity/act-toy-train.jpg",
    "cotton-candy": "img/activity/act-cotton-candy.jpg",
    "chocolate-fondue": "img/activity/act-chocolate-fondue.jpg",
    "popcorn": "img/activity/act-popcorn.jpg",
}

# Tier photos for Host / Music / Photographer — the same tier-card images
# builder.html shows on those steps. Keys are the names the sales module
# stores (catalogue labels), plus the bare tier word.
HOST_TIER_IMAGES = {"Premium": "img/host-premium.jpg", "Signature": "img/host-signature.jpg"}
MUSIC_IMAGES = {
    "Music Essential": "img/dj-classic.jpg", "Classic": "img/dj-classic.jpg",
    "Music Plus": "img/dj-premium.jpg", "Premium": "img/dj-premium.jpg",
}
PHOTO_IMAGES = {
    "Classic Package": "img/photo-classic.jpg", "Classic": "img/photo-classic.jpg",
    "Premium Package": "img/photo-premium.jpg", "Premium": "img/photo-premium.jpg",
    "Signature Package": "img/photo-signature.jpg", "Signature": "img/photo-signature.jpg",
}
PINATA_NAME_TO_ID = {
    "Square Pinata": "square", "Circle Pinata": "circle", "Number Pinata": "number",
    "Readymade Pinata": "readymade",
}
_THEMES_BY_NAME = {t["n"]: t for t in THEMES}
_GIFTS_BY_NAME = {g[1]: g for g in GIFTS}


def resolve_activity_image(activity_id: Optional[str], name: Optional[str] = None) -> Optional[str]:
    if activity_id and str(activity_id) in ACTIVITY_IMAGES:
        return ACTIVITY_IMAGES[str(activity_id)]
    if name:
        for aid, n, _p, _f in ACTIVITIES:
            if n == name:
                return ACTIVITY_IMAGES.get(aid)
    return None


# 2026-10-05, per Shruti — shown with a standard-decor (reference) photo on
# the quotation PDF and booking emails, when it isn't the chosen design's own.
DECOR_REFERENCE_NOTE = ("Reference picture. Details of the decor like balloon colours and flex/sunboard "
                        "designs (as applicable) will be discussed with you by your party manager before finalising.")


def decor_image_is_reference(theme_name: Optional[str], tier: Optional[str]) -> bool:
    """True when resolve_decor_image_by_name() falls back to a standard-decor
    photo (no matching photo of the chosen design)."""
    theme = _THEMES_BY_NAME.get(theme_name or "")
    if theme:
        photos = theme.get("tierPhotos") or {}
        if tier in photos or len(photos) == 1:
            return False
        if tier not in STD_META and photos:
            return False
    return True


def decor_spec_by_name(theme_name: Optional[str], tier: Optional[str]) -> list:
    """(label, value, not_included) rows for a named design + tier — the
    design's own list when it has one (Sustainable LED Decor), else the
    tier's shared list. Used by the sales quotation."""
    theme = _THEMES_BY_NAME.get(theme_name or "")
    return _spec_for(theme_name or "", tier, colors=_extract_colors(theme["b"]) if theme else "As per theme", theme=theme)


def resolve_decor_image_by_name(theme_name: Optional[str], tier: Optional[str]) -> Optional[str]:
    """Sales module decor: a tier name ('Classic'...) plus, optionally, a
    named Build-a-Birthday design (THEMES 'n'). Theme photo for that tier
    first, then the theme's only photo, then the standard-decor photo for
    the tier; None when nothing fits (e.g. tier 'Others' with no theme)."""
    theme = _THEMES_BY_NAME.get(theme_name or "")
    if theme:
        photos = theme.get("tierPhotos") or {}
        if tier in photos:
            return f"img/{photos[tier]}"
        if len(photos) == 1:
            return f"img/{next(iter(photos.values()))}"
    if tier in STD_META:
        return f"img/{STD_META[tier]}"
    if theme and theme.get("tierPhotos"):
        return f"img/{next(iter(theme['tierPhotos'].values()))}"
    return None


def resolve_gift_image_by_name(name: Optional[str]) -> Optional[str]:
    g = _GIFTS_BY_NAME.get(name or "")
    return f"img/{g[2]}" if g else None


# ─── Greeting name ──────────────────────────────────────────────────────
_TITLES = {"dr", "mr", "mrs", "ms", "miss", "mx", "prof", "shri", "smt"}


def greeting_name(full: Optional[str]) -> str:
    """First name for "Hi …" — keeps a title with it ("Dr. Vyoma Shah" ->
    "Dr. Vyoma", not "Dr."), 2026-10-05, per Shruti. "" when blank."""
    parts = (full or "").split()
    if not parts:
        return ""
    if parts[0].rstrip(".").lower() in _TITLES and len(parts) > 1:
        return f"{parts[0]} {parts[1]}"
    return parts[0]


# ─── Decor options (2026-10-08, per Shruti) ────────────────────────────────
# "the salesteam needs to send multiple decor options in the sales quote ...
# select decor options from the decor list and those photos with pricing and
# details comes up on the pdf ... add a link which directs to a page where
# they can see bigger photos with inclusions exclusions." Every design live
# on Build-a-Birthday (theme x tier with a photo) plus the 4 standard decors,
# ids as on the website ("uni-signature", "std-premium").
DECOR_OPTIONS_PAGE = f"{SITE_BASE_URL}/decor-options.html"
_STD_NAMES = {"Classic": "Classic Balloon Arch", "Premium": "Premium Decor",
              "Luxury": "Luxury Decor", "Signature": "Signature Decor"}
_TIER_ORDER = ["Classic", "Premium", "Luxury", "Signature"]


def _excl(label, value):
    v = (value or "").strip()
    if v.upper() in ("NA", "N/A", "") or v.lower() == "not included":
        return label
    if v.lower().startswith("not included"):
        return label + v[len("not included"):]       # "Name on Bunting — add for ₹200"
    return f"{label}: {v}"


def _option_dict(oid, name, theme_name, tier, price, photos, spec):
    return {
        "id": oid, "name": name, "theme": theme_name, "tier": tier, "price": price,
        "image": photos[0] if photos else None, "photos": photos,
        "included": [f"{l}: {v}" for l, v, na in spec if not na and not l.lower().startswith("needed from you")],
        "needed": [v for l, v, na in spec if l.lower().startswith("needed from you")],
        "excluded": [_excl(l, v) for l, v, na in spec if na],
    }


def decor_options() -> list:
    out = []
    for t in sorted(THEMES, key=lambda x: x["n"].lower()):
        retired = set(t.get("retiredTiers") or [])
        for tier in _TIER_ORDER:
            photo = (t.get("tierPhotos") or {}).get(tier)
            if not photo or tier in retired or tier not in DECOR_TIER_META:
                continue
            ov = ((t.get("tierOverrides") or {}).get(tier) or {})
            photos = [f"img/{photo}"] + [f"img/{x}" for x in (t.get("tierExtraPhotos") or {}).get(tier, [])]
            out.append(_option_dict(f"{t['id']}-{tier.lower()}", f"{t['n']} — {tier}", t["n"], tier,
                                    ov.get("price", DECOR_TIER_META[tier]["price"]), photos,
                                    _spec_for(t["n"], tier, colors=_extract_colors(t["b"]), theme=t)))
    for tier in _TIER_ORDER:
        if tier in STD_META:
            out.append(_option_dict(f"std-{tier.lower()}", f"Standard — {_STD_NAMES[tier]}", None, tier,
                                    DECOR_TIER_META[tier]["price"], [f"img/{STD_META[tier]}"],
                                    _spec_for("Standard Decor", tier, colors="As per theme")))
    return out


def decor_option(oid: Optional[str]) -> Optional[dict]:
    return next((o for o in decor_options() if o["id"] == oid), None) if oid else None
