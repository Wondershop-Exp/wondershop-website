-- ─────────────────────────────────────────────────────────────────────────────
-- Wondershop MVP Schema
-- Only the tables needed for: lead form → DB → email + WhatsApp + Google Sheet
-- Full 35-table schema (001_initial_schema.sql) runs when booking flow is built
-- ─────────────────────────────────────────────────────────────────────────────

-- Trigger to auto-update updated_on
CREATE OR REPLACE FUNCTION set_updated_on()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_on = NOW(); RETURN NEW; END; $$;

-- ─── LEADS ───────────────────────────────────────────────────────────────────
-- Captures every inbound enquiry from the website lead form.
-- FK columns (converted_by_id, order_id) stored as plain integers for MVP —
-- FK constraints added in full schema once admin_members + orders tables exist.

CREATE TABLE IF NOT EXISTS leads (
    lead_id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_name            VARCHAR(255) NOT NULL,
    phone                  VARCHAR(20)  NOT NULL,
    child_names            VARCHAR(500),
    email                  VARCHAR(255),
    event_date             DATE,
    kids_count             INTEGER,
    child_ages             VARCHAR(255),
    child_genders          VARCHAR(255),
    venue                  VARCHAR(255),
    location_type          VARCHAR(100),
    theme                  VARCHAR(255),
    city                   VARCHAR(100),
    pincode                VARCHAR(6),
    client_budget          DECIMAL(10,2),
    builder_snapshot       JSONB,
    status                 VARCHAR(20) NOT NULL DEFAULT 'New'
                             CHECK (status IN (
                               'New', 'Followup', 'Not Interested',
                               'DND', 'Raised by Mistake', 'Proposal Sent', 'Booked'
                             )),
    is_dnd                 BOOLEAN NOT NULL DEFAULT FALSE,
    lead_source            VARCHAR(100),
    lead_source_detail     VARCHAR(255),
    referred_by            VARCHAR(255),
    first_call_timestamp   TIMESTAMPTZ,
    disposition            VARCHAR(100),
    lost_reason            TEXT,
    converted_by_id        INTEGER,   -- FK to admin_members added in full schema
    order_id               INTEGER,   -- FK to orders added in full schema
    converted_on           TIMESTAMPTZ,
    created_on             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_leads_updated_on
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION set_updated_on();

CREATE INDEX IF NOT EXISTS idx_leads_phone  ON leads (phone);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads (created_on DESC);
