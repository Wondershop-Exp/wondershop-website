-- ─────────────────────────────────────────────────────────────────────────────
-- Packaging assist module (2026-09-08, per Shruti)
--
-- Digitizes the packing list she currently types up and sends over WhatsApp
-- per confirmed party, with staff checking items off by hand (she'd been
-- marking ✅ inline in the WhatsApp text). Real examples she shared show
-- these lists are bespoke per event — ad hoc headers ("Decor", "Branding",
-- "Host: Sunny", numbered activity "stations" like "1_vault - flex, cones,
-- football"), hand-written quantities/colours, sometimes no headers at all
-- (just one flat numbered list). So this is NOT an auto-composed-from-
-- catalogue system: it's a faithful digitization of the freeform list,
-- built via a paste-and-parse composer (see packaging.html), with a
-- reusable snippet library (packaging_templates) so recurring blocks
-- (e.g. "Spy Treasure Hunt Setup", "Branding Basics") don't get retyped
-- every time.
--
-- packaging_lists    — one per confirmed party. share_token is the whole
--                       access model for the staff tablet link (matches
--                       "I share it on WhatsApp" — same trust level as a
--                       WhatsApp link, no login for staff).
-- packaging_sections — ordered headers within a list ("Decor", "Branding",
--                       "1_vault - Photobooth", "Pending", ...).
-- packaging_items    — ordered freeform lines within a section, each with
--                       its own checked state + who/when (so progress
--                       survives a shift change and multiple staff can
--                       pack the same party together).
-- packaging_templates — reusable named snippets (a header + its items) ops
--                       can drop into a new list instead of retyping —
--                       seeded from Shruti's real examples, see backfill
--                       below. category is just for grouping them in the
--                       composer's picker (branding/decor/activities/host/
--                       hygiene/cake/other) — it has no bearing on where a
--                       template can be used.
-- ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS packaging_lists (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id       INTEGER REFERENCES leads(lead_id),
    title         VARCHAR(255) NOT NULL,
    event_lead    VARCHAR(255),
    share_token   VARCHAR(64) NOT NULL UNIQUE,
    created_by    VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pkg_lists_lead_id ON packaging_lists (lead_id);
CREATE INDEX IF NOT EXISTS idx_pkg_lists_share_token ON packaging_lists (share_token);

CREATE TABLE IF NOT EXISTS packaging_sections (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    packaging_list_id   INTEGER NOT NULL REFERENCES packaging_lists(id) ON DELETE CASCADE,
    header              VARCHAR(255) NOT NULL,
    sort_order          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pkg_sections_list_id ON packaging_sections (packaging_list_id);

CREATE TABLE IF NOT EXISTS packaging_items (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id    INTEGER NOT NULL REFERENCES packaging_sections(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    checked       BOOLEAN NOT NULL DEFAULT FALSE,
    checked_by    VARCHAR(255),
    checked_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pkg_items_section_id ON packaging_items (section_id);

CREATE TABLE IF NOT EXISTS packaging_templates (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    category      VARCHAR(50) NOT NULL DEFAULT 'other',
    -- items stored as a JSONB array of strings — a template is just a
    -- reusable header + item list, same shape as one pasted section.
    items         JSONB NOT NULL DEFAULT '[]',
    created_by    VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed templates from Shruti's first real examples (2026-09-08), so the
-- composer's snippet picker isn't empty on day one. She can edit/delete/add
-- to these freely from packaging.html — this is just a starting point.
INSERT INTO packaging_templates (name, category, items, created_by) VALUES
('Journaling — Materials', 'activities', '["Motivation stickers","Cutouts","Motifs","Glue","Washi tape","Gem stickers","Travel stickers","Quotes","Sticky notes","Fevicol - 12 pcs","Template","Alphabets","Glitter pens"]', 'Shruti'),
('Journaling — Per Child Kit', 'activities', '["1 Notebook","1 gem stickers","1 12x18 sticker sheet","Glitter pens","Fevicol","Black sketchpen","Washi Tape - 2","Tissue"]', 'Shruti'),
('Slime — Materials', 'activities', '["100ml bottles - 48","Stickers","Borax","Sequences","Glue","Acrylic paints in small plastic bottles - all colours","Foam","Glitter","Sequence","Jar","Plastic bowls","Spoons - metal and wooden","Powder","Plastic bottle to store the borax soln"]', 'Shruti'),
('Boys Hair Style — Materials', 'activities', '["Gel","Comb","Glitter","Color spray","Wet wipes","Easel","Board"]', 'Shruti'),
('Face Glitter — Materials', 'activities', '["Box glitter","Wet wipes","Gem stickers","Plastic pouch glitters","Easel","Board"]', 'Shruti'),
('Hair Glitter — Materials', 'activities', '["Glitter","Gel","Elastic","Hair","Tic tacs","Tail comb"]', 'Shruti'),
('Branding Basics', 'branding', '["Wondershop Tshirts","Pamphlets","Tent Card"]', 'Shruti'),
('Tape Box', 'other', '["Transparent tape - 1\"","Transparent tape - 2\"","Masking tape - 1\"","Masking tape - 2\"","Foam Tape - 1\"","Tissue double side tape - 1\"","Tissue double side tape - 2\"","Sutli Rassi","Curling Ribbon","Stapler with pins","Chalk"]', 'Shruti'),
('Spy Treasure Hunt Setup', 'activities', '["Clues in envelopes with puzzle pieces","Id cards","1_vault - easel, a4 board, cones, football, net","2_photobooth - standee, A6 sheets, pencils, invisible pens, body alphabets","3_hotel - easel, a4 board, cards","4_tarot - easel, a4 board, tarot cards small, candles, bone, skull","5_bookstore - secret code, pencil, erasers, easel, a4 board"]', 'Shruti'),
('Chitrakathi Shadow Puppet Show', 'activities', '["Wondershop light with extension","Extension cord","Masking tape","Cling wrap","Safety pins"]', 'Shruti'),
('Decor Basics', 'decor', '["Cutouts","Foil balloon (age number)","Balloons","Caution tapes","Tape box","Extension cord","Welcome poster","Name bunting","Black bedsheets"]', 'Shruti')
ON CONFLICT DO NOTHING;
