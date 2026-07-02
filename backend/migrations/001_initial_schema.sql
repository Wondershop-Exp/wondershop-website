-- ============================================================
-- Wondershop Experiences — Database Schema
-- Version: 2.0  |  Source: WS_DataDictionary_v1.docx (June 2026)
-- Engine: PostgreSQL
-- ============================================================
-- Type mapping from DD (MySQL) → PostgreSQL used here:
--   INT UNSIGNED AUTO_INCREMENT  → SERIAL  (4-byte integer, ~2.1B max)
--   TINYINT(1)                   → BOOLEAN
--   DATETIME / CURRENT_TIMESTAMP → TIMESTAMPTZ / NOW()
--   JSON                         → JSONB   (binary, indexable)
--   AUTO ON UPDATE               → set_updated_on() trigger
-- Note: 'order' is a SQL reserved word → table named 'orders'
-- Note: is_active + timestamps added to master tables where DD
--       omitted them (consistent pattern, treated as oversight).
-- ============================================================

-- ─── AUTO-UPDATE TRIGGER FUNCTION ───────────────────────────

CREATE OR REPLACE FUNCTION set_updated_on()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_on = NOW();
    RETURN NEW;
END;
$$;


-- ============================================================
-- LAYER 5 FIRST: Platform Config & Admin
-- (other layers reference admin_members and branch_master)
-- ============================================================

-- ─── admin_members ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS admin_members (
    admin_id       SERIAL PRIMARY KEY,
    username       VARCHAR(100) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    name           VARCHAR(255) NOT NULL,
    email          VARCHAR(255) NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_login     TIMESTAMPTZ,
    created_on     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_admin_username UNIQUE (username)
);

