# One-time backfill (2026-09-23, per Shruti — "these didn't get updated
# from sales to admin"). _copy_sales_data_to_admin_overrides() only runs
# automatically at the moment a lead converts to a booking (see
# _do_convert_lead() in routers/admin.py) -- every booking that was
# converted BEFORE that code shipped never had it run. The helper is safe
# to re-run: it skips any field that already has an override, so running
# this against every existing booking only fills in gaps, never touches a
# value already saved/edited in admin.
#
# Run from the backend/ folder (same place you run run_migration.py from,
# so it picks up the same .env / DATABASE_URL):
#   python backfill_sales_sync.py
import asyncio
from database import database
from routers.admin import _copy_sales_data_to_admin_overrides


async def main():
    await database.connect()
    try:
        rows = await database.fetch_all(
            "SELECT lead_id FROM leads WHERE is_booking = TRUE ORDER BY lead_id"
        )
        print(f"Found {len(rows)} booking(s) to check.")
        ok, skipped, failed = 0, 0, 0
        for row in rows:
            lead_id = row["lead_id"]
            try:
                before = await database.fetch_all(
                    "SELECT field_key FROM booking_field_overrides WHERE lead_id = :id",
                    values={"id": lead_id},
                )
                before_keys = {r["field_key"] for r in before}

                await _copy_sales_data_to_admin_overrides(lead_id, "Backfill (2026-09-23)")

                after = await database.fetch_all(
                    "SELECT field_key FROM booking_field_overrides WHERE lead_id = :id",
                    values={"id": lead_id},
                )
                after_keys = {r["field_key"] for r in after}
                new_keys = after_keys - before_keys

                if new_keys:
                    print(f"  Lead #{lead_id}: added {sorted(new_keys)}")
                    ok += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                print(f"  Lead #{lead_id}: FAILED -- {e}")

        print("")
        print(f"Done. {ok} booking(s) updated, {skipped} already up to date, {failed} failed.")
    finally:
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
