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

SITE_BASE_URL = "https://wondershop-exp.github.io/wondershop-website"

# ─── Decor ──────────────────────────────────────────────────────────────

DECOR_TIER_META = {
    "Classic": {
        "price": 6500,
        "spec": [
            ("Panels", "NA", True),
            ("Balloons", "Up to 200", False),
            ("Balloon Colours", "Up to 2", False),
            ("Happy Birthday, Name & Age", "Paper bunting (HBD & name), foil balloon (age)", False),
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
                    "Luxury": "Decor/decor-kpop-2panel.jpg", "Signature": "Decor/decor-kpop-3panel.jpg"}},
    {"id": "hp", "n": "Harry Potter", "b": "180 (Black, Gold, Red)",
     "tierPhotos": {"Premium": "Decor/decor-hp-1panel.jpg", "Signature": "Decor/decor-hp-3panel.jpg"}},
    {"id": "art", "n": "Art & Paint Party", "b": "150 (Colorful mix)",
     "tierPhotos": {"Premium": "Decor/decor-art-1panel.jpg", "Luxury": "Decor/decor-art-2panel.jpg"}},
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
     "tierPhotos": {"Signature": "Decor/decor-katseye-3panel.jpg"}},
    {"id": "stitch", "n": "Lilo & Stitch", "b": "150 (Blue, Turquoise, White)",
     "tierPhotos": {"Premium": "Decor/decor-stitch-1panel.jpg"}},
    {"id": "malgudi", "n": "Malgudi Days", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-malgudi-3panel.jpg"}},
    {"id": "mithai", "n": "Mithai Theme", "b": "180 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-mithai-3panel.jpg"}},
    {"id": "nanighar", "n": "Nani ka Ghar", "b": "150 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-nanighar-3panel.jpg"}},
    {"id": "treasure", "n": "The Great Ancient Indian Treasure", "b": "200 (mixed colours)",
     "tierPhotos": {"Signature": "Decor/decor-treasure-3panel.jpg"}},
]
_THEMES_BY_ID = {t["id"]: t for t in THEMES}

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
                "image_path": STD_META[tier],
                "spec": _spec_for("Standard Decor", tier, colors="As per theme"),
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
        "image_path": photo,
        "spec": _spec_for(theme["n"], tier, colors=_extract_colors(theme["b"])),
    }


def _spec_for(label: str, tier: str, colors: str) -> list:
    meta = DECOR_TIER_META.get(tier)
    if not meta:
        return []
    out = []
    for l, v, na in meta["spec"]:
        if v == "__THEME__":
            v = colors
        out.append((l, v, na))
    return out


# ─── Photographer ───────────────────────────────────────────────────────

PHOTO_TIER_FEATURES = {
    "Classic": ["1 photographer", "Output: Edited photos over drive link"],
    "Premium": ["1 photographer", "Photo + video content shoot",
                "Output: Edited photos, candid photos"],
    "Signature": ["1 photographer + 1 videographer", "Photo + video content shoot",
                  "Output: Edited photos, full event video (captured moments), candid photos"],
}


# ─── E-Invite ────────────────────────────────────────────────────────────

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
    they're left blank rather than guessed."""
    if not einvite_id:
        return None
    inv = _INVITES_BY_ID.get(str(einvite_id))
    return f"einvites/{inv[2]}" if inv else None


# ─── Pinata ──────────────────────────────────────────────────────────────

PINATAS = {
    "square": "pin-square-1.jpg",
    "circle": "pin-circle-1.jpg",
    "number": "pin-number-1.jpg",
}


def resolve_pinata_image(pinata_id: Optional[str]) -> Optional[str]:
    if not pinata_id or pinata_id == "custom":
        return None
    fname = PINATAS.get(str(pinata_id))
    return fname if fname else None


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
    ("g18", "Personalized Football", "return-gifts/personalized-football.jpg", 600),
    ("g19", "Personalized Pouch", "return-gifts/personalized-pouch.jpg", 325),
    ("g20", "Space Rocket Piggy Bank with Password", "return-gifts/space-rocket-piggy-bank.jpg", 410),
    ("g21", "Theme Based Penstand", "return-gifts/theme-penstand.jpg", 450),
    ("g22", "Toy Storage Box", "return-gifts/toy-storage-box.jpg", 375),
    ("g23", "Train Night Lamp", "return-gifts/train-night-lamp.jpg", 300),
    ("g24", "5 Pcs Steel Straw Set", "return-gifts/steel-straw-set.jpg", 190),
    ("g25", "Personalized Cap", "return-gifts/personalized-cap.png", 500),
    ("g26", "Live T-shirt Printing", "return-gifts/live-tshirt-printing.png", 550),
]
_GIFTS_BY_ID = {g[0]: g for g in GIFTS}


def resolve_gift(gift_id: Optional[str]) -> Optional[dict]:
    """Package hand-off gifts (prop-*, uni-craftset, etc.) aren't in the
    general catalogue and resolve to None — no image, price stays whatever
    was captured on the booking itself."""
    if not gift_id:
        return None
    g = _GIFTS_BY_ID.get(str(gift_id))
    if not g:
        return None
    return {"image_path": g[2], "catalogue_unit": g[3]}


PACKAGING_LABELS = {
    "paper-bag": "Paper Gift Bag",
    "wrap": "Gift Wrap",
    "both": "Gift Wrap + Paper Bag",
}
