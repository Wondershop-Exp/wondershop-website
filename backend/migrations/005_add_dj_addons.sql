-- ─────────────────────────────────────────────────────────────────────────────
-- Add DJ add-on flags to leads
-- Customer-selected DJ Lights (Rs.1,500) / Smoke Machine (Rs.2,000) add-ons,
-- captured on the builder's DJ step (or the equivalent Music section on the
-- spy/unicorn/turf package pages). Replaces the old "Signature DJ" tier,
-- which bundled both at a fixed higher tier price — these are now
-- independent, itemised add-ons on top of Classic/Premium DJ.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS dj_lights_addon         BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS dj_smoke_machine_addon  BOOLEAN DEFAULT FALSE;
