-- 044: decorator rate cards (2026-10-08, per Shruti).
-- "standardize the decor options ... use the partner onboarding form, where
-- for decorator types, we'll ask pricing for these 4 panels ... This quote
-- we'll track for multiple decorators and offer the pricing based on who is
-- the best fit in terms of price and quality."
--
-- One row per rate card a decorator submits through vendor-onboarding.html
-- (a decorator who re-submits gets a new row; the newest one is current).
-- rate_card holds the whole answer set as JSON: per decor tier (does it /
-- base rate / pastel + chrome extras / set-up time / per-design same rate,
-- other rate or can't do), transport rate per zone, flex pickup, booking
-- notice, language used. vendor_id is filled in best-effort from the mobile
-- number after the vendor row is created or matched - a plain column, no
-- foreign key, like the other *_id link columns.
--
-- Photos of the decorator's past work are kept as BYTEA (same as the vendor
-- cheque and decor reference images) and only ever served through the
-- authenticated admin endpoints.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

CREATE TABLE IF NOT EXISTS decor_rate_cards (
    id            SERIAL PRIMARY KEY,
    vendor_id     INTEGER,
    vendor_name   TEXT NOT NULL,
    mobile        VARCHAR(10) NOT NULL,
    language      VARCHAR(5),
    rate_card     JSONB NOT NULL,
    reviewed      BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_on  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decor_rate_cards_mobile ON decor_rate_cards (mobile);
CREATE INDEX IF NOT EXISTS idx_decor_rate_cards_vendor ON decor_rate_cards (vendor_id);

CREATE TABLE IF NOT EXISTS decor_rate_card_photos (
    id            SERIAL PRIMARY KEY,
    rate_card_id  INTEGER NOT NULL REFERENCES decor_rate_cards(id) ON DELETE CASCADE,
    image         BYTEA NOT NULL,
    image_type    VARCHAR(20) NOT NULL,
    image_name    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decor_rate_card_photos_card ON decor_rate_card_photos (rate_card_id);
