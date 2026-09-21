-- 033 — record whether each booking's emails actually went out.
-- 2026-09-21, per Shruti: "mail didn't go for the booking that we just did".
-- Until now a Gmail failure was only written to the server log (Railway),
-- so nobody on the team could tell that a customer never got their
-- confirmation. The backend now stamps the outcome on the lead and the
-- booking page shows it (with the failure reason), next to the invoice line.
--
-- customer_email_*  = the confirmation (with invoice + calendar invite) to the parent
-- team_email_*      = the order-form email to contact@ (sent after the scratch card)
-- status is 'sent' or 'failed'; error holds the reason for a failure.
--
-- Safe to run more than once. Existing rows stay NULL ("no record").

ALTER TABLE leads ADD COLUMN IF NOT EXISTS customer_email_status VARCHAR(10);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS customer_email_error  TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS customer_email_at     TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS team_email_status     VARCHAR(10);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS team_email_error      TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS team_email_at         TIMESTAMPTZ;
