-- ─────────────────────────────────────────────────────────────────────────────
-- vendor_master: create it, then allow primary_mobile to be blank
-- (2026-09-10, per Shruti)
--
-- vendor_master was designed in 001_initial_schema.sql, but that whole file
-- turns out to have never actually been run against production — only
-- 002_mvp_schema.sql (and everything after it) was. So this migration
-- creates the table itself (copied from 001_initial_schema.sql — it has no
-- foreign keys into any of that file's other, still-dormant tables, only a
-- self-reference for duplicate_of_id, so it's safe to create on its own)
-- before relaxing the one constraint that would otherwise block Shruti's
-- first real data load, from her supplier tracking spreadsheet: about half
-- of those ~390 real entries don't have a captured mobile number yet
-- (several are online/company vendors — Amazon, Uber, Vistaprint — that
-- never had a personal contact number to begin with).
--
-- set_updated_on() (used by the trigger below) already exists in production
-- — it's defined in 002_mvp_schema.sql and used by trg_leads_updated_on.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vendor_master (
    vendor_id             SERIAL PRIMARY KEY,
    name                  VARCHAR(255) NOT NULL,
    primary_contact_name  VARCHAR(255),
    primary_mobile        VARCHAR(10),
    alternate_mobile      VARCHAR(10),
    whatsapp_number       VARCHAR(10),
    email                 VARCHAR(255),
    deals_in              VARCHAR(500),
    address               TEXT,
    city                  VARCHAR(100),
    pincode               VARCHAR(6),
    timings               VARCHAR(255),
    website               VARCHAR(500),
    remarks               TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id       INTEGER REFERENCES vendor_master(vendor_id),
    created_on            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_vendor_master_updated_on'
    ) THEN
        CREATE TRIGGER trg_vendor_master_updated_on
        BEFORE UPDATE ON vendor_master
        FOR EACH ROW EXECUTE FUNCTION set_updated_on();
    END IF;
END $$;

-- primary_mobile is created nullable directly above already (the original
-- 001_initial_schema.sql version had NOT NULL here) — this ALTER is now a
-- no-op if the CREATE just ran, but keeps this migration re-runnable /
-- correct even against a vendor_master that somehow already existed with
-- the old NOT NULL constraint.
ALTER TABLE vendor_master ALTER COLUMN primary_mobile DROP NOT NULL;
