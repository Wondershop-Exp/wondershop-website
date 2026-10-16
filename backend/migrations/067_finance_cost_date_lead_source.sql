-- 067: finance costs (2026-10-16, per Shruti) - Finance is the single source
-- of truth for marketing spend.
--   spent_on     the date of the cost (defaults to today on the form); ym is
--                still kept, derived from it, for the monthly P&L.
--   lead_source  marketing costs only: which lead source it was spent on
--                (Instagram, Google, Wonderfest Feb 2026, Powai Rotary
--                Christmas Stall 2025 ...). Empty = brand / general. Feeds the
--                Sales Dashboard's spend, CPL, CAC, ROAS and ACOS.
-- Backfill below only fills blanks, so it is safe on every startup.
ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS spent_on DATE;
ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS lead_source VARCHAR(100);
UPDATE finance_costs SET spent_on = to_date(ym || '01', 'YYYYMMDD') WHERE spent_on IS NULL;
UPDATE finance_costs SET lead_source = CASE
    WHEN partner ~* '(facebook|instagram|meta|aisensy)' THEN 'Instagram'
    WHEN partner ~* 'google' THEN 'Google'
    WHEN partner ~* 'wonderfest' THEN 'Wonderfest Feb 2026'
    WHEN partner ~* 'rotary' THEN 'Powai Rotary Christmas Stall 2025'
  END
 WHERE category = 'mkt' AND lead_source IS NULL AND partner IS NOT NULL;