-- ─── branch_master ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS branch_master (
    branch_id       SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    city            VARCHAR(100) NOT NULL,
    pincode         VARCHAR(6) NOT NULL,
    contact_number  VARCHAR(10),
    timings         VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_on      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_branch_master_updated_on
BEFORE UPDATE ON branch_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── platform_config ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS platform_config (
    config_id    SERIAL PRIMARY KEY,
    config_key   VARCHAR(100) NOT NULL,
    config_value VARCHAR(500) NOT NULL,
    description  TEXT,
    updated_by   INTEGER REFERENCES admin_members(admin_id),
    updated_on   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_config_key UNIQUE (config_key)
);

-- ─── terms_conditions ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS terms_conditions (
    tc_id           SERIAL PRIMARY KEY,
    version         VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    effective_from  DATE NOT NULL,
    created_by      INTEGER REFERENCES admin_members(admin_id),
    created_on      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT FALSE
);


-- ============================================================
-- LAYER 1: Client & Child Management
-- ============================================================

-- ─── client_master ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS client_master (
    client_id         SERIAL PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    primary_mobile    VARCHAR(10) NOT NULL,
    secondary_mobile  VARCHAR(10),
    email             VARCHAR(255),
    pincode           VARCHAR(6) NOT NULL,
    city              VARCHAR(100) NOT NULL
                        CHECK (city IN ('Mumbai', 'Pune', 'Navi Mumbai')),
    state             VARCHAR(100) NOT NULL DEFAULT 'Maharashtra',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id   INTEGER REFERENCES client_master(client_id),
    created_on        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_client_mobile UNIQUE (primary_mobile)
);

CREATE INDEX IF NOT EXISTS idx_client_email ON client_master(email);

CREATE TRIGGER trg_client_master_updated_on
BEFORE UPDATE ON client_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── child_master ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS child_master (
    child_id         SERIAL PRIMARY KEY,
    client_id        INTEGER NOT NULL REFERENCES client_master(client_id),
    name             VARCHAR(255) NOT NULL,
    dob              DATE NOT NULL,
    gender           VARCHAR(10) NOT NULL
                       CHECK (gender IN ('Male', 'Female', 'Other')),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id  INTEGER REFERENCES child_master(child_id),
    created_on       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_child_client ON child_master(client_id);

CREATE TRIGGER trg_child_master_updated_on
BEFORE UPDATE ON child_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();


-- ============================================================
-- VENDOR MASTER (needed by service masters below)
-- ============================================================

-- ─── vendor_master ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vendor_master (
    vendor_id             SERIAL PRIMARY KEY,
    name                  VARCHAR(255) NOT NULL,
    primary_contact_name  VARCHAR(255),
    primary_mobile        VARCHAR(10) NOT NULL,
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

CREATE TRIGGER trg_vendor_master_updated_on
BEFORE UPDATE ON vendor_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();


-- ============================================================
-- LAYER 3: Service Masters
-- ============================================================

-- ─── base_decor_master ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS base_decor_master (
    decor_id             SERIAL PRIMARY KEY,
    name                 VARCHAR(255) NOT NULL,
    type                 VARCHAR(20) NOT NULL
                           CHECK (type IN ('Theme', 'Standard')),
    price                DECIMAL(10,2) NOT NULL,
    image_url            VARCHAR(500),
    description          TEXT,
    print_requirements   TEXT,
    stand_requirements   TEXT,
    lights_requirements  TEXT,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id      INTEGER REFERENCES base_decor_master(decor_id),
    created_on           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_base_decor_master_updated_on
BEFORE UPDATE ON base_decor_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── decor_theme ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS decor_theme (
    decor_theme_id   SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    fk_decor_id      INTEGER NOT NULL REFERENCES base_decor_master(decor_id),
    image_url        VARCHAR(500),
    video_url        VARCHAR(500),
    type             VARCHAR(20) NOT NULL
                       CHECK (type IN ('Theme', 'Standard')),
    age_group        VARCHAR(100),
    gender           VARCHAR(10)
                       CHECK (gender IN ('Male', 'Female', 'Any')),
    balloon_colours  VARCHAR(500),
    description      TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id  INTEGER REFERENCES decor_theme(decor_theme_id),
    created_on       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dt_base_decor ON decor_theme(fk_decor_id);

CREATE TRIGGER trg_decor_theme_updated_on
BEFORE UPDATE ON decor_theme
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── activities_master ──────────────────────────────────────
-- Note: Pricing is NOT stored here. It lives in service_vendor
-- (sp_per_unit, per_unit_type = 'per_child') and pricing_models.

CREATE TABLE IF NOT EXISTS activities_master (
    activity_id    SERIAL PRIMARY KEY,
    name           VARCHAR(255) NOT NULL,
    category       VARCHAR(100) NOT NULL,
    age_group      VARCHAR(100),
    gender         VARCHAR(10) CHECK (gender IN ('Male', 'Female', 'Any')),
    interest_area  VARCHAR(255),
    duration       INTEGER,                -- minutes
    requirements   TEXT,
    image_url      VARCHAR(500),
    video_url      VARCHAR(500),
    tag            VARCHAR(100),
    moq            INTEGER,               -- min children required
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_on     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_activities_master_updated_on
BEFORE UPDATE ON activities_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── host_master ────────────────────────────────────────────
-- Note: Individual host details (name, photo) are INTERNAL.
-- Clients select by tier only. Host is assigned post-booking by AM.

CREATE TABLE IF NOT EXISTS host_master (
    host_id           SERIAL PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    bio               TEXT,
    photo_url         VARCHAR(500),
    video_url         VARCHAR(500),
    theme_tags        VARCHAR(500),
    event_types       VARCHAR(500),
    gender            VARCHAR(10) CHECK (gender IN ('Male', 'Female', 'Other')),
    dob               DATE,
    years_of_working  INTEGER,
    host_tier         VARCHAR(20) NOT NULL
                        CHECK (host_tier IN ('Standard', 'Premium', 'Super Premium')),
    fk_vendor_id      INTEGER REFERENCES vendor_master(vendor_id),
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id   INTEGER REFERENCES host_master(host_id),
    created_on        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_host_master_updated_on
BEFORE UPDATE ON host_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── dj_master ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dj_master (
    dj_id                  SERIAL PRIMARY KEY,
    name                   VARCHAR(255) NOT NULL,
    equipment_description  TEXT,
    video_url              VARCHAR(500),
    years_of_experience    INTEGER,
    dj_tier                VARCHAR(20) NOT NULL
                             CHECK (dj_tier IN ('Standard', 'Premium')),
    fk_vendor_id           INTEGER REFERENCES vendor_master(vendor_id),
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_on             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_dj_master_updated_on
BEFORE UPDATE ON dj_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── pinata_master ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pinata_master (
    pinata_id       SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    theme           VARCHAR(255),
    age_group       VARCHAR(100),
    dimensions      VARCHAR(100),
    image_url       VARCHAR(500),
    base_type       VARCHAR(20) CHECK (base_type IN ('Standard', 'Custom')),
    lead_time_days  INTEGER,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_on      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_pinata_master_updated_on
BEFORE UPDATE ON pinata_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── photographer_master ────────────────────────────────────
-- Note: reel add-on price is in platform_config('reel_addon_price').

CREATE TABLE IF NOT EXISTS photographer_master (
    photographer_id   SERIAL PRIMARY KEY,
    package_name      VARCHAR(255) NOT NULL,
    tier              VARCHAR(20) NOT NULL
                        CHECK (tier IN ('Basic', 'Standard', 'Premium')),
    hours             INTEGER NOT NULL,
    deliverables      TEXT,
    portfolio_url     VARCHAR(500),
    addons_available  TEXT,
    fk_vendor_id      INTEGER REFERENCES vendor_master(vendor_id),
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_on        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_photographer_master_updated_on
BEFORE UPDATE ON photographer_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── gift_master ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gift_master (
    gift_id                    SERIAL PRIMARY KEY,
    name                       VARCHAR(255) NOT NULL,
    theme                      VARCHAR(255),
    age_group                  VARCHAR(100),
    utility_tag                VARCHAR(20)
                                 CHECK (utility_tag IN (
                                   'Stationery','Personalised','Art',
                                   'Activity Kit','Toy','Book','Other')),
    mrp                        DECIMAL(10,2) NOT NULL,
    sp                         DECIMAL(10,2) NOT NULL,
    dimensions                 VARCHAR(100),
    image_url                  VARCHAR(500),
    packaging_options          VARCHAR(255),
    personalisation_available  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id            INTEGER REFERENCES gift_master(gift_id),
    created_on                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_gift_master_updated_on
BEFORE UPDATE ON gift_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── einvite_master ─────────────────────────────────────────
-- Note: charge logic → platform_config('einvite_free_threshold')
--       and platform_config('einvite_charge').

CREATE TABLE IF NOT EXISTS einvite_master (
    invite_id             SERIAL PRIMARY KEY,
    name                  VARCHAR(255) NOT NULL,
    theme                 VARCHAR(255),
    image_url             VARCHAR(500),
    video_url             VARCHAR(500),
    supports_multi_child  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id       INTEGER REFERENCES einvite_master(invite_id),
    created_by            INTEGER REFERENCES admin_members(admin_id),
    created_on            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_einvite_master_updated_on
BEFORE UPDATE ON einvite_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── testimonials_master ────────────────────────────────────

CREATE TABLE IF NOT EXISTS testimonials_master (
    testimonial_id  SERIAL PRIMARY KEY,
    text            TEXT,
    image_url       VARCHAR(500),
    video_url       VARCHAR(500),
    client_name     VARCHAR(255) NOT NULL,
    client_city     VARCHAR(100),
    created_on      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_testimonials_master_updated_on
BEFORE UPDATE ON testimonials_master
FOR EACH ROW EXECUTE FUNCTION set_updated_on();


-- ============================================================
-- PRICING LAYER (before orders — orders uses pincode lookup)
-- ============================================================

-- ─── pricing_models ─────────────────────────────────────────
-- Defines a complete pricing bundle for a service mix.
-- Pincodes are mapped to a model via mapping_pricing_pincode.
-- 'pinnata' spelling matches DD exactly.

CREATE TABLE IF NOT EXISTS pricing_models (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    kids_count          INTEGER,
    host_tier           VARCHAR(20)
                          CHECK (host_tier IN ('Standard', 'Premium', 'Super Premium')),
    pinnata_category    VARCHAR(20)
                          CHECK (pinnata_category IN ('Standard', 'Custom', 'None')),
    dj_tier             VARCHAR(20)
                          CHECK (dj_tier IN ('Standard', 'Premium', 'None')),
    json_activities     JSONB,         -- [{activity_id, price_per_child}]
    photographer_pack   VARCHAR(20)
                          CHECK (photographer_pack IN ('Basic', 'Standard', 'Premium', 'None')),
    fk_einvite_id       INTEGER REFERENCES einvite_master(invite_id),
    fk_decor_theme_id   INTEGER REFERENCES decor_theme(decor_theme_id),
    host_price          DECIMAL(10,2),
    pinnata_price       DECIMAL(10,2),
    dj_price            DECIMAL(10,2),
    activities_price    DECIMAL(10,2),
    photographer_price  DECIMAL(10,2),
    einvite_price       DECIMAL(10,2),
    decor_theme_price   DECIMAL(10,2),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of        INTEGER REFERENCES pricing_models(id),
    created_on          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_pricing_models_updated_on
BEFORE UPDATE ON pricing_models
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── mapping_pricing_pincode ────────────────────────────────
-- Fallback: if pincode not found → platform_config('default_pricing_model_id').

CREATE TABLE IF NOT EXISTS mapping_pricing_pincode (
    id                   SERIAL PRIMARY KEY,
    pincode              VARCHAR(6) NOT NULL,
    fk_pricing_model_id  INTEGER NOT NULL REFERENCES pricing_models(id),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_on           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pincode_active UNIQUE (pincode, is_active)
);

CREATE TRIGGER trg_mapping_pricing_pincode_updated_on
BEFORE UPDATE ON mapping_pricing_pincode
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── cart_pack_discount ─────────────────────────────────────
-- Volume discount slabs applied automatically by cart total.

CREATE TABLE IF NOT EXISTS cart_pack_discount (
    id            SERIAL PRIMARY KEY,
    cart_value    DECIMAL(10,2) NOT NULL,
    discount_pct  DECIMAL(5,2) NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_on    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_cart_pack_discount_updated_on
BEFORE UPDATE ON cart_pack_discount
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── coupons ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id           SERIAL PRIMARY KEY,
    code                VARCHAR(50) NOT NULL,
    discount_pct        DECIMAL(5,2),
    discount_amt        DECIMAL(10,2),
    max_discount_amt    DECIMAL(10,2),
    minimum_cart_value  DECIMAL(10,2),
    valid_from          DATE NOT NULL,
    valid_to            DATE NOT NULL,
    usage_limit         INTEGER,
    usage_count         INTEGER NOT NULL DEFAULT 0,
    repeat_allowed      BOOLEAN NOT NULL DEFAULT FALSE,
    owner_name          VARCHAR(255),
    owner_mobile        VARCHAR(10),
    status              VARCHAR(10) NOT NULL DEFAULT 'Active'
                          CHECK (status IN ('Active', 'Paused', 'Stopped')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    duplicate_of_id     INTEGER REFERENCES coupons(coupon_id),
    created_on          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_coupon_code UNIQUE (code),
    CONSTRAINT chk_coupon_discount
        CHECK (discount_pct IS NOT NULL OR discount_amt IS NOT NULL)
);

CREATE TRIGGER trg_coupons_updated_on
BEFORE UPDATE ON coupons
FOR EACH ROW EXECUTE FUNCTION set_updated_on();


-- ============================================================
-- LAYER 2: Orders & Cart
-- ============================================================

-- ─── orders ─────────────────────────────────────────────────
-- DD table name: 'order' (reserved SQL keyword → renamed 'orders')
-- event_status must always match latest row in order_status_history.

CREATE TABLE IF NOT EXISTS orders (
    order_id                  SERIAL PRIMARY KEY,
    event_code                VARCHAR(50) NOT NULL,
    client_id                 INTEGER NOT NULL REFERENCES client_master(client_id),
    kids_count                INTEGER NOT NULL,
    event_date                DATE NOT NULL,
    event_start_time          TIME NOT NULL,
    event_end_time            TIME NOT NULL,
    venue_name                VARCHAR(255),
    venue_address             TEXT,
    venue_type                VARCHAR(50) NOT NULL
                                CHECK (venue_type IN (
                                  'Home', 'Society Banquet Hall', 'Club',
                                  'Café / Restaurant', 'School', 'Other')),
    city                      VARCHAR(100) NOT NULL,
    pincode                   VARCHAR(6) NOT NULL,
    theme                     VARCHAR(255),
    event_status              VARCHAR(30) NOT NULL DEFAULT 'Lead'
                                CHECK (event_status IN (
                                  'Lead', 'Proposal Sent', 'Awaiting Advance',
                                  'Booked', 'Planning', 'Ready For Execution',
                                  'InProgress', 'Completed', 'Cancelled', 'Refunded')),
    fk_branch_id              INTEGER REFERENCES branch_master(branch_id),
    fk_account_manager_id     INTEGER REFERENCES admin_members(admin_id),
    decor_ready_time          TIME,
    host_start_time           TIME,
    host_end_time             TIME,
    rsvp_number               VARCHAR(10),
    einvite_name              VARCHAR(500),
    einvite_location_address  TEXT,
    einvite_time              VARCHAR(100),   -- free text e.g. "5:00 PM onwards"
    einvite_instruction       TEXT,
    json_event_schedule       JSONB,          -- [{time, activity}]
    invoice_number            VARCHAR(50),
    invoice_url               VARCHAR(500),
    created_on                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_event_code UNIQUE (event_code)
);

CREATE INDEX IF NOT EXISTS idx_order_client  ON orders(client_id);
CREATE INDEX IF NOT EXISTS idx_order_date    ON orders(event_date);
CREATE INDEX IF NOT EXISTS idx_order_status  ON orders(event_status);
CREATE INDEX IF NOT EXISTS idx_order_branch  ON orders(fk_branch_id);

CREATE TRIGGER trg_orders_updated_on
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── client_child ───────────────────────────────────────────
-- Links orders to the child(ren) being celebrated.
-- Supports twin / sibling birthdays (one order, two children).

CREATE TABLE IF NOT EXISTS client_child (
    event_child_id  SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    child_id        INTEGER NOT NULL REFERENCES child_master(child_id),
    CONSTRAINT uq_cc_order_child UNIQUE (order_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_cc_order ON client_child(order_id);
CREATE INDEX IF NOT EXISTS idx_cc_child ON client_child(child_id);

-- ─── order_status_history ───────────────────────────────────
-- Immutable audit log. Do NOT update or delete rows.
-- latest new_status must always equal orders.event_status.

CREATE TABLE IF NOT EXISTS order_status_history (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    old_status  VARCHAR(30)
                  CHECK (old_status IN (
                    'Lead', 'Proposal Sent', 'Awaiting Advance', 'Booked',
                    'Planning', 'Ready For Execution', 'InProgress',
                    'Completed', 'Cancelled', 'Refunded')),
    new_status  VARCHAR(30) NOT NULL
                  CHECK (new_status IN (
                    'Lead', 'Proposal Sent', 'Awaiting Advance', 'Booked',
                    'Planning', 'Ready For Execution', 'InProgress',
                    'Completed', 'Cancelled', 'Refunded')),
    changed_by  INTEGER NOT NULL REFERENCES admin_members(admin_id),
    changed_on  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_on  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_osh_order ON order_status_history(order_id);

-- ─── cart ───────────────────────────────────────────────────
-- Financial summary. One cart per order.
-- balance_due updated by application whenever a payment is recorded.

CREATE TABLE IF NOT EXISTS cart (
    cart_id                   SERIAL PRIMARY KEY,
    order_id                  INTEGER NOT NULL REFERENCES orders(order_id),
    total_wo_discount         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    fk_cart_pack_discount_id  INTEGER REFERENCES cart_pack_discount(id),
    fk_cpd_pct                DECIMAL(5,2),     -- pack discount % snapshot
    fk_cpd_amt                DECIMAL(10,2),    -- pack discount amount
    fk_coupon_id              INTEGER REFERENCES coupons(coupon_id),
    coupon_code               VARCHAR(50),      -- snapshot at application
    coupon_pct                DECIMAL(5,2),
    coupon_amt                DECIMAL(10,2),
    total_payable             DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    advance_paid              DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    balance_due               DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    status                    VARCHAR(15) NOT NULL DEFAULT 'Active'
                                CHECK (status IN ('Active', 'Confirmed', 'Cancelled')),
    gift_delivery_address     VARCHAR(500),
    gift_required_by_date     DATE,
    created_on                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cart_order UNIQUE (order_id)
);

CREATE TRIGGER trg_cart_updated_on
BEFORE UPDATE ON cart
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── cart_config ────────────────────────────────────────────
-- Pre-booking configuration snapshot (builder UI source of truth).
-- One row per cart. Columnar format — one FK/ENUM per service step.
-- Auto-generates order_item rows when order moves to Awaiting Advance.

CREATE TABLE IF NOT EXISTS cart_config (
    cart_config_id         SERIAL PRIMARY KEY,
    cart_id                INTEGER NOT NULL REFERENCES cart(cart_id),
    fk_decor_theme_id      INTEGER REFERENCES decor_theme(decor_theme_id),
    host_tier              VARCHAR(20)
                             CHECK (host_tier IN ('Standard', 'Premium', 'Super Premium')),
    dj_tier                VARCHAR(20) DEFAULT 'None'
                             CHECK (dj_tier IN ('Standard', 'Premium', 'None')),
    fk_dj_id               INTEGER REFERENCES dj_master(dj_id),   -- assigned post-booking
    pinata_category        VARCHAR(20) DEFAULT 'None'
                             CHECK (pinata_category IN ('Standard', 'Custom', 'None')),
    fk_einvite_id          INTEGER REFERENCES einvite_master(invite_id),
    photographer_pack      VARCHAR(20) DEFAULT 'None'
                             CHECK (photographer_pack IN ('Basic', 'Standard', 'Premium', 'None')),
    fk_photographer_id     INTEGER REFERENCES photographer_master(photographer_id), -- assigned post-booking
    json_giftbundle        JSONB,          -- [{gift_id, qty, personalised, tag_design}]
    json_activity          JSONB,          -- [{activity_id, qty}]
    json_booking_snapshot  JSONB,          -- immutable snapshot at booking confirmation
    created_on             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cc_cart UNIQUE (cart_id)
);

CREATE TRIGGER trg_cart_config_updated_on
BEFORE UPDATE ON cart_config
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── order_item ─────────────────────────────────────────────
-- Financial ledger. One row per billable line item.
-- Auto-generated from cart_config when order → 'Awaiting Advance'.
-- AM can adjust finalized_price post-booking.
-- entity_table: name of master table (e.g. 'decor_theme', 'host_master')
-- fk_entity_id: PK of row in that table (polymorphic association).

CREATE TABLE IF NOT EXISTS order_item (
    order_item_id    SERIAL PRIMARY KEY,
    order_id         INTEGER NOT NULL REFERENCES orders(order_id),
    type             VARCHAR(100) NOT NULL,   -- 'decor','host','activity', etc.
    entity_table     VARCHAR(100) NOT NULL,   -- master table name
    fk_entity_id     INTEGER NOT NULL,        -- PK in entity_table
    quantity         INTEGER NOT NULL DEFAULT 1,
    display_price    DECIMAL(10,2) NOT NULL,  -- price shown to client at booking
    finalized_price  DECIMAL(10,2),           -- AM-confirmed price; NULL until set
    created_on       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oi_order  ON order_item(order_id);
CREATE INDEX IF NOT EXISTS idx_oi_entity ON order_item(entity_table, fk_entity_id);

CREATE TRIGGER trg_order_item_updated_on
BEFORE UPDATE ON order_item
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── payments ───────────────────────────────────────────────
-- Supports multiple instalments, refunds, and mixed methods.

CREATE TABLE IF NOT EXISTS payments (
    payment_id      SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    amount          DECIMAL(10,2) NOT NULL,
    status          VARCHAR(15) NOT NULL
                      CHECK (status IN ('Pending', 'Completed', 'Failed', 'Refunded')),
    gateway         VARCHAR(100),
    gateway_ref     VARCHAR(255),
    payment_type    VARCHAR(25) NOT NULL
                      CHECK (payment_type IN (
                        'Advance', 'Second Installment',
                        'Final Settlement', 'Refund')),
    payment_method  VARCHAR(20) NOT NULL
                      CHECK (payment_method IN (
                        'UPI', 'Cash', 'Cash Deposit', 'Bank Transfer')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_order  ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payments(status);


-- ============================================================
-- LAYER 4: Operations & Vendors
-- ============================================================

-- ─── service_vendor ─────────────────────────────────────────
-- Maps vendors to specific services with unit pricing.
-- This is the source of truth for activity per_child pricing.

CREATE TABLE IF NOT EXISTS service_vendor (
    id             SERIAL PRIMARY KEY,
    vendor_id      INTEGER NOT NULL REFERENCES vendor_master(vendor_id),
    type           VARCHAR(20) NOT NULL
                     CHECK (type IN (
                       'Gift','Cake','Venue','Activity',
                       'Photographer','Host','DJ','Decor','Other')),
    entity_type    VARCHAR(100),   -- master table name this service belongs to
    entity_id      INTEGER,        -- PK in entity_type table
    name           VARCHAR(255) NOT NULL,
    display_name   VARCHAR(255),
    per_unit_type  VARCHAR(15)
                     CHECK (per_unit_type IN (
                       'kg','pack','hours','per_child','per_event','Other')),
    mrp_per_unit   DECIMAL(10,2) NOT NULL,
    sp_per_unit    DECIMAL(10,2) NOT NULL,
    moq            INTEGER,
    is_primary     BOOLEAN NOT NULL DEFAULT FALSE,
    margin_pct     DECIMAL(5,2),
    duration       INTEGER,        -- minutes
    created_on     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_service_vendor_updated_on
BEFORE UPDATE ON service_vendor
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── event_activity ─────────────────────────────────────────
-- Per-order activity records with vendor assignment and pricing.

CREATE TABLE IF NOT EXISTS event_activity (
    id                         SERIAL PRIMARY KEY,
    order_id                   INTEGER NOT NULL REFERENCES orders(order_id),
    activity_id                INTEGER NOT NULL REFERENCES activities_master(activity_id),
    qty                        INTEGER NOT NULL,
    display_price_perchild     DECIMAL(10,2) NOT NULL,
    discounted_price_perchild  DECIMAL(10,2),
    total_payable              DECIMAL(10,2) NOT NULL,
    vendor_id                  INTEGER REFERENCES vendor_master(vendor_id),
    vendor_cp                  DECIMAL(10,2),  -- internal cost price
    created_on                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ea_order    ON event_activity(order_id);
CREATE INDEX IF NOT EXISTS idx_ea_activity ON event_activity(activity_id);

CREATE TRIGGER trg_event_activity_updated_on
BEFORE UPDATE ON event_activity
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── order_vendor_assignment ────────────────────────────────
-- Tracks vendor assignment per service category per order.
-- Also records payment to vendor and attendance on event day.

CREATE TABLE IF NOT EXISTS order_vendor_assignment (
    id                 SERIAL PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id),
    category           VARCHAR(20) NOT NULL
                         CHECK (category IN (
                           'Cake', 'Return Gift Items', 'Host', 'DJ',
                           'Decorator', 'Photographer', 'Volunteer',
                           'Tattoo Artist', 'Activity Vendor', 'Other')),
    vendor_id          INTEGER NOT NULL REFERENCES vendor_master(vendor_id),
    quoted_cost        DECIMAL(10,2),
    final_cost         DECIMAL(10,2),
    payment_status     VARCHAR(10) DEFAULT 'Pending'
                         CHECK (payment_status IN ('Pending', 'Partial', 'Paid')),
    payment_mode       VARCHAR(20)
                         CHECK (payment_mode IN (
                           'UPI', 'Cash', 'Cash Deposit', 'Bank Transfer')),
    attendance_status  VARCHAR(15) NOT NULL DEFAULT 'Assigned'
                         CHECK (attendance_status IN (
                           'Assigned', 'Confirmed', 'Reached',
                           'Completed', 'Cancelled')),
    created_on         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ova_order  ON order_vendor_assignment(order_id);
CREATE INDEX IF NOT EXISTS idx_ova_vendor ON order_vendor_assignment(vendor_id);

CREATE TRIGGER trg_order_vendor_assignment_updated_on
BEFORE UPDATE ON order_vendor_assignment
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── event_feedback ─────────────────────────────────────────
-- Post-event feedback. Triggered when AM sets status → Completed.

CREATE TABLE IF NOT EXISTS event_feedback (
    feedback_id      SERIAL PRIMARY KEY,
    order_id         INTEGER NOT NULL REFERENCES orders(order_id),
    event_member_id  INTEGER NOT NULL REFERENCES admin_members(admin_id),
    rating           INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    feedback_txt     TEXT,
    nps_score        INTEGER NOT NULL CHECK (nps_score BETWEEN 0 AND 10),
    created_on       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_event_feedback_updated_on
BEFORE UPDATE ON event_feedback
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── leads ──────────────────────────────────────────────────
-- Every inbound enquiry before it becomes an order.
-- builder_snapshot preserves the builder state at lead submission
-- so AM can resume where the parent left off.

CREATE TABLE IF NOT EXISTS leads (
    lead_id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_name            VARCHAR(255) NOT NULL,
    child_names            VARCHAR(500),
    email                  VARCHAR(255),
    phone                  VARCHAR(10) NOT NULL,
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
                               'DND', 'Raised by Mistake',
                               'Proposal Sent', 'Booked')),
    is_dnd                 BOOLEAN NOT NULL DEFAULT FALSE,
    lead_source            VARCHAR(100),
    lead_source_detail     VARCHAR(255),
    referred_by            VARCHAR(255),
    first_call_timestamp   TIMESTAMPTZ,
    disposition            VARCHAR(100),
    lost_reason            TEXT,
    converted_by_id        INTEGER REFERENCES admin_members(admin_id),
    order_id               INTEGER REFERENCES orders(order_id),
    converted_on           TIMESTAMPTZ,
    created_on             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_phone  ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_lead_date   ON leads(event_date);
CREATE INDEX IF NOT EXISTS idx_lead_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_lead_source ON leads(lead_source);

CREATE TRIGGER trg_leads_updated_on
BEFORE UPDATE ON leads
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── coupon_usage ───────────────────────────────────────────
-- Audit trail of every coupon use. Drives usage_count increment.

CREATE TABLE IF NOT EXISTS coupon_usage (
    id              SERIAL PRIMARY KEY,
    coupon_id       INTEGER NOT NULL REFERENCES coupons(coupon_id),
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    client_id       INTEGER NOT NULL REFERENCES client_master(client_id),
    discount_given  DECIMAL(10,2) NOT NULL,
    discount_pct    DECIMAL(5,2),
    used_on         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_on      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cu_coupon ON coupon_usage(coupon_id);
CREATE INDEX IF NOT EXISTS idx_cu_client ON coupon_usage(client_id);

CREATE TRIGGER trg_coupon_usage_updated_on
BEFORE UPDATE ON coupon_usage
FOR EACH ROW EXECUTE FUNCTION set_updated_on();

-- ─── change_log ─────────────────────────────────────────────
-- Immutable audit trail. APPEND-ONLY — never UPDATE or DELETE rows.
-- Sync_Mismatch rows are written by the nightly cron job.

CREATE TABLE IF NOT EXISTS change_log (
    log_id       SERIAL PRIMARY KEY,
    admin_id     INTEGER NOT NULL REFERENCES admin_members(admin_id),
    entity_type  VARCHAR(100) NOT NULL,
    entity_id    INTEGER NOT NULL,
    action       VARCHAR(20) NOT NULL
                   CHECK (action IN ('Create', 'Update', 'Delete', 'Sync_Mismatch')),
    before_value JSONB,
    after_value  JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cl_entity ON change_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_cl_admin  ON change_log(admin_id);


-- ============================================================
-- SEEDS
-- ============================================================

-- ─── platform_config (Section 8 of DD) ──────────────────────

INSERT INTO platform_config (config_key, config_value, description) VALUES
    ('default_pricing_model_id',    '1',
     'Fallback pricing model ID when pincode has no mapping in mapping_pricing_pincode'),
    ('einvite_free_threshold',      '25000',
     'Cart total (INR) above which e-invite is included at no charge'),
    ('einvite_charge',              '500',
     'E-invite charge (INR) when cart is below the free threshold'),
    ('gift_tag_free_threshold',     '35000',
     'Cart total above which personalised return gift tags are included free'),
    ('gift_tag_personalisation_fee','15',
     'Per-gift personalisation charge (INR) when below free threshold'),
    ('advance_pct',                 '50',
     'Advance payment percentage required to confirm booking'),
    ('inactivity_cta_timeout_mins', '10',
     'Minutes of builder inactivity before "Call to Customise" CTA triggers'),
    ('support_phone',               '+919004435362',
     'Phone number for floating call button in birthday builder'),
    ('reel_addon_price',            '999',
     'Price (INR) of photographer reel add-on'),
    ('city_pincode_enum',           '[]',
     'JSON array of {city, pincode} pairs for serviceable areas. Update before launch.')
ON CONFLICT (config_key) DO NOTHING;

-- ─── cart_pack_discount (volume discount slabs) ──────────────

INSERT INTO cart_pack_discount (cart_value, discount_pct) VALUES
    (50000,  5.00),
    (75000,  8.00),
    (100000, 10.00)
ON CONFLICT DO NOTHING;

-- ─── terms_conditions ────────────────────────────────────────

INSERT INTO terms_conditions (version, content, effective_from, is_active) VALUES (
    'v1.0',
    'Quotation is provided on the basis of the scope selected with the client. Any changes in requirements may result in a revised quotation.
Advance payment of 50% is required to reserve the event date.
The remaining 40% payment is due before the event date.
The remaining 10% payment is due post the party, on the event date.
Additional transport charges may apply based on the event location.
Any additions, deletions, or guest changes must be communicated in advance.
The number of guests cannot be decreased once the team has reached the venue.
Furniture and tables can be rented at additional cost.
No cancellation or refund is allowed on the day of the event.
The client is responsible for arranging housekeeping for any cleanup required prior to or during the event.
The Wondershop team is not responsible for movement of chairs, tables, or furniture during the event.',
    CURRENT_DATE,
    TRUE
);

-- ─── admin_members ───────────────────────────────────────────
-- DO NOT seed real credentials here.
-- Use: INSERT INTO admin_members (username, password_hash, name, email)
--      VALUES ('admin', crypt('your_password', gen_salt('bf')), 'Admin', 'admin@wondershopexperiences.com');
-- Requires pgcrypto: CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
