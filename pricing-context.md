# Wondershop Experiences — Pricing Context Document
_Last updated: 2026-08-18 · Source: WSR Birthday Brochure v5.pdf + founder inputs_

---

## How Discounting Works, End to End

There are four distinct pricing paths on the site. Every one of them, when a discount applies, is computed live from the real cart total at checkout — there are no coupon codes left anywhere on the site (the last flat codes, PKGUNICORN and PKGTURF, were retired 2026-08-12).

### 1. Generic Build a Birthday (no package origin)
Just the Order-Value Discount Slabs below, nothing else.

### 2. Unicorn Magic (unicorn-basic.html)
The package's MRP is the sum of every component's **true/full value** — each tier carries both a `price` (its internal, already-discounted figure) and an `origPrice` (the real value); the MRP always uses `origPrice` when one exists, via a `realPrice()` helper, so nothing is silently pre-discounted before the customer ever sees a number (bug fixed 2026-08-18 — tier cards used to show a per-component "was/now/Save ₹X" badge using the undisclosed `price`, which this replaced with one clearly-labelled package-level discount). Default cart MRP: ₹26,500.

The guaranteed discount is whichever is bigger of: a flat ₹3,500, or 10% of the total capped at ₹3,999. That guarantee is then compared against the Order-Value Discount Slabs below — whichever of the two is worth more in rupees wins, so a customer who adds enough extras to earn a bigger sitewide slab discount gets that instead automatically, with a "🎉 you unlocked a bigger discount" popup.

Return Gifts are excluded from this discount (they already carry real per-item pricing, so discounting them again would double-dip).

### 3. Turf Takeover (turf-basic.html)
Same true-value MRP approach (decor/engagement/music/e-invite summed at full value). Default cart MRP: ₹43,000.

The guarantee here is 10% of the total capped at ₹4,750, compared against the Order-Value Discount Slabs the same way as Unicorn — bigger one wins, same popup. Unlike Unicorn, this discount applies to the **whole cart including Return Gifts**.

### 4. Spy Mystery (spy-basic.html)
No discount logic at all, at any order value — quotes one fixed price and checkout charges exactly that.

---

## Order-Value Discount Slabs
_The baseline sitewide auto-discount (2026-08-12, per Shruti; slab boundaries widened 2026-08-14; table corrected 2026-08-18 — Unicorn/Turf's own copies of this table had drifted stale and were resynced to match). Qualifying value is the cart total before any discount._

| Order Value | Discount | Capped At |
|-------------|----------|-----------|
| ₹25,000 – ₹34,999 | 5% off | up to ₹1,500 |
| ₹35,000 – ₹44,999 | 7% off | up to ₹2,500 |
| ₹45,000+ | 9% off | up to ₹4,500 |
| Below ₹25,000 | No discount | — |

This table is the one thing all four pricing paths above have in common — see "How Discounting Works" for how each path layers on top of (or ignores) it.

---

## How Total Savings Are Displayed ("trueMRP")
_Added 2026-08-18, per Shruti — "discounts should be very clearly called out, even the [free] einvite one."_

Before this, a customer building the same combo via the generic Build a Birthday flow (not a dedicated package page) only ever saw the order-value slab discount called out — if they'd also crossed the free-e-invite threshold, that saving was invisible, just folded quietly into a lower total. `trueMRP()` in builder.html now sums every cart item's real pre-savings value (its normal price, or its original price for anything zeroed out by a free-addon threshold) so the bottom bar, mini-cart, and checkout Order Summary can show one clearly-labelled struck-through MRP with **all** savings combined — the order-value discount and any unlocked free addon — instead of only part of the story. (The free-pinata threshold this originally covered was removed 2026-08-18 — see Pinata below — so today the only free-addon threshold feeding into this is E-Invite.)

---

## Music
_Renamed from "DJ" site-wide (2026-08-16, per Shruti) — user-facing labels only; internal code identifiers (S.dj, cat:'DJ', img/dj-*.jpg, etc.) are unchanged, see builder.html. Tier names further renamed 2026-08-19, per Shruti, to "Music Essential"/"Music Plus" (internal tier word stays 'Classic'/'Premium' — see musicLabel() in builder.html)._

| Tier | Price | Inclusions |
|------|-------|------------|
| Music Essential (internal: Classic) | ₹7,000 | 1 speaker, 1 mixer, 2 cordless mics, 1 operator. Up to 50 guests, 4 hours. |
| Music Plus (internal: Premium) | ₹11,000 | 2 big speakers, 1 mixer, 2 cordless mics, 1 operator. 50–200 guests, 4 hours. |

Optional add-ons: Music Lights (₹1,500), Smoke Machine (₹2,000).

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
- ₹2,000 for all options (Build a Birthday)
- **No free-above-threshold offer** (removed 2026-08-18, per Shruti — "let's not give free pinata") — Pinata always charges full price at every order value, on every pricing path (generic Build a Birthday, Spy, Unicorn, Turf alike). The old ₹40,000 threshold and its "🎁 Addon Unlocked!" framing are gone entirely.
- Free E-Invite and the sitewide Order-Value Discount Slabs are unaffected by this change and still apply as described elsewhere in this doc
- All pinata options are handmade (readymade pinatas may be added as an option in future)

## E-Invite
- **Free** above ₹20,000 order value (updated 2026-08-12, was ₹30,000), checked against the cart total excluding the e-invite's own price
- ₹500 below ₹20,000 order value
- Not offered on package-origin checkouts (Spy/Unicorn/Turf) — those always charge full e-invite price, no threshold
- Shown to the customer as "🎁 Addon Unlocked!" once free, not "(FREE)" (reworded 2026-08-18, per Shruti); the struck-through original price is still shown alongside it, and the saving is folded into the same total-savings figure as the order-value discount (see "How Total Savings Are Displayed" above) rather than being invisible

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
