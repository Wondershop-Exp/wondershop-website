# One-time cleanup (2026-09-23, per Shruti -- "schedule - replicate same
# style as sales. don't get it as a comment"). The sync code (and the
# backfill you already ran) wrote Event Schedule's Customer's Choice as
# "[Copied from Sales by ...]\n<lines>" -- that's now fixed going forward
# (see routers/admin.py), but any event_schedule_text override already
# written with the old format needs a one-time cleanup so it matches too:
# this moves that bracketed line into Remarks and leaves Customer's Choice
# as just the clean schedule lines, same as sales shows them. Only rows
# still holding the machine-written prefix are touched -- if you've since
# hand-edited one of these in admin, it won't start with that exact
# bracketed text any more and this script leaves it alone.
#
# Run from the backend/ folder:
#   python cleanup_schedule_prefix.py
import asyncio
import re
from database import database

PREFIX_RE = re.compile(r"^(\[Copied from Sales by [^\]]*\])\n(.*)$", re.S)


async def main():
    await database.connect()
    try:
        rows = await database.fetch_all(
            """SELECT id, lead_id, customer_choice_override, remarks
               FROM booking_field_overrides
               WHERE field_key = 'event_schedule_text'
                 AND customer_choice_override LIKE '[Copied from Sales by%'"""
        )
        print(f"Found {len(rows)} event_schedule_text row(s) with the old prefix format.")
        fixed = 0
        for row in rows:
            m = PREFIX_RE.match(row["customer_choice_override"] or "")
            if not m:
                print(f"  Lead #{row['lead_id']}: didn't match expected shape, skipping.")
                continue
            prefix, lines = m.group(1), m.group(2)
            new_remarks = row["remarks"] or f"{prefix} Copied from the Sales panel."
            await database.execute(
                """UPDATE booking_field_overrides
                   SET customer_choice_override = :cco, remarks = :rm
                   WHERE id = :id""",
                values={"cco": lines, "rm": new_remarks, "id": row["id"]},
            )
            print(f"  Lead #{row['lead_id']}: cleaned up.")
            fixed += 1
        print("")
        print(f"Done. {fixed} row(s) fixed.")
    finally:
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
