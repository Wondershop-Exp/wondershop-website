-- 2026-10-12, per Shruti: primary mobile is mandatory; existing partners
-- without one get a placeholder until the real number is added.
UPDATE vendor_master SET primary_mobile = '1111111111'
 WHERE COALESCE(TRIM(primary_mobile), '') = '';
