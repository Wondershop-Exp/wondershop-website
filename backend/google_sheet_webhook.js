/**
 * Wondershop Leads & Bookings — Google Apps Script Webhook
 *
 * SETUP (one-time, ~5 minutes):
 *   1. Open your Google Sheet
 *   2. Extensions → Apps Script → paste this entire file → Save
 *   3. Run → doPost_test (first time: grant permissions when prompted)
 *   4. Run → setupSheet (adds the Status dropdown, color-coding, and the
 *        "Confirmed Bookings" tab — safe to re-run any time)
 *   5. Deploy → New deployment → Type: Web app
 *        Execute as: Me
 *        Who has access: Anyone
 *   6. Copy the deployment URL → paste into .env as GOOGLE_SHEET_WEBHOOK_URL
 *   7. Every time you edit this script, click Deploy → Manage deployments
 *      → pencil icon → New version → Deploy (URL stays the same)
 *
 * The script appends one row per lead to the "Leads & Bookings" tab. Column
 * order matches HEADERS below.
 *
 * WORKFLOW (single source of truth — no more separate booking/lead sheets):
 *   - Every submission (checkout or custom request) lands here with
 *     Status = "Lead". Sales works this "Leads & Bookings" tab top to bottom.
 *   - When a booking is actually confirmed (after the feasibility call +
 *     advance), change that row's Status to "Confirmed" using the
 *     dropdown. It will automatically appear on the "Confirmed Bookings"
 *     tab, which ops works from — that tab is a live filter, not a copy,
 *     so there's nothing to keep in sync by hand.
 *   - Use "Contacted" for leads sales has reached but not yet closed, and
 *     "Lost" for leads that won't convert (keeps the main tab honest).
 */

// 2026-08-14, per Shruti — was "Leads", but the tab she actually works from
// (with the full 55-column header row already pasted in) is called
// "Leads & Bookings". Renamed to match — see the doPost() fix below for why
// a name mismatch here silently sent data to the wrong tab.
var SHEET_NAME = "Leads & Bookings";       // Raw feed — every submission lands here
var CONFIRMED_TAB_NAME = "Confirmed Bookings"; // Live filtered view for ops
var STATUS_OPTIONS = ["Lead", "Contacted", "Confirmed", "Lost"];

// 2026-08-14, per Shruti — added "Child DOBs" + a "Services" group (Decor,
// Pinata, Return Gifts, Music, Host, Activities, Photography, E-Invite),
// broken out of the raw Cart Snapshot JSON into their own readable columns.
// IMPORTANT: this HEADERS array only gets WRITTEN to a brand-new empty
// sheet (see doPost/setupSheet below — both skip the header row if the
// sheet already has data). On your EXISTING sheet you'll need to add these
// new header cells yourself (or clear+re-run setupSheet on a fresh tab) —
// otherwise the new columns will append data past your current last column
// without a matching header label.
var HEADERS = [
  "Lead ID", "Submitted At", "Status",
  "Parent Name", "Phone", "Email",
  "Event Date", "Kids Count", "Child Names", "Child Ages", "Child Genders", "Child DOBs",
  "Theme", "Venue", "Venue Maps Link", "Venue Contact Name", "Venue Contact Phone",
  "Location Type", "City", "Pincode", "Budget (₹)",
  "Grand Total (₹)", "Discount %", "Advance Paid (₹)", "Balance Due (₹)",
  "Reward Type", "Reward Label", "Reward Value (₹)", "Reward Terms", "Reward Expiry",
  "Reward Code Issued", "Coupon Code Redeemed", "Referral Code Issued",
  "Redeemed Reward Service",
  "Remarks",
  "Lead Source", "Lead Source Detail", "Referred By",
  "Gift Delivery Address", "Gift Delivery Maps Link", "Gift Delivery Address Type",
  "Gift Delivery Contact", "Gift Delivery Contact Phone", "Gift Required By Date",
  "DJ Lights Addon", "Smoke Machine Addon",
  "Decor", "Pinata", "Return Gifts", "Music", "Host", "Activities", "Photography", "E-Invite",
  "Cart Snapshot (JSON)"
];

