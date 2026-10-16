"""Reconcile the old Google Sheet against the Sales module (2026-10-16, per
Shruti: "ensure all leads have been migrated"). Read-only - changes nothing.

For every lead row in the sheet (Instagram, Wonderfest, Wonderfest April-March,
Powai Christmas Stall, Google Leads) it reports one result:
  Migrated              - this phone is a lead in the Sales module (lead IDs given)
  Excluded: ...         - left out on purpose (DND, Wrong Number, Did not enquire,
                          Looking for partnership, no / invalid phone)
  MISSING               - should be there but no lead has this phone  <- check these
Writes "../Lead Management/Recon - Google Sheet vs Sales module.csv" (opens in
Excel / Google Sheets) and prints a per-sheet summary.

    cd backend
    .venv/bin/python scripts/recon_google_sheet.py "../Lead Management/recon_sheet_rows.json"
"""
import asyncio, collections, csv, json, os, sys
import asyncpg
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


async def main(path):
    rows = json.load(open(path, encoding="utf-8"))
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        db = await con.fetch(
            """SELECT lead_id, RIGHT(regexp_replace(COALESCE(phone,''), '[^0-9]', '', 'g'), 10) AS p,
                      lead_source, status, is_booking, occasion, lead_origin
               FROM leads""")
    finally:
        await con.close()
    by = collections.defaultdict(list)
    for r in db:
        if r["p"]:
            by[r["p"]].append(r)
    out_path = os.path.join(os.path.dirname(os.path.abspath(path)), "Recon - Google Sheet vs Sales module.csv")
    summ = collections.defaultdict(collections.Counter)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Sheet", "Sheet row", "Name", "Phone (sheet)", "Status in sheet", "Result",
                    "Lead IDs in Sales module", "Lead source now", "Status now"])
        for r in rows:
            hits = by.get(r["phone"] or "", [])
            if r["expected"]:
                res = r["expected"] + (" (but a lead exists)" if hits else "")
            elif hits:
                res = "Migrated"
            else:
                res = "MISSING"
            summ[r["sheet"]][res.split(" (")[0]] += 1
            w.writerow([r["sheet"], r["row"], r["name"], r["phone_raw"], r["sheet_status"], res,
                        ", ".join(str(h["lead_id"]) for h in hits),
                        ", ".join(sorted({h["lead_source"] or "" for h in hits})),
                        ", ".join(sorted({("Booking" if h["is_booking"] else (h["status"] or "")) for h in hits}))])
    for sh, c in summ.items():
        print(f"{sh}: " + " · ".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
