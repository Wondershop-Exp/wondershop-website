"""One-time load of old / existing leads straight into the database
(2026-10-15, per Shruti). Same rules as POST /api/admin/old-leads/import:
anyone whose phone is already in the Sales module is skipped, and running it
again skips what it already loaded.

Customer data is NOT in this repo (it is public) - pass the JSON file:
    cd backend
    .venv/bin/python scripts/import_old_leads.py "../Lead Management/old_leads.json"
Add --dry-run to only count what would be created.
"""
import asyncio, datetime as D, json, os, re, sys
import asyncpg
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

SCHEMA = """
ALTER TABLE leads ADD COLUMN IF NOT EXISTS show_from DATE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS hidden_from_team BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS occasion VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_highlights VARCHAR(200);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS earlier_conversations TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS date_precision VARCHAR(10);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_generated_at TIMESTAMPTZ;
"""


async def main(path, dry):
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    leads = json.load(open(path, encoding="utf-8"))
    con = await asyncpg.connect(url)
    try:
        if not dry:
            await con.execute(SCHEMA)
        rows = await con.fetch(
            "SELECT DISTINCT RIGHT(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), 10) AS p "
            "FROM leads WHERE lead_origin = 'sales_module'")
        existing = {r["p"] for r in rows if r["p"]}
        created, skipped = 0, set()
        todo = []
        for l in leads:
            ph = re.sub(r"[^0-9]", "", l["phone"] or "")[-10:]
            if ph in existing:
                skipped.add(ph)
                continue
            todo.append((ph, l))
        print(f"{len(leads)} in file - {len(todo)} to create - {len(skipped)} phone numbers already in the Sales module (skipped)")
        if dry:
            return
        async with con.transaction():
            for ph, l in todo:
                d = lambda k: D.date.fromisoformat(l[k]) if l.get(k) else None
                ld = d("lead_date")
                lead_id = await con.fetchval(
                    """INSERT INTO leads
                         (parent_name, phone, child_names, child_ages, child_genders, event_date, theme, lead_origin,
                          lead_source, status, is_booking, show_from, hidden_from_team, occasion, lead_highlights,
                          earlier_conversations, date_precision, lead_generated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,'sales_module',$8,'New',FALSE,$9,FALSE,$10,$11,$12,$13,$14)
                       RETURNING lead_id""",
                    (l.get("parent_name") or "").strip() or "(confirm)", ph, l.get("child_names"), l.get("child_ages"),
                    l.get("child_genders"), d("event_date"), None if l["occasion"] == "Birthday" else l["occasion"],
                    l.get("lead_source"), d("show_from"), l["occasion"], l.get("lead_highlights"),
                    l.get("earlier_conversations"), l.get("date_precision") or "exact",
                    D.datetime.combine(ld, D.time(), tzinfo=D.timezone(D.timedelta(hours=5, minutes=30))) if ld else None,
                )
                pid = await con.fetchval(
                    "INSERT INTO lead_sales_playbook (lead_id, requirements, created_by) VALUES ($1, '{}', $2) RETURNING id",
                    lead_id, "Shruti Admin")
                await con.execute(
                    "INSERT INTO lead_sales_playbook_log (playbook_id, actor, action, detail) VALUES ($1, $2, 'created', 'Old leads import')",
                    pid, "Shruti Admin")
                created += 1
        print(f"Created {created} leads.")
    finally:
        await con.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if not args:
        sys.exit(__doc__)
    asyncio.run(main(args[0], "--dry-run" in sys.argv))
