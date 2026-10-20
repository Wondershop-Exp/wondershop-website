-- 072: admin override of the value a booking earns sales commission on
-- (2026-10-20, per Shruti: "sometimes for some costs, we cannot give a
-- commission. so give sid/i a provision to adjust the total revenue on which
-- she will get commission"). NULL = use the booking value.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commission_base NUMERIC(12, 2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commission_note TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commission_set_by TEXT;
