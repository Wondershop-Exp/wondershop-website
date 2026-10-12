-- 2026-10-12: "Mascot (1 character, 3 hours)" had a comma, which splits it in
-- the comma-separated activity lists. Renamed to "Mascot (1 character · 3 hours)".
UPDATE booking_field_overrides
   SET customer_choice_override = REPLACE(customer_choice_override, 'Mascot (1 character, 3 hours)', 'Mascot (1 character · 3 hours)')
 WHERE customer_choice_override LIKE '%Mascot (1 character, 3 hours)%';
UPDATE booking_field_overrides
   SET assigned_value = REPLACE(assigned_value, 'Mascot (1 character, 3 hours)', 'Mascot (1 character · 3 hours)')
 WHERE assigned_value LIKE '%Mascot (1 character, 3 hours)%';
UPDATE lead_sales_playbook
   SET activities = CAST(REPLACE(CAST(activities AS TEXT), 'Mascot (1 character, 3 hours)', 'Mascot (1 character · 3 hours)') AS JSONB)
 WHERE CAST(activities AS TEXT) LIKE '%Mascot (1 character, 3 hours)%';
