-- 071: monthly sales targets per person (2026-10-20, per Shruti — "add targets
-- on conversion revenue/bookings ... show how much extra they can earn"),
-- set by the admin on the Sales Performance page. ym = YYYYMM.
CREATE TABLE IF NOT EXISTS sales_targets (
    rep              VARCHAR(80) NOT NULL,
    ym               VARCHAR(6)  NOT NULL,
    bookings_target  INTEGER,
    revenue_target   NUMERIC(12, 2),
    updated_by       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rep, ym)
);
