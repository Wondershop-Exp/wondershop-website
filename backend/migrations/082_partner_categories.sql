-- 082: "What do you deal in" categories added from Slack #vendor-contacts
-- (2026-11-02, per Shruti). The built-in list lives in backend/partner_categories.py;
-- this table holds the ones added later, after Shruti confirms in Slack.
-- slack_category_requests = a "Add X as a new category?" question waiting for
-- a yes / no in its thread. Safe to run again.
CREATE TABLE IF NOT EXISTS partner_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(60) NOT NULL,
    added_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS partner_categories_name_lower ON partner_categories (LOWER(name));

CREATE TABLE IF NOT EXISTS slack_category_requests (
    id SERIAL PRIMARY KEY,
    channel VARCHAR(40) NOT NULL,
    thread_ts VARCHAR(40) NOT NULL,
    name VARCHAR(60) NOT NULL,
    vendor_ids TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    asked_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS slack_category_requests_thread ON slack_category_requests (channel, thread_ts);
