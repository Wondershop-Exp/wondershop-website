-- 078: one standard Sales Lead name - Shruti, Sidhant or Mitika (2026-10-29,
-- per Shruti: "we have only 3 sales people ... cleanup this field and keep it
-- standard across"). "Shruti Admin", "SG Sales", "mitika sangoi",
-- "Sidhant (Slack)" etc. become the plain name; anything else (e.g. "System")
-- becomes empty = Unassigned. A trigger keeps every future write standard.
-- Safe to run again.
CREATE OR REPLACE FUNCTION ws_rep(v TEXT) RETURNS TEXT LANGUAGE SQL IMMUTABLE AS $$
  SELECT CASE
    WHEN v IS NULL OR TRIM(v) = '' THEN NULL
    WHEN LOWER(TRIM(v)) ~ '^(shruti|sg( |$)|sg sales)' THEN 'Shruti'
    WHEN LOWER(TRIM(v)) ~ '^(sidhant|siddhant|sid( |$))' THEN 'Sidhant'
    WHEN LOWER(TRIM(v)) ~ '^mitika' THEN 'Mitika'
    ELSE NULL END
$$;

CREATE OR REPLACE FUNCTION ws_leads_rep_trg() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.event_sales_lead := ws_rep(NEW.event_sales_lead);
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS leads_rep_std ON leads;
CREATE TRIGGER leads_rep_std BEFORE INSERT OR UPDATE OF event_sales_lead ON leads
  FOR EACH ROW EXECUTE FUNCTION ws_leads_rep_trg();

-- existing rows; an empty Sales Lead takes whoever registered the lead
UPDATE leads SET event_sales_lead = ws_rep(event_sales_lead)
  WHERE event_sales_lead IS DISTINCT FROM ws_rep(event_sales_lead);
UPDATE leads l SET event_sales_lead = ws_rep(p.created_by)
  FROM lead_sales_playbook p
  WHERE p.lead_id = l.lead_id AND l.event_sales_lead IS NULL AND ws_rep(p.created_by) IS NOT NULL;
