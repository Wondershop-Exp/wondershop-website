-- 042: "Did not Enquire" lead status (2026-10-07, per Shruti — "add 'Did
-- not Enquire' as a status on sales lead dropdown and leads dropdown").
-- Also applied automatically on startup (db_ensure.py). Safe to run again.

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'New', 'Initial Discussions Done', 'Proposal Sent', 'Negotiations Ongoing',
    'Not Interested', 'DND', 'Did not Enquire', 'Cancelled'
));
