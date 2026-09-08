-- ─────────────────────────────────────────────────────────────────────────────
-- Packaging module: quantities + staff remarks (2026-09-08, per Shruti)
--
-- Adds two things to packaging_items, both driven by the redesigned staff
-- packing view (packaging list "Ledger" design):
--   qty         — optional quantity admin sets per item when composing the
--                 list (e.g. "Balloons — green, orange, red" x3). Shown as
--                 a small badge next to the item. NULL = no badge shown.
--   remark(...) — a free-text note staff can leave on any item from the
--                 tablet view, for "didn't find this" / "packed something
--                 different" cases — separate from the checked state, so
--                 an item can be checked off AND carry a note for whoever
--                 reviews the list afterwards. remark_by/remark_at mirror
--                 checked_by/checked_at.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE packaging_items
    ADD COLUMN IF NOT EXISTS qty        INTEGER,
    ADD COLUMN IF NOT EXISTS remark     TEXT,
    ADD COLUMN IF NOT EXISTS remark_by  VARCHAR(255),
    ADD COLUMN IF NOT EXISTS remark_at  TIMESTAMPTZ;
