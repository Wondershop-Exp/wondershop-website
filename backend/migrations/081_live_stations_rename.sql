-- 081: partner category "Carnival Stalls & Mascots" renamed to
-- "Live Stations & Mascots" (2026-11-01, per Shruti). Safe to run again.
UPDATE vendor_master SET deals_in = REPLACE(deals_in, 'Carnival Stalls & Mascots', 'Live Stations & Mascots')
  WHERE deals_in LIKE '%Carnival Stalls & Mascots%';
