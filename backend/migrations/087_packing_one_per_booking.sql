-- 087: One packing list per event + Slack packing bot (2026-11-16, per Shruti —
-- "1 event will have only 1 packing list", "we should be able to update/create
-- the packing list from slack as well").
--
-- 1. A unique index on packaging_lists.lead_id, so a booking can never get a
--    second list. Older duplicates (see the 2026-11-04 Delete button) would
--    make CREATE UNIQUE INDEX fail, so it is only created once there are
--    none; until then routers/packaging.py blocks new duplicates itself and
--    the startup log says which bookings still have two.
-- 2. slack_packing_posts: one row per Slack message the packing bot answered,
--    so a reply in that thread adds to the same list, and a "which one?"
--    question can be answered with a number. Applied on startup (db_ensure.py).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_pkg_lists_lead_id')
       AND NOT EXISTS (SELECT lead_id FROM packaging_lists WHERE lead_id IS NOT NULL
                       GROUP BY lead_id HAVING COUNT(*) > 1) THEN
        CREATE UNIQUE INDEX uq_pkg_lists_lead_id ON packaging_lists (lead_id) WHERE lead_id IS NOT NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS slack_packing_posts (
    channel     VARCHAR(40) NOT NULL,
    ts          VARCHAR(40) NOT NULL,
    posted_by   VARCHAR(255),
    list_id     INTEGER REFERENCES packaging_lists(id) ON DELETE SET NULL,
    -- waiting for "which booking?": {"candidates": [lead_id, ...], "text": "<the items>"}
    pending     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel, ts)
);
