-- 055: Instagram ad leads from AISensy (2026-10-12, per Shruti — "integrate
-- our Lead Management System with the AISensy platform ... name and number
-- along with the lead generation date should directly flow into the Admin
-- Panel ... Lead Source 'Insta', Lead Source Platform 'AISensy', Ad shown").
--
-- A lead that comes in through the AISensy webhook (routers/aisensy_webhook.py)
-- is an ordinary row in `leads` (lead_origin='sales_module' + a
-- lead_sales_playbook row, so the sales team works it in the Sales Quotation
-- Module exactly like one they registered themselves). These columns carry
-- what's specific to it. leads.lead_source holds "Insta".
-- Also applied on startup (db_ensure.py), so no manual run is needed.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_source_platform VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_shown VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_id VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ad_source_url TEXT;
-- When the person first messaged us on WhatsApp (from AISensy's payload;
-- falls back to the time the webhook arrived).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_leads_source_platform ON leads (lead_source_platform);

-- Every webhook call AISensy makes, kept for 60 days (pruned by the webhook
-- itself) — lets us see exactly what AISensy sends and why a message did or
-- didn't become a lead (created / duplicate / ignored / error).
CREATE TABLE IF NOT EXISTS aisensy_webhook_log (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    topic        VARCHAR(100),
    phone        VARCHAR(20),
    lead_id      INTEGER,
    outcome      VARCHAR(20) NOT NULL,
    detail       TEXT,
    payload      JSONB
);
CREATE INDEX IF NOT EXISTS idx_aisensy_log_received ON aisensy_webhook_log (received_at DESC);
