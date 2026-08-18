# Wondershop Experiences — Pricing Context Document
_Last updated: August 2026 · Source: WSR Birthday Brochure v5.pdf + founder inputs_

---

## Order-Value Discount Slabs
_Replaces the old flat/service-count discount logic (2026-08-12, per Shruti; slab boundaries widened 2026-08-14, per Shruti — this table updated 2026-08-18 to match, was previously stale). Qualifying value is the cart total before any discount. Only ONE discount ever applies on a booking — whichever is worth more in rupees, the auto-slab discount or a coupon/referral/scratch-card code — never both._

| Order Value | Discount | Capped At |
|-------------|----------|-----------|
| ₹25,000 – ₹34,999 | 5% off | up to ₹1,500 |
| ₹35,000 – ₹44,999 | 7% off | up to ₹2,500 |
| ₹45,000+ | 9% off | up to ₹4,500 |
| Below ₹25,000 | No discount | — |

**Package-origin checkouts (Unicorn Magic, Turf Takeover):** unicorn-basic.html and turf-basic.html apply this exact same slab table client-side to quote their own discounted price, and builder.html's checkout now applies it too (fixed 2026-08-18 — checkout previously showed the undiscounted total while the package page quoted a discounted one). Unicorn Magic's Return Gifts already carry their own per-item pricing and are excluded from the discount (matches unicorn-basic.html); Turf Takeover's discount applies to the whole cart including Return Gifts (matches turf-basic.html). Both packages retired their old flat coupon codes (PKGUNICORN 10%/15%, PKGTURF 15%) on 2026-08-12 in favor of this automatic slab discount.

**Spy Mystery checkouts:** spy-basic.html quotes one fixed price with no discount offered at any order value, so builder.html's checkout correctly charges full price here — this slab table does not apply to Spy.

---

## Music
_Renamed from "DJ" site-wide (2026-08-16, per Shruti) — user-facing labels only; internal code identifiers (S.dj, cat:'DJ', img/dj-*.jpg, etc.) are unchanged, see builder.html._

| Tier | Standalone | Bundled | Inclusions |
|------|-----------|---------|------------|
| Music Lite | ₹7,000 | ₹6,500 | 1 speaker, 1 cordless mic, music mixer, 1 operator. Home/small spaces. |
| Music Standard | ₹11,000 | ₹10,000 | 2 speakers, 2 cordless mics, music mixer, 1 pro music player |
| Music Pro | ₹15,000 | ₹12,000 | 2 speakers, 2 cordless mics, music mixer, 1 expert music player + music lights |

---

## Host

| Tier | Standalone | Bundled | Duration / Notes |
|------|-----------|---------|-----------------|
| Starter | ₹10,000 | ₹8,000 | 60 mins engagement |
| Premium | ₹12,000 | ₹10,000 | 85 mins engagement |
| Signature | ₹15,000 | ₹13,000 | 90 mins engagement, premium props, signature-category host |

---

## Decor (from brochure)

| Package | Price | Inclusions |
|---------|-------|------------|
| Home Package | ₹5,000 | 1 balloon arch (2 colours), Happy Birthday bunting, 1 foil balloon |
| Silver (Venue) | ₹7,500 | 1 balloon arch, HB banner, personalised name bunting, balloon bunches |
| Gold (Venue) | ₹21,000 | Welcome arch, welcome board, main cake decor area + cake stand, halogen lights, LED HB light, personalised name bunting, cake table |
| Photo Booth | ₹3,500 | — |

---

## Activities (per child, tiered by headcount)

### Page 1
| Activity | <12 kids | 13–25 kids | >25 kids |
|----------|----------|------------|---------|
| Canvas Painting | ₹850 | ₹800 | ₹750 |
| Tote Bag Painting | ₹750 | ₹700 | ₹650 |
| Cap Decoration | ₹850 | ₹800 | ₹750 |
| Soft Toy Making | ₹1,000 | ₹950 | ₹900 |
| Jacket Decoration | ₹1,150 | ₹1,100 | ₹1,050 |
| Pot Painting | ₹850 | ₹800 | ₹750 |
| Tattoo (up to 3 hrs) | ₹2,500 flat | ₹2,500 flat | ₹2,500 flat |

### Page 2
| Activity | <12 kids | 13–25 kids | >25 kids |
|----------|----------|------------|---------|
| Texture Art | ₹900 | ₹850 | ₹800 |
| Mosaic Art | ₹950 | ₹900 | ₹850 |
| Mini Art Station (fridge magnets, colouring sheets) | ₹3,500 flat | ₹4,000 flat | ₹5,000 flat |
| Mascot (2 hrs) | ₹4,000 flat | ₹4,000 flat | ₹4,000 flat |
| Pottery (3 hrs) | ₹5,000 flat | ₹5,000 flat | ₹5,000 flat |
| Storytelling (up to 2 hrs) | ₹11,000 flat | ₹12,500 flat | ₹15,000 flat |
| Makeover Station (nail, braiding, tattoo, 3 hrs) | ₹6,000 flat | ₹6,500 flat | ₹7,000 flat |

### Page 3
| Activity | <12 kids | 13–25 kids | >25 kids |
|----------|----------|------------|---------|
| Dreamcatcher | ₹850 | ₹800 | ₹750 |
| DIY Clock | ₹850 | ₹800 | ₹750 |
| Tie & Dye | ₹950 | ₹900 | ₹850 |
| Journaling | ₹850 | ₹850 | ₹850 |
| Cupcake Decoration (1 per child) | ₹90 | ₹85 | ₹80 |
| Nail Art | ₹3,500 flat | ₹3,500 flat | ₹3,500 flat |
| Mandala Art Station | ₹650 | ₹600 | ₹550 |

---

## Pinata
- ₹2,000 for all options
- **Free** above ₹40,000 order value (updated 2026-08-12, was ₹50,000), checked against the cart total *excluding the pinata's own price* — same rule as E-Invite below (fixed 2026-08-18; the pinata's own price was briefly counting toward its own free threshold, which could make a pricier pinata free while a cheaper one wasn't)
- Not offered on package-origin checkouts (Spy/Unicorn/Turf) — those always charge full pinata price, no threshold
- All pinata options are handmade (readymade pinatas may be added as an option in future)

## E-Invite
- **Free** above ₹20,000 order value (updated 2026-08-12, was ₹30,000), checked against the cart total excluding the e-invite's own price
- ₹500 below ₹20,000 order value
- Not offered on package-origin checkouts (Spy/Unicorn/Turf) — those always charge full e-invite price, no threshold

## Return Gift Personalisation
- **Not free at any order value** (2026-08-12, per Shruti — no free-above-threshold offer for this)

---

## Other Services (from brochure)
| Service | Price |
|---------|-------|
| Cake | Starting ₹1,850/kg |
| Photographer | Starting ₹7,500 |

---

## Terms & Conditions
- 50% advance to reserve date
- Price inclusive of materials + GST
- Non-negotiable, standardised pricing
- Additional transport charge based on location
- Balance payable by end of event on same day
- Inform of any additions/deletions in advance
- Guest count cannot be decreased once at venue
- Furniture/venue provided by client (can rent at extra cost)
- No cancellations once at venue