function doPost(e) {
  try {
    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    // 2026-08-14, per Shruti — this used to fall back to ss.getActiveSheet()
    // when no tab named SHEET_NAME existed, which silently wrote every
    // submission into whatever tab happened to be open last in the Sheets
    // UI (in practice, a stray ~19-column tab, NOT "Leads & Bookings" with
    // its full 55-column header row). Create the correctly-named tab
    // instead of guessing — this is deterministic no matter which tab was
    // last clicked in the browser.
    var sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) sheet = ss.insertSheet(SHEET_NAME);

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

    // Reward-service add-on (Free Tattoo/Bubble Artist added to an EXISTING
    // booking from the scratch-card reveal screen) updates that booking's
    // row in place rather than appending a new one.
    if (d.action === "update_reward_service") {
      return _updateRewardServiceCell(sheet, d);
    }

    sheet.appendRow([
      d.lead_id        || "",
      d.submitted_at   || new Date().toISOString(),
      d.status         || "Lead",
      d.parent_name    || "",
      d.phone          || "",
      d.email          || "",
      d.event_date     || "",
      d.kids_count     || "",
      d.child_names    || "",
      d.child_ages     || "",
      d.child_genders  || "",
      d.child_dobs     || "",
      d.theme          || "",
      d.venue          || "",
      d.venue_maps_link    || "",
      d.venue_contact_name || "",
      d.venue_contact_phone|| "",
      d.location_type  || "",
      d.city           || "",
      d.pincode        || "",
      d.client_budget  || "",
      d.order_grand_total  || "",
      d.order_discount_pct || "",
      d.order_advance       || "",
      d.order_balance       || "",
      d.reward_type    || "",
      d.reward_label   || "",
      d.reward_value   || "",
      d.reward_terms   || "",
      d.reward_expiry  || "",
      d.reward_code    || "",
      d.redeemed_coupon_code || "",
      d.referral_code  || "",
      "",  // Redeemed Reward Service — only ever set later, via the update_reward_service action
      d.remarks        || "",
      d.lead_source        || "",
      d.lead_source_detail || "",
      d.referred_by    || "",
      d.gift_delivery_address      || "",
      d.gift_delivery_maps_link    || "",
      d.gift_delivery_address_type || "",
      d.gift_delivery_contact      || "",
      d.gift_delivery_contact_phone|| "",
      d.gift_required_by_date      || "",
      d.dj_lights_addon            || "",
      d.dj_smoke_machine_addon     || "",
      d.decor          || "",
      d.pinata         || "",
      d.return_gifts   || "",
      d.music          || "",
      d.host           || "",
      d.activities     || "",
      d.photography    || "",
      d.einvite        || "",
      d.cart_snapshot  || "",
    ]);

    // Keep the Status dropdown + color-coding covering the newly added row
    // too, so ops/sales never hit a row without the picker.
    _applyStatusFormatting(sheet, sheet.getLastRow());

    return ContentService
      .createTextOutput(JSON.stringify({ success: true, lead_id: d.lead_id }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Handles the "update_reward_service" action — finds the row matching
 * d.lead_id (by the Lead ID column) and sets its "Redeemed Reward Service"
 * cell, instead of appending a new row. Used when a customer adds a
 * complimentary service reward (Tattoo/Bubble Artist) onto their existing
 * booking from the scratch-card reveal screen, after that booking's row
 * already exists in the sheet.
 */
function _updateRewardServiceCell(sheet, d) {
  var leadIdColIdx = HEADERS.indexOf("Lead ID");           // 0-based, for reading getValues()
  var targetColIdx = HEADERS.indexOf("Redeemed Reward Service") + 1; // 1-based, for getRange()
  var data = sheet.getDataRange().getValues();

  for (var r = 1; r < data.length; r++) {  // skip header row
    if (String(data[r][leadIdColIdx]) === String(d.lead_id)) {
      sheet.getRange(r + 1, targetColIdx).setValue(d.service_label || "");
      return ContentService
        .createTextOutput(JSON.stringify({ success: true, lead_id: d.lead_id, updated_row: r + 1 }))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }

  return ContentService
    .createTextOutput(JSON.stringify({ success: false, error: "Lead ID " + d.lead_id + " not found in sheet" }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Run this manually, ONCE, from the Apps Script editor (Run → setupSheet)
 * after pasting/updating this script — and again any time you want to
 * re-apply formatting. It never touches existing row data.
 *
 * Sets up:
 *   1. Header row styling + frozen row on the "Leads & Bookings" tab
 *   2. A Status column dropdown (Lead / Contacted / Confirmed / Lost)
 *   3. Conditional formatting that color-codes the Status column
 *   4. A "Confirmed Bookings" tab that live-filters to Status = Confirmed
 */
function setupSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
  }
  sheet.getRange(1, 1, 1, HEADERS.length)
       .setFontWeight("bold")
       .setBackground("#F4A932")
       .setFontColor("#FFFFFF");
  sheet.setFrozenRows(1);

  _applyStatusFormatting(sheet, Math.max(sheet.getLastRow(), 2000));

  // Confirmed Bookings tab — live filtered view, ops works from here.
  // This is a formula, not a copy, so it always reflects the Leads & Bookings tab.
  var confSheet = ss.getSheetByName(CONFIRMED_TAB_NAME) || ss.insertSheet(CONFIRMED_TAB_NAME);
  confSheet.clear();
  var statusColLetter = _colLetter(HEADERS.indexOf("Status") + 1);
  var lastColLetter   = _colLetter(HEADERS.length);
  // Sheet name has a space + "&" in it, so it must be single-quoted inside
  // the formula (bare 'Leads & Bookings!A1:...' would fail to parse).
  confSheet.getRange("A1").setFormula(
    "=QUERY('" + SHEET_NAME + "'!A1:" + lastColLetter + ',' +
    '"select * where ' + statusColLetter + ' = \'Confirmed\'", 1)'
  );
  confSheet.setFrozenRows(1);

  SpreadsheetApp.getUi().alert(
    'Setup complete: "' + SHEET_NAME + '" now has a Status dropdown + color-coding, ' +
    'and "' + CONFIRMED_TAB_NAME + '" live-filters to Confirmed rows.'
  );
}

/** Applies the Status dropdown + conditional color-coding through row `throughRow`. */
function _applyStatusFormatting(sheet, throughRow) {
  var statusCol = HEADERS.indexOf("Status") + 1; // 1-based
  var numRows = Math.max(throughRow - 1, 1);
  var statusRange = sheet.getRange(2, statusCol, numRows, 1);

  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(STATUS_OPTIONS, true)
    .setAllowInvalid(false)
    .build();
  statusRange.setDataValidation(rule);

  var rules = [
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Lead").setBackground("#FEF3C7").setFontColor("#92400E")
      .setRanges([statusRange]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Contacted").setBackground("#DBEAFE").setFontColor("#1E40AF")
      .setRanges([statusRange]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Confirmed").setBackground("#DCFCE7").setFontColor("#166534")
      .setRanges([statusRange]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Lost").setBackground("#FEE2E2").setFontColor("#991B1B")
      .setRanges([statusRange]).build(),
  ];
  sheet.setConditionalFormatRules(rules);
}

/** Converts a 1-based column number to its A1 letter(s), e.g. 42 → "AP". */
function _colLetter(n) {
  var s = "";
  while (n > 0) {
    var rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
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
        reward_code:  "",
        redeemed_coupon_code: "",
        referral_code: "",
        status:       "Lead"
      })
    }
  };
  var result = doPost(fakeEvent);
  Logger.log(result.getContent());
}
