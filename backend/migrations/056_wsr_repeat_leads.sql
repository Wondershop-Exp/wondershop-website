-- 056: "WSR Repeat" leads — past Wondershop retail-store customers (2026-10-12,
-- per Shruti). Birthday / Christmas / summer-party leads built from the old
-- store's purchase history. Each is an ordinary sales_module lead with
-- lead_source = 'WSR Repeat', plus:
--   show_from          — the lead stays out of the sales list (and admin Leads
--                        tab) until this date (2 months before the birthday,
--                        3 months for a 1st/5th/10th milestone).
--   hidden_from_team   — kept in the database but never shown to the team
--                        (owner's call, e.g. a difficult past client).
--   occasion           — Birthday / Christmas party / Summer party.
--   lead_highlights    — e.g. "REGULAR, HIGH SPENDER" (milestone is worked out
--                        from the child's age, so it stays right each year).
--   past_customer_note — notes for sales + the store purchase history.
-- Customer data itself is NOT in this repo (it is public) — it is loaded once
-- through POST /admin/sales-leads/import-wsr-repeat.
-- Also applied on startup (db_ensure.py).

ALTER TABLE leads ADD COLUMN IF NOT EXISTS show_from DATE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS hidden_from_team BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS occasion VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_highlights VARCHAR(200);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS past_customer_note TEXT;
CREATE INDEX IF NOT EXISTS idx_leads_show_from ON leads (show_from);
