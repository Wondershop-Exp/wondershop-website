-- 058: the website copy of a booking's final invite (2026-10-14, per Shruti —
-- "please hide/mask all parent numbers and venues from our website einvites").
-- Built on the booking page: the admin marks the phone number / venue areas,
-- they're blurred in the browser, and only this copy is ever served publicly.
ALTER TABLE booking_invites ADD COLUMN IF NOT EXISTS website_image BYTEA;
ALTER TABLE booking_invites ADD COLUMN IF NOT EXISTS website_image_type VARCHAR(40);
