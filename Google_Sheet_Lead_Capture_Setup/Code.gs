/**
 * Wondershop Experiences — Lead & Booking capture into Google Sheets
 * ─────────────────────────────────────────────────────────────────
 * SETUP (one-time, ~10 minutes):
 *  1. Go to sheets.google.com → create a new blank spreadsheet.
 *     Name it something like "Wondershop Leads & Bookings".
 *  2. In that Sheet: Extensions → Apps Script. Delete any placeholder
 *     code in the editor, and paste this whole file in its place.
 *  3. Click Deploy → New deployment.
 *     - Click the gear icon next to "Select type" → choose "Web app".
 *     - Description: "Lead capture" (anything you like).
 *     - Execute as: Me (your Google account).
 *     - Who has access: Anyone.
 *     - Click Deploy. Authorize the permissions it asks for (it's your
 *       own script, talking to your own sheet — safe to allow).
 *  4. Copy the "Web app URL" it gives you (ends in /exec).
 *  5. Send that URL back — it gets pasted into builder.html as
 *     WS_SHEET_URL, and every lead + booking will start landing in
 *     this Sheet automatically, in real time.
 *
 * Re-deploying later (e.g. if you edit this script): Deploy → Manage
 * deployments → pencil icon → New version → Deploy. The URL stays the same.
 */

const SHEET_NAME = 'Leads & Bookings';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = getOrCreateSheet_();

    sheet.appendRow([
      new Date(),                 // Timestamp (when it hit the Sheet)
      data.type || '',            // 'lead' or 'booking'
      data.name || '',
      data.phone || '',
      data.email || '',
      data.child || '',
      data.event_date || '',
      data.event_time || '',
      data.kids_count || '',
      data.venue || '',
      data.pincode || '',
      data.theme || '',
      data.budget || '',
      data.estimated_total || '',
      data.advance || '',
      data.decor || '',
      data.activities || '',
      data.host || '',
      data.dj || '',
      data.pinata || '',
      data.einvite || '',
      data.photographer || '',
      data.return_gifts || '',
      data.notes || '',
      data.lead_source || 'Website',
      data.utm_source || '',
      data.page_url || '',
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  // Lets you sanity-check the deployed URL in a browser — should say "live".
  return ContentService.createTextOutput('Wondershop lead capture endpoint is live.');
}

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow([
      'Timestamp', 'Type', 'Parent Name', 'Phone', 'Email', 'Child Name(s)',
      'Event Date', 'Event Time', 'Kids Count', 'Venue', 'Pincode',
      'Theme', 'Budget', 'Estimated Total (Rs)', 'Advance (Rs)',
      'Decor', 'Activities', 'Host', 'DJ', 'Pinata', 'E-Invite',
      'Photographer', 'Return Gifts', 'Notes', 'Lead Source', 'UTM Source', 'Page URL',
    ]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, 27).setFontWeight('bold');
  }
  return sheet;
}
