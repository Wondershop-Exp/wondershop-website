"""Tidy the Sales Lead name on every lead (2026-10-15, per Shruti): variants
like "mitika", "mitika sangoi", "Mitika Sangoi" become "Mitika" - same for
Shruti and Sidhant, matching the Sales Lead dropdown.

    cd backend
    .venv/bin/python scripts/normalize_sales_lead.py [--dry-run]
"""
import asyncio, os, sys
import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
NAMES = ["Mitika", "Shruti", "Sidhant"]


async def main(dry):
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        for n in NAMES:
            rows = await con.fetch(
                "SELECT event_sales_lead AS v, COUNT(*) AS c FROM leads "
                "WHERE TRIM(event_sales_lead) ILIKE $1 AND event_sales_lead <> $2 GROUP BY 1", n + "%", n)
            for r in rows:
                print(f'  "{r["v"]}" -> "{n}"  ({r["c"]} leads)')
            if not dry and rows:
                await con.execute(
                    "UPDATE leads SET event_sales_lead = $2 WHERE TRIM(event_sales_lead) ILIKE $1 AND event_sales_lead <> $2",
                    n + "%", n)
        print("Dry run - nothing changed." if dry else "Done.")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
