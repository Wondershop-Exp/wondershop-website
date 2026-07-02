/**
 * Wondershop Leads — Google Apps Script Webhook
 *
 * SETUP (one-time, ~5 minutes):
 *   1. Open your Google Sheet
 *   2. Extensions → Apps Script → paste this entire file → Save
 *   3. Run → doPost_test (first time: grant permissions when prompted)
 *   4. Deploy → New deployment → Type: Web app
 *        Execute as: Me
 *        Who has access: Anyone
 *   5. Copy the deployment URL → paste into .env as GOOGLE_SHEET_WEBHOOK_URL
 *   6. Every time you edit this script, click Deploy → Manage deployments
 *      → pencil icon → New version → Deploy (URL stays the same)
 *
 * The script appends one row per lead. Column order matches HEADERS below.
 */

var SHEET_NAME = "Leads";   // Change if your sheet tab has a different name

var HEADERS = [
  "Lead ID", "Submitted At", "Status",
  "Parent Name", "Phone", "Email",
  "Event Date", "Kids Count", "Child Names", "Child Ages", "Child Genders",
  "Theme", "Venue", "Location Type", "City", "Pincode", "Budget (₹)",
  "Lead Source", "Referred By"
];

function doPost(e) {
  try {
    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(SHEET_NAME) || ss.getActiveSheet();

    // Add headers if the sheet is empty
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
      sheet.getRange(1, 1, 1, HEADERS.length)
           .setFontWeight("bold")
           .setBackground("#F4A932")
           .setFontColor("#FFFFFF");
      sheet.setFrozenRows(1);
    }

    var d = JSON.parse(e.postData.contents);

    sheet.appendRow([
      d.lead_id        || "",
      d.submitted_at   || new Date().toISOString(),
      d.status         || "New",
      d.parent_name    || "",
      d.phone          || "",
      d.email          || "",
      d.event_date     || "",
      d.kids_count     || "",
      d.child_names    || "",
      d.child_ages     || "",
      d.child_genders  || "",
      d.theme          || "",
      d.venue          || "",
      d.location_type  || "",
      d.city           || "",
      d.pincode        || "",
      d.client_budget  || "",
      d.lead_source    || "",
      d.referred_by    || "",
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ success: true, lead_id: d.lead_id }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/** Run this manually once to test without an HTTP request */
function doPost_test() {
  var fakeEvent = {
    postData: {
      contents: JSON.stringify({
        lead_id:      999,
        submitted_at: new Date().toISOString(),
        parent_name:  "Test Parent",
        phone:        "9999999999",
        email:        "test@example.com",
        event_date:   "2026-08-15",
        kids_count:   12,
        child_names:  "Arya",
        child_ages:   "7",
        child_genders:"Girl",
        theme:        "Unicorn",
        venue:        "Home",
        location_type:"Home",
        city:         "Mumbai",
        pincode:      "400001",
        client_budget:25000,
        lead_source:  "Website",
        referred_by:  "",
        status:       "New"
      })
    }
  };
  var result = doPost(fakeEvent);
  Logger.log(result.getContent());
}
