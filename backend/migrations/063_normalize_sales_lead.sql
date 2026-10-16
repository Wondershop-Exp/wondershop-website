-- 063: tidy Sales Lead names (2026-10-16, per Shruti — "why is mitika sangoi
-- showing in the filter?"). Variants like "mitika", "mitika sangoi",
-- "Mitika Sangoi" become the dropdown name. Same rule as
-- scripts/normalize_sales_lead.py, now applied on startup (db_ensure.py).
UPDATE leads SET event_sales_lead = 'Mitika'  WHERE TRIM(event_sales_lead) ILIKE 'mitika%'  AND event_sales_lead <> 'Mitika';
UPDATE leads SET event_sales_lead = 'Shruti'  WHERE TRIM(event_sales_lead) ILIKE 'shruti%'  AND event_sales_lead <> 'Shruti';
UPDATE leads SET event_sales_lead = 'Sidhant' WHERE TRIM(event_sales_lead) ILIKE 'sidhant%' AND event_sales_lead <> 'Sidhant';
