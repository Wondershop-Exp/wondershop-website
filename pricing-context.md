# Wondershop Experiences — Pricing Context Document
_Last updated: 2026-08-24 · Source: WSR Birthday Brochure v5.pdf + founder inputs_

---

## How Discounting Works, End to End

There are four distinct pricing paths on the site. Every one of them, when a discount applies, is computed live from the real cart total at checkout — there are no coupon codes left anywhere on the site (the last flat codes, PKGUNICORN and PKGTURF, were retired 2026-08-12).

### 1. Generic Build a Birthday (no package origin)
Just the Order-Value Discount & Freebie Tiers below, nothing else.

### 2. Unicorn Magic (unicorn-basic.html)
The package's MRP is the sum of every component's **true/full value** — each tier carries both a `price` (its internal, already-discounted figure) and an `origPrice` (the real value); the MRP always uses `origPrice` when one exists, via a `realPrice()` helper, so nothing is silently pre-discounted before the customer ever sees a number (bug fixed 2026-08-18 — tier cards used to show a per-component "was/now/Save ₹X" badge using the undisclosed `price`, which this replaced with one clearly-labelled package-level discount). Default cart MRP: ₹26,500.

The guaranteed discount is whichever is bigger of: a flat ₹3,500, or 10% of the total capped at ₹3,999. That guarantee is then compared against the **old 3-row % slab ladder** (25k→5% cap ₹1,500 / 35k→7% cap ₹2,500 / 45k→9% cap ₹4,500) — whichever of the two is worth more in rupees wins, so a customer who adds enough extras to earn a bigger sitewide slab discount gets that instead automatically, with a "🎉 you unlocked a bigger discount" popup. **This comparison is untouched by the 2026-08-24 reprice below** (explicit scope decision, 2026-08-24: the new flat-rupee tiers apply to the generic flow only) — Unicorn keeps comparing against the old % slabs, not the new table.

Return Gifts are excluded from this discount (they already carry real per-item pricing, so discounting them again would double-dip).

### 3. Turf Takeover (turf-basic.html)
Same true-value MRP approach (decor/engagement/music/e-invite summed at full value). Default cart MRP: ₹43,000.

The guarantee here is 10% of the total capped at ₹4,750, compared against the same old % slab ladder as Unicorn — bigger one wins, same popup, also untouched by the 2026-08-24 reprice below. Unlike Unicorn, this discount applies to the **whole cart including Return Gifts**.

### 4. Spy Mystery (spy-basic.html)
No discount logic at all, at any order value — quotes one fixed price and checkout charges exactly that.

---

