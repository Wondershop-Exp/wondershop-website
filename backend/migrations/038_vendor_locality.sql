-- 038: Vendor locality (2026-09-30, per Shruti — "add a textbox for locality
-- (based on pincode). autofill that as well"). The onboarding form looks the
-- pincode up (India Post data, via GET /api/vendor-onboarding/pincode/{pin})
-- and fills city + locality; the vendor can still edit both.
--
-- RUN THIS BEFORE deploying the matching backend: the vendor endpoints read
-- and write this column, so the Partners tab and the onboarding form fail
-- until it exists. Safe to run more than once.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS locality VARCHAR(100);
