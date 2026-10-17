"""Load marketing costs into the Finance page's costs (finance_costs) -
2026-10-17, per Shruti: the Ai-Sensi expense sheet (+ the Rotary Powai stall).
Category Marketing, with date, partner, lead source, payment mode (paid).
Skips a cost that is already there (same month, same amount, same partner) so
anything typed in by hand on the Finance page isn't doubled. Prints each row.

    cd backend
    .venv/bin/python scripts/import_marketing_costs.py "../Lead Management/aisensi_costs.json" [--dry-run]
"""
import asyncio, datetime as D, json, os, sys
import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))


async def main(path, dry):
    rows = json.load(open(path, encoding="utf-8"))
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await con.execute("ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS spent_on DATE")
        await con.execute("ALTER TABLE finance_costs ADD COLUMN IF NOT EXISTS lead_source VARCHAR(100)")
        add = skip = 0
        for r in rows:
            d = D.date.fromisoformat(r["spent_on"])
            ym = d.strftime("%Y%m")
            key = "%sens%" if r["partner"].lower().startswith("ai") else "%rotary%"
            dup = await con.fetchval(
                """SELECT id FROM finance_costs WHERE category = 'mkt' AND ym = $1 AND amount = $2
                     AND (partner ILIKE $3 OR spent_on = $4) LIMIT 1""", ym, r["amount"], key, d)
            tag = "SKIP (already in Finance)" if dup else "add"
            print(f'  {r["spent_on"]}  Rs {r["amount"]:>8,.0f}  {r["partner"]:<18} {r["lead_source"]:<35} {r["paid_via"]:<13} {tag}')
            if dup:
                skip += 1
                continue
            add += 1
            if not dry:
                await con.execute(
                    """INSERT INTO finance_costs (ym, spent_on, category, partner, lead_source, description, amount, paid, paid_via, created_by)
                       VALUES ($1, $2, 'mkt', $3, $4, $5, $6, TRUE, $7, 'Import (Ai-Sensi sheet)')""",
                    ym, d, r["partner"], r["lead_source"], r["description"], r["amount"], r["paid_via"])
        print(f"{add} {'to add' if dry else 'added'}, {skip} skipped as already in Finance")
    finally:
        await con.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], "--dry-run" in sys.argv))
