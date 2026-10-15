"""Instagram leads loaded from the old Google Sheet (2026-10-15, per Shruti):
  1. Sales Lead = "Last Called By" from the sheet (only where the lead has no
     Sales Lead yet - never overwrites one the team has set).
  2. Leads that were "Followup Required" with a follow-up date get that
     follow-up on the Sales platform (a call-log entry: last call date, "Call
     back later", follow-up 11:00 AM on that date, the sheet's remarks) and are
     made visible now, since they are live conversations.
Only touches leads created by the old-leads import (earlier_conversations set).
Safe to run again: the follow-up entry is added once (id "sheet-fu").

    cd backend
    .venv/bin/python scripts/update_old_leads_owner_followup.py "../Lead Management/old_leads_owner_followup.json" [--dry-run]
"""
import asyncio, json, os, sys
import asyncpg
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


async def main(path, dry):
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    data = json.load(open(path, encoding="utf-8"))
    con = await asyncpg.connect(url)
    try:
        rows = await con.fetch(
            """SELECT l.lead_id, RIGHT(regexp_replace(l.phone, '[^0-9]', '', 'g'), 10) AS p,
                      l.event_sales_lead, p.id AS pid, p.call_log
               FROM leads l JOIN lead_sales_playbook p ON p.lead_id = l.lead_id
               WHERE l.lead_origin = 'sales_module' AND l.earlier_conversations IS NOT NULL
                 AND l.lead_source IN ('Instagram', 'Reference', 'Repeat')""")
        by_phone = {}
        for r in rows:
            by_phone.setdefault(r["p"], []).append(r)
        owner, fups = [], []
        for d in data:
            for r in by_phone.get(d["phone"], []):
                if d.get("sales_lead") and not (r["event_sales_lead"] or "").strip():
                    owner.append((d["sales_lead"], r["lead_id"]))
                if d.get("followup"):
                    log = r["call_log"]
                    log = json.loads(log) if isinstance(log, str) else (log or [])
                    if any(e.get("id") == "sheet-fu" for e in log):
                        continue
                    log.append({"id": "sheet-fu", "date": d.get("last_call") or d["followup"], "first_call": False,
                                "disposition": "Call back later", "followup_at": d["followup"] + "T11:00",
                                "remarks": d.get("remarks"), "by": d.get("sales_lead"), "at": None})
                    fups.append((json.dumps(log), r["pid"], r["lead_id"]))
        print(f"Sales Lead to set: {len(owner)} leads - follow-ups to add: {len(fups)} leads")
        if dry:
            return
        async with con.transaction():
            await con.executemany("UPDATE leads SET event_sales_lead = $1 WHERE lead_id = $2", owner)
            await con.executemany("UPDATE lead_sales_playbook SET call_log = $1::jsonb, updated_at = NOW() WHERE id = $2",
                                  [(a, b) for a, b, _ in fups])
            await con.executemany("UPDATE leads SET show_from = LEAST(show_from, CURRENT_DATE) WHERE lead_id = $1",
                                  [(c,) for _, _, c in fups])
        print("Done.")
    finally:
        await con.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if not args:
        sys.exit(__doc__)
    asyncio.run(main(args[0], "--dry-run" in sys.argv))
