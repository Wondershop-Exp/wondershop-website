-- 043: call log on sales leads (2026-10-07, per Shruti — moving the sales
-- team off Google Sheets: "Call date (with a checkbox for first call),
-- Disposition dropdown (unanswered, call back later, wrong number),
-- Followup date time, remarks").
-- One JSON array per lead: [{"id","date","first_call","disposition",
-- "followup_at","remarks","by","at"}]. Also applied on startup (db_ensure.py).

ALTER TABLE lead_sales_playbook ADD COLUMN IF NOT EXISTS call_log JSONB;
