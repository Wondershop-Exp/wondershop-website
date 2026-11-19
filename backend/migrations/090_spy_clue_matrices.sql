-- 090: Spy clue matrices + clue-prep jobs (2026-11-19, per Shruti — "help me
-- setup a visual dashboard for ops team (Shilpa) to be able to do the whole
-- process from putting the clues in envelopes to adding volunteer names
-- herself ... this is our IP ... this link should expire. Sales team should
-- not have access to this.").
--
--   spy_matrices    the library of station-movement matrices, reused party to
--                   party because the printed clues are reused. grid = one row
--                   per team colour, one column per round, each cell a station
--                   number 1..stations (every row and every column uses each
--                   station at most once, so no two teams meet).
--   spy_clue_jobs   one per party: which matrix, which room / game / volunteer
--                   is at each station, who the host is, team colours, and
--                   Shilpa's private link (token + expires_at + revoked).
--                   progress = {"<team>-<envelope>": "<what was on it>"} — an
--                   envelope counts as done only while the clue + name it was
--                   ticked with are still the same, so a later volunteer change
--                   un-ticks just the envelopes it affects.
-- Admin only: /api/admin/spy-clues/* is not in security.SALES_ALLOWED.
-- Applied on startup (db_ensure.py). Safe to run again.
CREATE TABLE IF NOT EXISTS spy_matrices (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    teams       INTEGER NOT NULL,
    stations    INTEGER NOT NULL,
    grid        JSONB NOT NULL,
    notes       TEXT,
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_spy_matrices_size ON spy_matrices (teams, stations);

CREATE TABLE IF NOT EXISTS spy_clue_jobs (
    id            SERIAL PRIMARY KEY,
    lead_id       INTEGER REFERENCES leads(lead_id) ON DELETE SET NULL,
    title         TEXT NOT NULL,
    event_date    DATE,
    matrix_id     INTEGER REFERENCES spy_matrices(id) ON DELETE SET NULL,
    teams         INTEGER NOT NULL,
    stations      INTEGER NOT NULL,
    grid          JSONB NOT NULL,
    team_colours  JSONB NOT NULL DEFAULT '[]'::jsonb,
    station_setup JSONB NOT NULL DEFAULT '[]'::jsonb,
    host_name     TEXT,
    final_label   TEXT,
    token         TEXT UNIQUE,
    expires_at    TIMESTAMPTZ,
    revoked       BOOLEAN NOT NULL DEFAULT FALSE,
    progress      JSONB NOT NULL DEFAULT '{}'::jsonb,
    opened_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    TEXT,
    updated_at    TIMESTAMPTZ,
    updated_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_spy_clue_jobs_lead ON spy_clue_jobs (lead_id);
-- Number of kids at the party (2026-11-19, per Shruti).
ALTER TABLE spy_clue_jobs ADD COLUMN IF NOT EXISTS kids INTEGER;

-- The classic 5x5 from Shruti's sheet (19 Nov 2026), so the library isn't empty.
INSERT INTO spy_matrices (name, teams, stations, grid, created_by)
SELECT '5×5 Classic', 5, 5, '[[1,2,3,4,5],[5,4,2,3,1],[2,3,1,5,4],[3,5,4,1,2],[4,1,5,2,3]]'::jsonb, 'Shruti'
WHERE NOT EXISTS (SELECT 1 FROM spy_matrices WHERE name = '5×5 Classic');
