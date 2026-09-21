"""
One-off: wipe ALL leads and bookings (and everything hanging off them) so the
admin dashboard starts clean after testing.   Written 2026-09-21, per Shruti:
"purge the old test data ... fresh start".

WHAT IT DELETES
  leads (this is BOTH tables in the admin panel - Leads and Bookings - and
  everything the dashboard's lead/booking/revenue numbers are built from), plus
  the rows that belong to them:
    booking_change_log, booking_field_overrides   (admin-panel edits per booking)
    lead_sales_playbook (+ its log)               (sales-team sheets per lead)
    packaging_lists (+ sections/items)            (only lists attached to a lead)
    reward_codes, referral_redemptions, referral_codes
                                                  (scratch-card / refer-and-earn
                                                   codes issued to test customers)
  Lead numbers restart from 1 afterwards.

WHAT IT KEEPS
  vendors, sales-team codes, catalogue/price data, packaging templates,
  packaging lists NOT attached to a lead, monthly targets on the dashboard,
  the Instagram cache, and all site settings.

NOT COVERED (lives outside our database)
  * Visits / landing funnel / builder funnel come from Google Analytics - they are
    hidden on the dashboard by ANALYTICS_START_DATE (backend/config.py), not deleted.
  * The Google Sheet tracker rows written for each booking - clear those by hand.

HOW TO RUN (from the backend folder, same way as run_migration.py):
    python3 scripts/purge_test_data.py              # DRY RUN - only shows counts
    python3 scripts/purge_test_data.py --execute    # asks you to type a phrase, then deletes

It runs as ONE transaction: if anything fails, nothing is deleted.
This cannot be undone - take a Railway Postgres backup first if in any doubt.
"""
import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL is not set (backend/.env) - nothing to do.")
url = url.replace("postgresql+asyncpg://", "postgresql://")
parsed = urlparse(url)

EXECUTE = "--execute" in sys.argv

# Children first, parents last. (label, table, WHERE clause or None for all rows)
STEPS = [
    ("booking edit history",            "booking_change_log",       None),
    ("booking admin-panel overrides",   "booking_field_overrides",  None),
    ("sales playbook log",              "lead_sales_playbook_log",  None),
    ("sales playbook sheets",           "lead_sales_playbook",      None),
    ("packaging items",                 "packaging_items",
        "section_id IN (SELECT s.id FROM packaging_sections s JOIN packaging_lists l "
        "ON l.id = s.packaging_list_id WHERE l.lead_id IS NOT NULL)"),
    ("packaging sections",              "packaging_sections",
        "packaging_list_id IN (SELECT id FROM packaging_lists WHERE lead_id IS NOT NULL)"),
    ("packaging lists (attached to a lead)", "packaging_lists",     "lead_id IS NOT NULL"),
    ("referral redemptions",            "referral_redemptions",     None),
    ("referral codes",                  "referral_codes",           None),
    ("reward codes",                    "reward_codes",             None),
    ("LEADS + BOOKINGS",                "leads",                    None),
]

conn = psycopg2.connect(url)
conn.autocommit = False
cur = conn.cursor()


def exists(table):
    cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    return cur.fetchone()[0] is not None


def count(table, where):
    cur.execute(f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else ""))
    return cur.fetchone()[0]


print(f"\nDatabase : {parsed.hostname}:{parsed.port}/{(parsed.path or '').lstrip('/')}")
print("Mode     : " + ("EXECUTE (will delete)" if EXECUTE else "dry run (nothing is changed)") + "\n")

plan = []
for label, table, where in STEPS:
    if not exists(table):
        print(f"  {label:<40} (table not present - skipped)")
        continue
    n = count(table, where)
    plan.append((label, table, where, n))
    print(f"  {label:<40} {n:>7} row(s)")

cur.execute("SELECT MIN(created_on), MAX(created_on), COUNT(*) FILTER (WHERE is_booking) FROM leads")
first, last, bookings = cur.fetchone()
print(f"\n  leads created between {first} and {last}; {bookings} of them are confirmed bookings.\n")

if not EXECUTE:
    print("Dry run only. Re-run with --execute to delete.\n")
    conn.close()
    sys.exit(0)

phrase = "DELETE ALL LEADS"
if input(f"This permanently deletes the rows above from {parsed.hostname}.\nType {phrase} to continue: ").strip() != phrase:
    print("Cancelled - nothing deleted.")
    conn.close()
    sys.exit(1)

try:
    for label, table, where, n in plan:
        if n:
            cur.execute(f"DELETE FROM {table}" + (f" WHERE {where}" if where else ""))
            print(f"  deleted {cur.rowcount:>6}  {label}")
    cur.execute("ALTER TABLE leads ALTER COLUMN lead_id RESTART WITH 1")
    conn.commit()
    print("\nDone. Lead numbers will start again from 1.\n")
except Exception:
    conn.rollback()
    print("\nFAILED - rolled back, nothing was deleted.\n")
    raise
finally:
    conn.close()
