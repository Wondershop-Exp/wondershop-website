-- ─────────────────────────────────────────────────────────────────────────────
-- Admin booking-management overrides
-- Powers the internal admin.html page: lets team members assign/modify
-- booking fields WITHOUT ever mutating the original leads row or
-- builder_snapshot JSON. "Customer's Choice" shown on the admin page is
-- always: override.customer_choice_override ?? derived-from-original.
-- Every change is appended to booking_change_log for a full audit trail.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS booking_field_overrides (
    id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id                     INTEGER NOT NULL REFERENCES leads(lead_id),
    field_key                   VARCHAR(100) NOT NULL,
    field_label                 VARCHAR(255) NOT NULL,
    section                     VARCHAR(50)  NOT NULL DEFAULT 'Customer & Event Details',
    customer_choice_override    TEXT,
    assigned_value              TEXT,
    remarks                     TEXT,
    removed                     BOOLEAN NOT NULL DEFAULT FALSE,
    is_custom                   BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by                  VARCHAR(255),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (lead_id, field_key)
);

CREATE INDEX IF NOT EXISTS idx_bfo_lead_id ON booking_field_overrides (lead_id);

CREATE TABLE IF NOT EXISTS booking_change_log (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id      INTEGER NOT NULL REFERENCES leads(lead_id),
    field_key    VARCHAR(100),
    field_label  VARCHAR(255),
    change_type  VARCHAR(30) NOT NULL,   -- customer_choice | assigned_value | remarks | removed | restored | field_added | coupon | payment_status
    old_value    TEXT,
    new_value    TEXT,
    changed_by   VARCHAR(255) NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bcl_lead_id ON booking_change_log (lead_id);
CREATE INDEX IF NOT EXISTS idx_bcl_changed_at ON booking_change_log (changed_at DESC);
