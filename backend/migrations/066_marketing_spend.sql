-- 066: marketing spend by month and lead source (2026-10-16, per Shruti) -
-- entered by admin on the Sales Dashboard; drives CPL / CAC / ROAS / ACOS.
-- Never sent to the sales login. Also applied on startup (db_ensure.py).
CREATE TABLE IF NOT EXISTS marketing_spend (
    ym          CHAR(6)       NOT NULL,          -- e.g. 202610
    source      VARCHAR(100)  NOT NULL,          -- same text as leads.lead_source
    amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
    updated_by  VARCHAR(100),
    updated_on  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (ym, source)
);
