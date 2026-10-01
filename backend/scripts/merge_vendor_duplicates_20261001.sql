-- One-time cleanup (2026-10-01, per Shruti) — merge vendors confirmed to be
-- the same business:
--   1. Wondershop Retail      <- Wondershop
--   2. Shri Maruthi Courier   <- Shree Maruthi Courier
--   3. Thakar Adivasi Kala Aangan <- Chetan Gangavane Chitrakathi
-- (Left as separate on purpose: SM Enterprises / Ace Telecom — different
-- companies, same contact; Tattoo Artist Sakshi / Sejal Tattoo — different;
-- Aashish / Ashish Enterprises — not confirmed yet.)
--
-- For each pair: any field that is blank on the kept record is filled from
-- the duplicate, then the duplicate is marked duplicate_of_id = kept record
-- and made inactive. Nothing is deleted. The vendor form ignores rows marked
-- as duplicates, so these numbers now update only the kept record.
--
-- Run from backend/:  python run_migration.py scripts/merge_vendor_duplicates_20261001.sql
-- All-or-nothing; safe to run twice (already-merged pairs are skipped).

DO $$
DECLARE
  pairs TEXT[][] := ARRAY[
    ['Wondershop Retail',          'Wondershop'],
    ['Shri Maruthi Courier',       'Shree Maruthi Courier'],
    ['Thakar Adivasi Kala Aangan', 'Chetan Gangavane Chitrakathi']
  ];
  keep_name TEXT; dupe_name TEXT;
  keep_id INT; dupe_id INT; n_keep INT; n_dupe INT;
  i INT;
BEGIN
  FOR i IN 1 .. array_length(pairs, 1) LOOP
    keep_name := pairs[i][1]; dupe_name := pairs[i][2];

    SELECT COUNT(*), MIN(vendor_id) INTO n_keep, keep_id FROM vendor_master
     WHERE lower(trim(name)) = lower(keep_name) AND duplicate_of_id IS NULL;
    SELECT COUNT(*), MIN(vendor_id) INTO n_dupe, dupe_id FROM vendor_master
     WHERE lower(trim(name)) = lower(dupe_name) AND duplicate_of_id IS NULL;

    IF n_dupe = 0 AND EXISTS (SELECT 1 FROM vendor_master
         WHERE lower(trim(name)) = lower(dupe_name) AND duplicate_of_id IS NOT NULL) THEN
      RAISE NOTICE 'Already merged: % -> %', dupe_name, keep_name;
      CONTINUE;
    END IF;
    IF n_keep <> 1 OR n_dupe <> 1 THEN
      RAISE EXCEPTION 'Stopped, nothing changed: expected exactly one "%" (found %) and one "%" (found %)',
        keep_name, n_keep, dupe_name, n_dupe;
    END IF;

    UPDATE vendor_master k SET
      primary_contact_name     = COALESCE(NULLIF(trim(k.primary_contact_name), ''), d.primary_contact_name),
      primary_mobile           = COALESCE(NULLIF(trim(k.primary_mobile), ''), d.primary_mobile),
      alternate_mobile         = COALESCE(NULLIF(trim(k.alternate_mobile), ''), d.alternate_mobile),
      whatsapp_number          = COALESCE(NULLIF(trim(k.whatsapp_number), ''), d.whatsapp_number),
      email                    = COALESCE(NULLIF(trim(k.email), ''), d.email),
      deals_in                 = COALESCE(NULLIF(trim(k.deals_in), ''), d.deals_in),
      address                  = COALESCE(NULLIF(trim(k.address), ''), d.address),
      locality                 = COALESCE(NULLIF(trim(k.locality), ''), d.locality),
      city                     = COALESCE(NULLIF(trim(k.city), ''), d.city),
      pincode                  = COALESCE(NULLIF(trim(k.pincode), ''), d.pincode),
      timings                  = COALESCE(NULLIF(trim(k.timings), ''), d.timings),
      website                  = COALESCE(NULLIF(trim(k.website), ''), d.website),
      gst_number               = COALESCE(NULLIF(trim(k.gst_number), ''), d.gst_number),
      preferred_payment_mode   = COALESCE(NULLIF(trim(k.preferred_payment_mode), ''), d.preferred_payment_mode),
      bank_account_holder_name = COALESCE(NULLIF(trim(k.bank_account_holder_name), ''), d.bank_account_holder_name),
      bank_name                = COALESCE(NULLIF(trim(k.bank_name), ''), d.bank_name),
      bank_account_number      = COALESCE(NULLIF(trim(k.bank_account_number), ''), d.bank_account_number),
      bank_ifsc_code           = COALESCE(NULLIF(trim(k.bank_ifsc_code), ''), d.bank_ifsc_code),
      remarks = concat_ws(' | ', NULLIF(trim(k.remarks), ''),
                          'Merged duplicate "' || d.name || '" (#' || d.vendor_id || ') on 2026-10-01'
                          || CASE WHEN NULLIF(trim(d.remarks), '') IS NOT NULL
                                  THEN ' — its notes: ' || d.remarks ELSE '' END)
    FROM vendor_master d
    WHERE k.vendor_id = keep_id AND d.vendor_id = dupe_id;

    UPDATE vendor_master SET
      duplicate_of_id = keep_id,
      is_active = FALSE,
      remarks = concat_ws(' | ', NULLIF(trim(remarks), ''),
                          'Duplicate of "' || keep_name || '" (#' || keep_id || ') — merged 2026-10-01')
    WHERE vendor_id = dupe_id;

    RAISE NOTICE 'Merged % (#%) into % (#%)', dupe_name, dupe_id, keep_name, keep_id;
  END LOOP;
END $$;
