/**
 * Apps Script Web App for the DEDICATED Spy Agent Registration Google
 * Sheet (2026-09-22, per Shruti: keep this off the main Leads & Bookings
 * sheet, in its own sheet, with one worksheet tab per party).
 *
 * This is a separate, self-contained script from google_sheet_webhook.js
 * — it only ever handles the one action below, and it's meant to be bound
 * to a brand-new spreadsheet of its own, not the existing Leads sheet.
 *
 * ── ONE-TIME SETUP ──────────────────────────────────────────────────
 * 1. Create a new Google Sheet (e.g. name it "Spy Agent Registrations").
 * 2. In it: Extensions -> Apps Script. Delete whatever's in the default
 *    Code.gs and paste this whole file in its place.
 * 3. Deploy -> New deployment -> gear icon -> type "Web app" ->
 *    Execute as: Me, Who has access: Anyone -> Deploy.
 *    (First time, it'll ask you to authorize — that's expected.)
 * 4. Copy the "Web app URL" it gives you.
 * 5. In Railway, add an env var SPY_SHEET_WEBHOOK_URL with that URL,
 *    then redeploy the backend (or wait for the auto-redeploy).
 * That's it — every submission now creates (or reuses) a tab in THIS
 * sheet named after the party, e.g. "Saachi's 10th Birthday Quest".
 *
 * ── REDEPLOYING AFTER AN EDIT ───────────────────────────────────────
 * Any time you paste an updated version of this file in: Deploy ->
 * Manage deployments -> pencil icon -> New version -> Deploy. The Web
 * app URL stays the same, so nothing else needs to change.
 * ─────────────────────────────────────────────────────────────────────
 */

var SPY_PHOTOS_FOLDER_NAME = "Spy Agent Photos";
var SPY_HEADERS = [
  // 2026-09-24, per Shruti — "tshirt size is not coming up... a lot of
  // people have already filled in the form": the T-Shirt Size question
  // was added to the registration form on 2026-09-23 and the backend has
  // been sending tshirt_size in every payload since, but this script was
  // never updated to receive it, so it was silently dropped on every
  // submission (not recoverable — it was never written anywhere).
  "Timestamp", "Agent Name", "Agent DOB", "Parent Name", "Parent Phone", "Agent Photo", "T-Shirt Size",
];

function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    if (d.action !== "spy_agent_registration") {
      return ContentService
        .createTextOutput(JSON.stringify({ success: false, error: "Unknown action: " + d.action }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    return _appendSpyRegistration(d);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Picks the worksheet tab name for a party: prefers the human-readable
 * mission_label ("Saachi's 10th Birthday Quest (9th October)"), falls
 * back to event_id, and sanitizes for Google Sheets' tab-name rules
 * (no [ ] * ? / \ : , max 100 chars, can't start/end with a quote).
 */
function _sheetNameForParty(d) {
  var raw = (d.mission_label || d.event_id || "Party").toString();
  var clean = raw.replace(/[\[\]\*\?\/\\:]/g, "").trim();
  clean = clean.replace(/^['"]+|['"]+$/g, "").trim();
  if (clean.length > 95) clean = clean.slice(0, 95).trim();
  return clean || "Party";
}

/**
 * Appends one row to this party's worksheet tab (creating it with its
 * own header row on first use). If a photo was uploaded (base64 in
 * d.agent_photo_b64), saves it into the SPY_PHOTOS_FOLDER_NAME Drive
 * folder (created on first use, reused after), shares it view-only to
 * anyone with the link, and puts that link in the row — the photo itself
 * never touches the sheet.
 */
function _appendSpyRegistration(d) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tabName = _sheetNameForParty(d);
  var sheet = ss.getSheetByName(tabName);
  var isNewTab = !sheet;
  if (isNewTab) {
    sheet = ss.insertSheet(tabName);
    sheet.appendRow(SPY_HEADERS);
    sheet.getRange(1, 1, 1, SPY_HEADERS.length)
         .setFontWeight("bold")
         .setBackground("#6B21A8")
         .setFontColor("#FFFFFF");
    sheet.setFrozenRows(1);
    sheet.autoResizeColumns(1, SPY_HEADERS.length);
  } else {
    // 2026-09-24, per Shruti — a party tab created before T-Shirt Size
    // existed only has 6 header columns; add the 7th header here so this
    // tab's rows line up with SPY_HEADERS from now on, instead of needing
    // every existing tab fixed by hand.
    var lastCol = sheet.getLastColumn();
    var headerRow = lastCol > 0 ? sheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];
    if (headerRow.indexOf("T-Shirt Size") === -1) {
      sheet.getRange(1, SPY_HEADERS.length)
           .setValue("T-Shirt Size")
           .setFontWeight("bold")
           .setBackground("#6B21A8")
           .setFontColor("#FFFFFF");
    }
  }

  var photoLink = "";
  if (d.agent_photo_b64) {
    try {
      var folders = DriveApp.getFoldersByName(SPY_PHOTOS_FOLDER_NAME);
      var folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(SPY_PHOTOS_FOLDER_NAME);
      var mime = "image/jpeg";
      var name = d.agent_photo_filename || "agent-photo.jpg";
      if (/\.png$/i.test(name)) mime = "image/png";
      else if (/\.webp$/i.test(name)) mime = "image/webp";
      var bytes = Utilities.base64Decode(d.agent_photo_b64);
      var blob = Utilities.newBlob(bytes, mime, name);
      var file = folder.createFile(blob);
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      photoLink = file.getUrl();
    } catch (photoErr) {
      // Registration still saves even if the photo step fails for some
      // reason (e.g. Drive quota) — just flag it in the link cell instead
      // of losing the whole submission.
      photoLink = "Upload failed: " + photoErr.message;
    }
  }

  sheet.appendRow([
    d.submitted_at || new Date().toISOString(),
    d.agent_name   || "",
    d.agent_dob    || "",
    d.parent_name  || "",
    d.parent_phone || "",
    photoLink,
    d.tshirt_size  || "",
  ]);

  // The blank starter "Sheet1" tab Google adds to every new spreadsheet
  // is harmless to leave in place — not auto-deleted here, since that's
  // an easy way to accidentally nuke a tab Shruti was using for notes.

  return ContentService
    .createTextOutput(JSON.stringify({ success: true }))
    .setMimeType(ContentService.MimeType.JSON);
}

/** Run this manually once (Apps Script editor -> select this function -> Run) to test without an HTTP request. Check the "Executions" tab, or View -> Logs, for the result. */
function doPost_test_spy_registration() {
  var fakeEvent = {
    postData: {
      contents: JSON.stringify({
        action:               "spy_agent_registration",
        event_id:             "test-event",
        mission_label:        "Test Agent's 10th Birthday Quest (9th October)",
        submitted_at:         new Date().toISOString(),
        agent_name:           "Test Agent",
        agent_dob:            "2016-05-02",
        parent_name:          "Test Parent",
        parent_phone:         "9999999999",
        agent_photo_b64:      "",
        agent_photo_filename: "",
      })
    }
  };
  var result = doPost(fakeEvent);
  Logger.log(result.getContent());
}
