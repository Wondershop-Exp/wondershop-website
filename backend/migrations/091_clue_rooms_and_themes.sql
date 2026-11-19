-- 091: Standard room names per theme for clue prep (2026-11-19, per Shruti —
-- "the room names are unique and standardized. can you make it a dropdown ...
-- same is applicable for harry potter as well ... I can input a new name
-- there if required ... If I add a new room name, it should be available
-- across all events").
--
--   clue_rooms        the room master, one list per theme. A room added from
--                     any party lands here and shows in every party's dropdown.
--   theme columns     a party (spy_clue_jobs) and a saved matrix (spy_matrices)
--                     belong to one theme, so Spy and Harry Potter clue sets
--                     don't get mixed up. Existing rows are Spy.
-- Applied on startup (db_ensure.py). Safe to run again.
CREATE TABLE IF NOT EXISTS clue_rooms (
    id          SERIAL PRIMARY KEY,
    theme       TEXT NOT NULL,
    name        TEXT NOT NULL,
    icon        TEXT,
    games       JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS clue_rooms_theme_name_uq ON clue_rooms (theme, lower(name));

ALTER TABLE spy_matrices  ADD COLUMN IF NOT EXISTS theme TEXT NOT NULL DEFAULT 'Spy';
ALTER TABLE spy_clue_jobs ADD COLUMN IF NOT EXISTS theme TEXT NOT NULL DEFAULT 'Spy';

-- The 5 standard Spy rooms, exactly as Shruti named them (19 Nov 2026).
INSERT INTO clue_rooms (theme, name, icon, games, sort_order, created_by) VALUES
  ('Spy', 'Surveillance Room', '📷', '["Photobooth + Fingerprint matching","Photobooth"]', 1, 'Shruti'),
  ('Spy', 'The Grand Mystery Hotel', '🏨', '["Floor Puzzle","House of Cards"]', 2, 'Shruti'),
  ('Spy', 'Madame Scarlet''s Fortune Parlor', '🔮', '["Riddles"]', 3, 'Shruti'),
  ('Spy', 'The Royal Treasury', '👑', '["Nerf","Dizzy Football"]', 4, 'Shruti'),
  ('Spy', 'The Wonder Bookstore', '📚', '["Crack the Code A4 (7-9 yrs)","Crack the Code Books (10+ yrs)"]', 5, 'Shruti')
ON CONFLICT DO NOTHING;
