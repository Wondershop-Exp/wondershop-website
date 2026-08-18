-- ─────────────────────────────────────────────────────────────────────────────
-- Instagram feed cache (2026-08-18, per Shruti — "let's fix instagram with
-- meta's free api now"). Replaces the paid Elfsight widget on builder.html
-- and the hardcoded 6-photo grid on index.html with the account's real
-- latest posts, pulled via Meta's Instagram API with Instagram Login
-- (graph.instagram.com — free, no usage fee).
--
-- Single-row cache table (id is always 1) holding:
--   - the current long-lived access token + its expiry, so the backend can
--     refresh it automatically before the 60-day expiry without needing
--     Shruti to ever generate a new one by hand
--   - the last-fetched media list as JSON, so /api/instagram/feed serves a
--     fast cached response instead of calling Instagram on every page load
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS instagram_cache (
    id                INTEGER PRIMARY KEY DEFAULT 1,
    access_token      TEXT,
    token_expires_at  TIMESTAMPTZ,
    media_json        TEXT,
    profile_json      TEXT,   -- {media_count, followers_count, follows_count, username}
    fetched_at        TIMESTAMPTZ,
    updated_on        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_instagram_cache_single_row CHECK (id = 1)
);

INSERT INTO instagram_cache (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
