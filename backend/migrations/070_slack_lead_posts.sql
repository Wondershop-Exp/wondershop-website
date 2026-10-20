-- 070: Slack lead bot (2026-10-20, per Shruti — "make this a channel to make
-- any leads - insta / referral etc. we can mention the lead source or you can
-- ask if not mentioned"). One row per Slack message the bot turned into leads,
-- so a reply in that message's thread ("referral", "2 - stall", "Saloni insta
-- ad") can set the source on the right leads. Also applied on startup
-- (db_ensure.py).
CREATE TABLE IF NOT EXISTS slack_lead_posts (
    channel     VARCHAR(40) NOT NULL,
    ts          VARCHAR(40) NOT NULL,
    posted_by   VARCHAR(255),
    -- [{"pos": 1, "lead_id": 123, "name": "Priya"}] in the order they were posted
    items       JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel, ts)
);
