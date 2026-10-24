-- 075: leads.status was still VARCHAR(20) on the live database (migration 017,
-- which widened it, never ran there), so "Initial Discussions Done" (24
-- characters) failed to save (2026-10-24, per Shruti). Safe to run again.
ALTER TABLE leads ALTER COLUMN status TYPE VARCHAR(40);
