-- Monthly dashboard manual inputs (2026-09-11, per Shruti — MTD dashboard
-- screenshot: "we would look at monthly revenue... add some graphics around
-- target achieved"). Two things the app has no way to source automatically
-- today live here, entered by hand once a month from the admin dashboard:
--   - the month's revenue target (Shruti wants to set this per month rather
--     than use one fixed default — it's been ramping as the business grows)
--   - Instagram DM leads and "carried forward" leads (leads still being
--     worked from a prior month) — neither channel is logged in `leads`
--     today, since every row in that table comes through the website
--     builder. See dashboard.py's leads-funnel section for what IS computed
--     automatically (Website leads, Repeat leads — both derived from real
--     `leads` rows).
CREATE TABLE IF NOT EXISTS dashboard_monthly_overrides (
    month_start                DATE PRIMARY KEY,   -- first-of-month, e.g. 2026-09-01
    monthly_target              NUMERIC,             -- NULL = fall back to config.MONTHLY_REVENUE_TARGET
    instagram_leads             INTEGER,
    instagram_converted         INTEGER,
    instagram_revenue           NUMERIC,
    carried_forward_leads       INTEGER,
    carried_forward_converted   INTEGER,
    carried_forward_revenue     NUMERIC,
    updated_by                  VARCHAR(100),
    updated_on                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
