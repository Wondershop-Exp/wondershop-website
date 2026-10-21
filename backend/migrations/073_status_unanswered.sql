-- 073: "Unanswered" lead status (2026-10-21, per Shruti: "add unanswered in
-- the lead status dropdown"). Safe to run again.
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'New', 'Unanswered', 'Initial Discussions Done', 'Proposal Sent', 'Negotiations Ongoing',
    'Not Interested', 'DND', 'Did not Enquire', 'Cancelled', 'Re-engage later'
));
