-- Finance dashboard (2026-10-14, per Shruti: "can we not save this cost in database?").
-- finance_costs: costs entered by hand on finance.html that aren't in the MIS
--   sheet (salaries, rent, cleaning, transport, ads...). Feeds P&L / EBITDA / cash flow.
-- finance_snapshot: one row holding the monthly + event-level summary computed in the
--   browser from the uploaded WSR MIS .xlsx (the raw sheet itself is never uploaded).
-- Admin password only (not the sales login) - see routers/finance.py.
CREATE TABLE IF NOT EXISTS finance_costs (
    id           SERIAL PRIMARY KEY,
    ym           CHAR(6)       NOT NULL,          -- e.g. 202610
    category     VARCHAR(20)   NOT NULL,          -- man | rent | elec | wifi | mkt | shopx | other
    description  VARCHAR(300),
    amount       NUMERIC(12,2) NOT NULL,
    paid         BOOLEAN       NOT NULL DEFAULT TRUE,
    created_by   VARCHAR(100),
    created_on   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS finance_costs_ym_idx ON finance_costs (ym);

CREATE TABLE IF NOT EXISTS finance_snapshot (
    id          INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    data        JSONB        NOT NULL,
    source_name VARCHAR(300),
    updated_by  VARCHAR(100),
    updated_on  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
