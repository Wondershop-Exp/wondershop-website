-- 077: notes on partners + saved contacts from Slack (2026-10-28, per Shruti).
-- "create a slack channel where i can input them and you create them in the
-- vendor master ... give a comments box where I can input my thoughts so that
-- later on I can fetch them." Contacts posted in #vendor-contacts
-- (routers/slack_vendors.py) are saved in vendor_master with
-- onboarding_source = 'slack_contact'. Notes from Slack (the post, thread
-- replies) and from the Partners tab go in vendor_notes, newest first.
-- slack_vendor_posts maps a Slack post to the partner(s) it created, so a
-- later reply in its thread lands on the right partner.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

CREATE TABLE IF NOT EXISTS vendor_notes (
    id          SERIAL PRIMARY KEY,
    vendor_id   INTEGER NOT NULL REFERENCES vendor_master(vendor_id) ON DELETE CASCADE,
    note        TEXT NOT NULL,
    added_by    VARCHAR(100),
    source      VARCHAR(20) NOT NULL DEFAULT 'admin',
    slack_ts    VARCHAR(30),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vendor_notes_vendor ON vendor_notes (vendor_id, created_at DESC);

CREATE TABLE IF NOT EXISTS slack_vendor_posts (
    channel     VARCHAR(30) NOT NULL,
    ts          VARCHAR(30) NOT NULL,
    vendor_ids  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel, ts)
);

-- Allow the new origin value next to the two from migration 031.
ALTER TABLE vendor_master DROP CONSTRAINT IF EXISTS vendor_master_onboarding_source_check;
ALTER TABLE vendor_master ADD CONSTRAINT vendor_master_onboarding_source_check
    CHECK (onboarding_source IN ('admin_entered', 'self_submitted', 'slack_contact'));
