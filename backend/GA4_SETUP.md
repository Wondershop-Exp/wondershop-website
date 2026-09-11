# GA4 setup for the admin dashboard

The admin dashboard's "Traffic & Builder Funnel" card reads live data from
Google Analytics 4 via the GA4 Data API. It's entirely optional — leave it
unconfigured and that card just shows "Not connected yet" while the rest of
the dashboard (bookings, revenue, AOV, conversion) works normally.

This is a one-time setup, done entirely in the Google Cloud / Analytics
consoles and Railway's dashboard. **Nothing here should ever be pasted into
a chat with Claude** — the service account key is a credential, and it goes
straight from Google into Railway's environment variables.

## What you're setting up

Two environment variables on the Railway backend service:

- `GA4_PROPERTY_ID` — the numeric ID of your GA4 property (not the
  Measurement ID `G-KG6H6WL7QQ` you already have in the site's `<head>` —
  a different, numeric ID).
- `GA4_SERVICE_ACCOUNT_JSON` — the full contents of a Google Cloud service
  account key file, pasted as one JSON blob.

## 1. Create a Google Cloud project (or reuse one)

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. If you don't already have a project for Wondershop, create one (top-left
   project picker → "New Project"). Any name is fine, e.g. "Wondershop
   Analytics".

## 2. Enable the Google Analytics Data API

1. In that project, go to **APIs & Services → Library**.
2. Search for **"Google Analytics Data API"** and click **Enable**.

## 3. Create a service account

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → Service account**.
3. Give it a name, e.g. `wondershop-dashboard-reader`. No roles need to be
   granted at the Google Cloud project level — access is granted inside
   GA4 itself in the next step.
4. Click **Done**.
5. Open the service account you just created, go to the **Keys** tab →
   **Add Key → Create new key → JSON**. This downloads a `.json` file to
   your computer.
6. Note the `client_email` field inside that file (something like
   `wondershop-dashboard-reader@your-project.iam.gserviceaccount.com`) —
   you need it for the next step.

Treat this JSON file like a password: don't email it, don't paste it into
any chat (including this one), don't commit it to git.

## 4. Grant that service account access in GA4

1. Go to [analytics.google.com](https://analytics.google.com/) and open the
   Wondershop GA4 property.
2. **Admin** (gear icon, bottom-left) → under the **Property** column →
   **Property Access Management**.
3. Click the blue **+** → **Add users**.
4. Paste the service account's `client_email` from step 3.6.
5. Give it the **Viewer** role. Click **Add**.

## 5. Find your GA4 Property ID

Still in **Admin → Property Details** (or the property picker at the very
top), you'll see **Property ID** — a plain number like `123456789`. That's
`GA4_PROPERTY_ID`. (This is different from the Measurement ID `G-...` used
in the tracking snippet.)

## 6. Register `step_name` / `step_number` as custom dimensions

This step unlocks the per-step "where builder users drop off" table. Without
it, the dashboard still shows total builder starts/checkouts/bookings/leads
— just not the per-step breakdown.

1. **Admin → Data display → Custom definitions → Custom dimensions**.
2. Click **Create custom dimension**.
   - Dimension name: `step_name`
   - Scope: **Event**
   - Event parameter: `step_name`
   - Click **Save**.
3. Repeat for a second one:
   - Dimension name: `step_number`
   - Scope: **Event**
   - Event parameter: `step_number`
   - Click **Save**.

**Important:** this only affects data collected *after* you register it —
GA4 does not backfill custom dimensions onto historical events. So the
per-step table will be empty for a day or two after you do this, then fill
in as new `builder_step_view` events come in. That's expected, not a bug —
the dashboard shows a note explaining this until the data appears.

## 7. Set the two environment variables on Railway

1. Open the Railway project → the backend service → **Variables** tab.
2. Add:
   - `GA4_PROPERTY_ID` = the numeric ID from step 5.
   - `GA4_SERVICE_ACCOUNT_JSON` = the **entire contents** of the JSON key
     file from step 3.5, pasted as-is (it's valid JSON, Railway stores it
     as a single multi-line string — no need to escape or minify it).
3. Save. Railway will redeploy the backend automatically.

Once both variables are set, reload the admin dashboard's Dashboard tab —
the GA4 card should switch from "Not connected yet" to showing live traffic
and funnel numbers within a few seconds (no code changes or redeploy needed
beyond the env vars themselves).

## Troubleshooting

- **Card shows "GA4 is configured but the last fetch failed: ..."** — almost
  always either (a) the service account wasn't actually granted Viewer
  access on the right GA4 property (step 4), or (b) `GA4_PROPERTY_ID` is
  wrong (double-check it's the numeric Property ID, not the `G-...`
  Measurement ID). The error message from Google is shown directly on the
  card to help narrow it down.
- **Totals show up but the per-step drop-off table doesn't** — the
  `step_name`/`step_number` custom dimensions (step 6) either aren't
  registered yet, or were registered too recently for data to exist. Give
  it a day.
- **Nothing changes after setting the Railway variables** — confirm the
  backend service actually redeployed (Railway does this automatically on
  variable changes, but check the Deployments tab), then hard-refresh the
  admin page.
