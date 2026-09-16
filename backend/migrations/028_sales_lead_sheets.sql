-- ─────────────────────────────────────────────────────────────────────────────
-- Sales lead / event playbook module (2026-09-16, per Shruti/Cowork request)
--
-- REPLACES an earlier draft of this same migration (never run against any
-- database — safe to overwrite in place) that created a fully standalone
-- sales_lead_sheets table. The real flow, per Shruti:
--   1. A sales team member logs into the sales module (shared admin
--      password, same as packaging.html/admin.html) and registers a lead.
--      This is a REAL row in `leads` — not a separate table — tagged
--      lead_origin='sales_module' so it's distinguishable from the public
--      website's submissions (lead_origin defaults to 'website'). It shows
--      up in admin.html's normal Leads tab like any other lead.
--   2. Sales fills in client & event details (mapped onto existing `leads`
--      columns wherever one already fits — parent_name, phone, child_names,
--      child_ages, child_genders, event_date, event_time, venue,
--      kids_count, event_sales_lead), event requirements + cost, the event
--      schedule, and notes — all sales-module-specific data lives in the
--      new lead_sales_playbook table below, one row per lead, linked by
--      lead_id (same FK pattern packaging_lists.lead_id already uses).
--   3. Once the booking is confirmed, sales records the Grand Total /
--      balance received (leads.client_budget / order_advance /
--      payment_method — the exact columns admin.html's existing Billing &
--      Rewards panel already reads) and sends the lead to ops
--      (playbook_stage -> 'sent_to_ops'). This reuses the same is_booking
--      conversion admin.html's "Converted" status already performs, so
--      the row moves into the Bookings tab exactly as it would from the
--      website pipeline.
--   4. Ops (Shruti) fills in the rest of the playbook — a volunteer (and
--      materials, where relevant) per chosen activity, who's doing decor /
--      music, the lead volunteer, the general volunteer list, the ops
--      lead — then marks playbook_stage -> 'ops_ready'.
--   5. The finished playbook prints as an A4, 2-page sheet via the
--      browser's own Print → Save as PDF (no server-side PDF rendering) —
--      same visual design as the Wondershop_Order_Lead_Form.docx template
--      already in use, just populated from real data instead of blank.
-- ─────────────────────────────────────────────────────────────────────────────

-- Harmless no-op if the earlier, never-deployed draft of this migration was
-- never run anywhere; cleans it up if it somehow was.
DROP TABLE IF EXISTS sales_lead_activity_log;
DROP TABLE IF EXISTS sales_lead_sheets;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_origin VARCHAR(20) NOT NULL DEFAULT 'website';
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_lead_origin_check;
ALTER TABLE leads ADD CONSTRAINT leads_lead_origin_check CHECK (lead_origin IN ('website', 'sales_module'));
CREATE INDEX IF NOT EXISTS idx_leads_origin ON leads (lead_origin);

CREATE TABLE IF NOT EXISTS lead_sales_playbook (
    id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id                     INTEGER NOT NULL UNIQUE REFERENCES leads(lead_id),

    -- event requirements (options + cost), one free-shape JSON object keyed
    -- by category (decor, host, host_gifts, music, return_gifts,
    -- return_gift_tags, packaging, pinata_type, pinata_bags,
    -- pinata_fillings, cake) so the frontend can add a category without a
    -- migration — each value shaped {"selected": "...", "cost": 1234, ...}.
    requirements                JSONB NOT NULL DEFAULT '{}',

    -- chosen catalogue activities, price snapshot at time of picking, ops
    -- later adds volunteer/materials to the same entries in place:
    -- [{"id","name","price","flat","volunteer","materials"}]
    activities                  JSONB NOT NULL DEFAULT '[]',
    -- freeform "not in the list yet" entries for Shruti to evaluate, never
    -- auto-priced: [{"text","added_by","added_on"}]
    new_activity_suggestions    JSONB NOT NULL DEFAULT '[]',

    -- event schedule entered by sales: [{"time","item"}]
    event_schedule              JSONB NOT NULL DEFAULT '[]',

    -- timing detail not covered by leads.event_time (start time)
    event_end_time              VARCHAR(20),
    venue_handover_time         VARCHAR(20),
    packup_time                 VARCHAR(20),

    -- notes
    notes_special_instructions  TEXT,
    notes_changes_updates       TEXT,

    -- ops assignments (stage 4) — Sales Lead itself reuses the existing
    -- leads.event_sales_lead column (see 010_order_form.sql), so it is
    -- deliberately not duplicated here.
    volunteers_general          VARCHAR(500),
    lead_volunteer              VARCHAR(255),
    decor_assigned_to           VARCHAR(255),
    music_assigned_to           VARCHAR(255),
    ops_lead_name               VARCHAR(255),

    -- post-event notes, filled in after the event (same as the printed
    -- Wondershop_Order_Lead_Form.docx template)
    post_event_missing_items    TEXT,
    post_event_client_feedback  TEXT,
    post_event_internal_notes   TEXT,

    -- workflow
    playbook_stage              VARCHAR(20) NOT NULL DEFAULT 'sales_intake'
                                   CHECK (playbook_stage IN ('sales_intake', 'sent_to_ops', 'ops_ready')),
    sent_to_ops_by              VARCHAR(255),
    sent_to_ops_at              TIMESTAMPTZ,
    ops_ready_by                VARCHAR(255),
    ops_ready_at                TIMESTAMPTZ,

    created_by                  VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by                  VARCHAR(255),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lsp_lead_id ON lead_sales_playbook (lead_id);
CREATE INDEX IF NOT EXISTS idx_lsp_stage   ON lead_sales_playbook (playbook_stage);

-- Append-only edit trail (same convention as sales_lead_activity_log /
-- change_log elsewhere) — powers the "last updated by X" line and a
-- visible history so several teammates can see who did what.
CREATE TABLE IF NOT EXISTS lead_sales_playbook_log (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    playbook_id   INTEGER NOT NULL REFERENCES lead_sales_playbook(id) ON DELETE CASCADE,
    actor         VARCHAR(255) NOT NULL,
    action        VARCHAR(30) NOT NULL
                    CHECK (action IN (
                      'created', 'updated', 'activity_added', 'activity_removed',
                      'new_activity_suggested', 'sent_to_ops', 'ops_ready'
                    )),
    detail        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lsp_log_playbook_id ON lead_sales_playbook_log (playbook_id);
