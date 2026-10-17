-- 068: approved Lead Source list (2026-10-17, per Shruti): Instagram, Facebook,
-- Google, Repeat, Stall, Referral, Website. "Insta" becomes "Instagram" (same
-- source; the Instagram filters already match both). Other old values are left
-- as they are and show as "(old value)" until someone picks from the list.
UPDATE leads SET lead_source = 'Instagram' WHERE lower(trim(lead_source)) IN ('insta', 'instagram') AND lead_source <> 'Instagram';
