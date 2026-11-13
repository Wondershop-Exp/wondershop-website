-- 2026-11-13, per Shruti: a read-only "Sales remarks" column on the booking
-- page. What the sales panel sends over at conversion goes here; Remarks is
-- left for what the team types on the booking page.
ALTER TABLE booking_field_overrides ADD COLUMN IF NOT EXISTS sales_remarks TEXT;

-- Existing bookings: a remark written by the sales-to-booking copy and never
-- edited on the booking page since (no "remarks" change logged for that field)
-- moves to Sales remarks, so Remarks starts empty.
UPDATE booking_field_overrides o
   SET sales_remarks = o.remarks, remarks = NULL
 WHERE o.remarks IS NOT NULL AND TRIM(o.remarks) <> ''
   AND o.sales_remarks IS NULL
   AND EXISTS (SELECT 1 FROM booking_change_log l
                WHERE l.lead_id = o.lead_id AND l.field_key = o.field_key AND l.change_type = 'synced_from_sales')
   AND NOT EXISTS (SELECT 1 FROM booking_change_log l
                    WHERE l.lead_id = o.lead_id AND l.field_key = o.field_key AND l.change_type = 'remarks');
