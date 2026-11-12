-- 084: Vendor item master (2026-11-12, per Shruti). "can I upload the vendor
-- catalogs via bot and then you read and update their catalogs in the vendor
-- item master, where you upload photo, name, size, price etc. - whatever is
-- available." One row per thing a partner offers (a ride, a stall, a prop ...),
-- read from their catalogue PDF / photos (vendor_catalogue_reader.py) or added
-- by hand in the Partners tab. price = what the PARTNER charges us.
-- slack_catalogue_posts = a catalogue posted in Slack #vendor-contacts (so
-- replies in its thread can add prices, or name the partner). Safe to re-run.
CREATE TABLE IF NOT EXISTS vendor_items (
    id            SERIAL PRIMARY KEY,
    vendor_id     INTEGER NOT NULL REFERENCES vendor_master(vendor_id) ON DELETE CASCADE,
    name          VARCHAR(150) NOT NULL,
    category      VARCHAR(60),
    size_text     VARCHAR(200),
    price         NUMERIC(12,2),
    price_unit    VARCHAR(40),
    price_note    VARCHAR(300),
    description   TEXT,
    item_code     VARCHAR(60),
    age_group     VARCHAR(60),
    capacity      VARCHAR(100),
    photo_data    BYTEA,
    photo_type    VARCHAR(40),
    source_ref    VARCHAR(300),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_by    VARCHAR(100),
    created_on    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vendor_items_vendor ON vendor_items (vendor_id);
CREATE UNIQUE INDEX IF NOT EXISTS vendor_items_vendor_name ON vendor_items (vendor_id, LOWER(name));

CREATE TABLE IF NOT EXISTS slack_catalogue_posts (
    id          SERIAL PRIMARY KEY,
    channel     VARCHAR(40) NOT NULL,
    ts          VARCHAR(40) NOT NULL,
    vendor_id   INTEGER,
    files       JSONB,
    status      VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS slack_catalogue_posts_thread ON slack_catalogue_posts (channel, ts);
