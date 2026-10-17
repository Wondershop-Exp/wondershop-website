"""Restore lead statuses the team set that the yearly roll-over overwrote
(2026-10-17 bug: a lead whose event date had passed was flipped back to
"Re-engage later" on every list load). For each lead now "Re-engage later"
whose last status change in the change log is to something else, put that
status back. Lists every change; --dry-run first.

    cd backend
    .venv/bin/python scripts/restore_statuses.py [--dry-run]
"""
import asyncio, os, sys
import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))


async def main(dry):
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await con.fetch(
            """SELECT l.lead_id, l.parent_name, c.new_value, c.changed_by, c.changed_at
               FROM leads l
               JOIN LATERAL (SELECT new_value, changed_by, changed_at FROM booking_change_log
                             WHERE lead_id = l.lead_id AND field_key = 'status'
                             ORDER BY changed_at DESC LIMIT 1) c ON TRUE
               WHERE l.is_booking = FALSE AND l.status = 'Re-engage later'
                 AND c.new_value IS NOT NULL AND c.new_value <> 'Re-engage later' AND c.new_value <> 'Converted'""")
        for r in rows:
            print(f'  #{r["lead_id"]} {r["parent_name"]}: Re-engage later -> {r["new_value"]} (set by {r["changed_by"]} {r["changed_at"]:%d %b %H:%M})')
        print(f"{len(rows)} leads {'would be ' if dry else ''}restored")
        if not dry and rows:
            await con.executemany("UPDATE leads SET status = $2 WHERE lead_id = $1", [(r["lead_id"], r["new_value"]) for r in rows])
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
