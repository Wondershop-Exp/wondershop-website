"""
One-off (but re-runnable) loader for vendor_master, from a cleaned CSV
matching vendor_master's columns exactly (see clean_vendors.py — the
source-Excel-to-CSV step — which is not part of this repo, run separately
whenever there's a fresh export to bring in).

Usage:
    cd backend
    .venv/bin/python scripts/import_vendor_master.py ../vendor_master_clean.csv

Safety: refuses to run if vendor_master already has rows, unless --force is
passed — this is meant for the initial bulk load. Once the admin panel's
Vendors tab is live and staff start editing/adding vendors there, re-running
this would blindly duplicate everyone against the rows already in the table.
For a fresh sheet export later on, re-clean it and import into a scratch
table / review manually rather than re-running this against a live table.
"""
import csv
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

COLUMNS = [
    "name", "primary_contact_name", "primary_mobile", "alternate_mobile",
    "whatsapp_number", "email", "deals_in", "address", "city", "pincode",
    "timings", "website", "remarks", "is_active",
]


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if not args:
        print("Usage: python import_vendor_master.py <path-to-clean.csv> [--force]")
        sys.exit(1)
    csv_path = args[0]

    url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM vendor_master")
    existing = cur.fetchone()[0]
    if existing and not force:
        print(f"vendor_master already has {existing} row(s) — refusing to run again "
              f"without --force (see the safety note at the top of this script).")
        conn.close()
        sys.exit(1)

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    placeholders = ", ".join(["%s"] * len(COLUMNS))
    col_list = ", ".join(COLUMNS)
    insert_sql = f"INSERT INTO vendor_master ({col_list}) VALUES ({placeholders})"

    inserted = 0
    for row in rows:
        values = []
        for col in COLUMNS:
            v = row.get(col, "")
            if col == "is_active":
                values.append(v.strip().lower() == "true")
            elif v == "":
                values.append(None)
            else:
                values.append(v)
        cur.execute(insert_sql, values)
        inserted += 1

    conn.commit()
    print(f"✅ Inserted {inserted} vendor(s) into vendor_master.")
    conn.close()


if __name__ == "__main__":
    main()
