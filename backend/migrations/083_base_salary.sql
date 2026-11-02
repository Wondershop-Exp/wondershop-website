-- 083: monthly base salary per sales person for the payout summary on the
-- Sales Performance page (2026-11-02, per Shruti). The latest one set on or
-- before a month applies to that month. Safe to run again.
ALTER TABLE sales_targets ADD COLUMN IF NOT EXISTS base_salary NUMERIC(12, 2);
