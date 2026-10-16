"""One-time (2026-10-16, per Shruti): old leads from the Google Sheet import
that the team had already spoken to (any call recorded, or a status other
than New - Not Interested, Unanswered, Converted ...) move from "New" to
"Re-engage later". Leads never contacted stay New; the live "Followup
Required" ones (they carry the sheet's follow-up) are left alone; anything
the team has already changed (status no longer New) is left alone.
Run after the code with migration 064 is live (the status must be allowed).

    cd backend
    .venv/bin/python scripts/set_reengage_later.py [--dry-run]
"""
import asyncio, os, sys
import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

WHERE = """
  l.lead_origin = 'sales_module' AND l.is_booking = FALSE AND l.status = 'New'
  AND l.earlier_conversations IS NOT NULL
  AND (l.earlier_conversations ~ 'Called by|First call|Last call'
       OR l.earlier_conversations ~ 'Status then: (Not Interested|Unanswered|Converted|Others)')
  AND NOT EXISTS (SELECT 1 FROM lead_sales_playbook p, jsonb_array_elements(COALESCE(p.call_log, '[]'::jsonb)) e
                  WHERE p.lead_id = l.lead_id AND e->>'id' = 'sheet-fu')
"""


async def main(dry):
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        n = await con.fetchval(f"SELECT COUNT(*) FROM leads l WHERE {WHERE}")
        left = await con.fetchval("""SELECT COUNT(*) FROM leads l WHERE l.lead_origin='sales_module' AND l.status='New'
                                      AND l.earlier_conversations IS NOT NULL""")
        print(f"{n} leads -> Re-engage later; {left - n} imported leads stay New")
        if not dry:
            await con.execute(f"UPDATE leads l SET status = 'Re-engage later' WHERE {WHERE}")
            print("Done.")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