## Order-Value Discount & Freebie Tiers
_Full reprice of the generic Build a Birthday flow, 2026-08-24, per Shruti — replaces the old 3-row %-off slab ladder with a flat-rupee monetary discount plus tiered freebies. **Generic Build a Birthday only** (explicit scope decision, 2026-08-24) — Unicorn Magic and Turf Takeover keep comparing their own package guarantee against the old % slab ladder described in "How Discounting Works" above, untouched by this table; Spy Mystery has no discount at any order value. Qualifying value is the cart total before any discount, checked against the raw catalogue total (an item becoming free doesn't itself un-qualify the cart)._

| Order Value | Monetary Discount | Freebie Amount | Total Discount | Freebie |
|-------------|-------------------|-----------------|-----------------|---------|
| ₹1 – ₹19,999 | ₹0 | ₹0 | ₹0 | — |
| ₹20,000 – ₹24,999 | ₹0 | ₹500 | ₹500 | E-Invite |
| ₹25,000 – ₹34,999 | ₹500 | ₹500 | ₹1,000 | E-Invite |
| ₹35,000 – ₹44,999 | ₹750 | ₹500 | ₹1,250 | E-Invite |
| ₹45,000 – ₹54,999 | ₹1,000 | ₹500 | ₹1,500 | E-Invite |
| ₹55,000 – ₹99,999 | ₹1,000 | ₹3,000 | ₹4,000 | Tattoo Artist + E-Invite |
| ₹1,00,000 – ₹1,49,999 | ₹1,000 | ₹8,000 | ₹9,000 | Tattoo Artist + E-Invite + 1 activity worth ₹5,000 |
| ₹1,50,000 and above | ₹1,500 | ₹8,000 | ₹9,500 | Tattoo Artist + E-Invite + 1 activity worth ₹5,000 |

Freebies are cumulative and stack — a cart at ₹1,20,000 carries all three (E-Invite, Tattoo Artist, the ₹5,000 activity credit) at once, plus the ₹1,000 monetary discount.

**How each freebie is actually granted** (builder.html — see `VALUE_TIERS`/`activityFreebiePrice()`/the single-badge `bb-freebies` widget):
- **E-Invite** — unchanged mechanic from before this reprice: the customer picks an E-Invite design on Step 6 same as always; its price zeroes out once the cart (excluding the invite itself) crosses ₹20,000. No action needed from Wondershop's side.
- **Tattoo Artist** — maps to the existing "Tattoo Station" Activities catalogue entry (₹2,500 flat, matches the freebie value exactly, so it goes fully free, not partially discounted). Auto-added the instant the cart crosses ₹55,000 (`ensureTattooClaimed()`) — no tap required. If the customer had already added Tattoo Station themselves before crossing the threshold, it simply becomes free — no double-adding.
- **₹5,000 activity credit** — per Shruti's decision on how this should work (2026-08-24): the moment the cart crosses ₹1,00,000, a picker of eligible activities capped at ₹7,500 opens automatically (Mini Art Station, Pottery Station, Nail Art Station, Glitter Station, Hair Styling for Boys/Girls — all flat-priced, non theme-restricted). Whichever one the customer picks gets up to ₹5,000 off (capped at its own price, so a ₹3,500 pick is fully free rather than going negative); if the picked activity costs more than ₹5,000, the customer pays the difference. It's added into the Activities section with the discount clearly struck-through, and the saving rolls into the same total-savings figure shown in the bottom bar and checkout Order Summary as every other discount on the site.

**How the badge widget itself works** (rewritten 2026-08-24, Round 2, per Shruti's Amazon-style feedback): a single centered circular badge sits above the sticky bottom bar (hidden below ₹15,000 cart value, and on Unicorn/Turf/Spy) showing only the *next* unresolved milestone — never all 7 at once. Its ring boundary fills in proportion to progress toward that milestone (`milestonePct()`: if `x` is the previous milestone's threshold, `y` this milestone's threshold, `z=y-x`, and `m` the current cart total, the ring is `(m-x)/z` full), with a lock icon underneath. The instant a milestone is crossed, the ring completes, the lock flips to a green tick, a short pop animation plays alongside confetti and a "🎉 …unlocked!" toast, and after a beat the badge auto-advances to show the next milestone (or hides once all 7 are resolved). Money-off milestones show the ₹ amount directly in the badge circle instead of an icon; E-Invite/Activity-credit milestones reuse the same icons as the homepage hero section (`img/icons/icon-invite-bw.png` / `icon-activities-bw.png`); the Tattoo Artist milestone auto-claims silently as described above rather than showing a "+" to tap.

This table is specific to the generic Build a Birthday flow — see "How Discounting Works" above for how Unicorn/Turf/Spy differ.

---

## How Total Savings Are Displayed ("trueMRP")
_Added 2026-08-18, per Shruti — "discounts should be very clearly called out, even the [free] einvite one."_

A customer building a combo via the generic Build a Birthday flow (not a dedicated package page) sees every savings source called out, not just the monetary discount — if they've also crossed a free-addon threshold (E-Invite, Tattoo Artist, or the ₹5,000 activity credit — see the tiers table above), that saving is shown too, not folded quietly into a lower total. `trueMRP()` in builder.html sums every cart item's real pre-savings value (its normal price, or its original price for anything zeroed/discounted by a freebie threshold) so the bottom bar, mini-cart, and checkout Order Summary can show one clearly-labelled struck-through MRP with **all** savings combined — the monetary discount and every unlocked free addon — instead of only part of the story. (The free-pinata threshold this originally covered was removed 2026-08-18 — see Pinata below — so today the freebie thresholds feeding into this are E-Invite, Tattoo Artist, and the ₹5,000 activity credit, all added 2026-08-24.)

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
_Simplified from 3 tiers to 2 (2026-08-19, per Shruti) — the old middle "Premium" tier (₹12,000/85 mins) was dropped; the old bottom "Classic" tier is renamed "Premium" (same ₹10,000/60 mins) and "Signature" (₹15,000/90 mins) is unchanged apart from copy tweaks._

| Tier | Price | Duration / Notes |
|------|-------|-------------------|
| Premium | ₹10,000 | Up to 60 mins engagement, experienced host, essential props |
| Signature | ₹15,000 | Up to 90 mins engagement, senior host, premium props |

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
- Free E-Invite/Tattoo Artist/₹5,000 activity credit and the generic flow's Order-Value Discount & Freebie Tiers are unaffected by this change and still apply as described elsewhere in this doc
- All pinata options are handmade (readymade pinatas may be added as an option in future)

## Tattoo Artist (Activities catalogue: "Tattoo Station", ₹2,500 flat)
- Free on the generic Build a Birthday flow once the cart crosses ₹55,000 — see the Order-Value Discount & Freebie Tiers table above for the full mechanic
- Not offered as a freebie on package-origin checkouts (Spy/Unicorn/Turf) — no threshold applies there, always full price if added

## E-Invite
- **Free** above ₹20,000 order value (updated 2026-08-12, was ₹30,000), checked against the cart total excluding the e-invite's own price — see the Order-Value Discount & Freebie Tiers table above
- ₹500 below ₹20,000 order value
- Not offered on package-origin checkouts (Spy/Unicorn/Turf) — those always charge full e-invite price, no threshold
- Shown to the customer as "🎁 Addon Unlocked!" once free, not "(FREE)" (reworded 2026-08-18, per Shruti); the struck-through original price is still shown alongside it, and the saving is folded into the same total-savings figure as every other discount (see "How Total Savings Are Displayed" above) rather than being invisible

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
