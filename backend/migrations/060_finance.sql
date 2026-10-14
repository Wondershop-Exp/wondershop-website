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

-- Who the cost was paid to, from the Partners list (vendor_master.name) - e.g.
-- the office landlord, each staff member. Same free-text style as event_team.
ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS partner VARCHAR(200);
-- How it was paid (same choices as Partners & Expenses on a booking) - for bank/cash recon.
-- 'Pending' = not paid yet. `paid` is kept in step (paid = paid_via <> 'Pending').
ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS paid_via VARCHAR(30);
