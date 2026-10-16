-- 064: "Re-engage later" lead status (2026-10-16, per Shruti). For old leads
-- the team has already spoken to (including past customers) that we will
-- contact again at a planned time - their upcoming birthday, or Christmas for
-- repeat / high-spending customers - instead of showing them as New.
-- Also applied on startup (db_ensure.py), after 042. Safe to run again.

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'New', 'Initial Discussions Done', 'Proposal Sent', 'Negotiations Ongoing',
    'Not Interested', 'DND', 'Did not Enquire', 'Cancelled', 'Re-engage later'
));
