-- 062: call disposition "Call back later" renamed "Follow-up required"
-- (2026-10-16, per Shruti). Rewrites the label inside every saved call log.
-- Safe to re-run; applied on startup (db_ensure.py).
UPDATE lead_sales_playbook
SET call_log = (
    SELECT jsonb_agg(CASE WHEN e->>'disposition' = 'Call back later'
                          THEN jsonb_set(e, '{disposition}', '"Follow-up required"') ELSE e END
                     ORDER BY ord)
    FROM jsonb_array_elements(call_log) WITH ORDINALITY AS t(e, ord)
)
WHERE jsonb_typeof(call_log) = 'array' AND call_log::text LIKE '%Call back later%';
