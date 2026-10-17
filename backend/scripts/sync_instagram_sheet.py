"""Sync the Instagram tab of the Google Sheet into the Sales module
(2026-10-17, per Shruti - "WSE Birthday Leads 20261017.xlsx"). For every sheet
row (DND / Wrong Number / Did not enquire / partnership left out) whose phone
is a lead in the Sales module:

  1. Sales Lead = "Last Called By" (Mitika / Sidhant / Shruti).
  2. Lead source = Instagram.
  3/4. Call log: the First Call and the Last Called On dates become call
     entries (by the Last Called By person, sheet remarks on the latest one,
     disposition from the sheet status). A date that already has a call in the
     log is not added twice; the old "sheet-fu" entry (11 AM) is replaced.
  5. Follow Up Date -> follow-up 9:00 AM on the latest call, for leads that
     are still open (Followup Required / Unanswered / New).
  Status: Followup Required -> "Initial Discussions Done"; Unanswered / New ->
     "New" - only when the lead is still New or Re-engage later on the portal.
  Fields filled only where empty on the portal: child's gender, venue, venue
     type, kids count, theme; event date = the sheet's Event Date when it is
     still in the future.
Phones in the sheet but not yet in the Sales module are created as new
Instagram leads. Bookings are never touched. Safe to run again.

    cd backend
    .venv/bin/python scripts/sync_instagram_sheet.py "../Lead Management/instagram_sync.json" [--dry-run]
"""
import asyncio, collections, datetime as D, json, os, sys
import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
IST = D.timezone(D.timedelta(hours=5, minutes=30))
DISP = {"Unanswered": "Unanswered", "Followup Required": "Follow-up required"}
OPEN = {"Followup Required", "Unanswered", "New"}


def build_log(log, r):
    log = [e for e in (log or []) if e.get("id") != "sheet-fu"]
    dates = {str(e.get("date") or "")[:10] for e in log}
    by = r["by"] if r["by"] in ("Mitika", "Sidhant", "Shruti") else (r["by"] or None)
    for key, d, first in (("sheet-first", r["first_call"], True), ("sheet-last", r["last_call"], False)):
        if not d or any(e.get("id") == key for e in log):
            continue
        if d in dates:
            continue
        if key == "sheet-last" and d == r["first_call"]:
            continue
        log.append({"id": key, "date": d, "first_call": first, "disposition": None, "followup_at": None,
                    "remarks": "From Google Sheet", "by": by, "at": None})
        dates.add(d)
    log.sort(key=lambda e: (str(e.get("date") or ""), str(e.get("at") or "")))
    if log and (r["remarks"] or r["followup"]):
        last = log[-1]
        if str(last.get("id", "")).startswith("sheet-"):
            if r["remarks"]:
                last["remarks"] = "From Google Sheet: " + r["remarks"]
            last["disposition"] = last.get("disposition") or DISP.get(r["status"])
        if r["followup"] and r["status"] in OPEN and not last.get("followup_at"):
            last["followup_at"] = r["followup"] + "T09:00"
    return log


async def main(path, dry):
    rows = json.load(open(path, encoding="utf-8"))
    con = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    stats = collections.Counter()
    try:
        db = await con.fetch(
            """SELECT l.lead_id, RIGHT(regexp_replace(COALESCE(l.phone,''), '[^0-9]', '', 'g'), 10) AS p, l.status,
                      l.lead_source, l.event_sales_lead, l.child_genders, l.venue, l.kids_count, l.theme, l.event_date,
                      l.earlier_conversations, l.created_on, p.id AS pid, p.call_log, p.venue_type
               FROM leads l JOIN lead_sales_playbook p ON p.lead_id = l.lead_id
               WHERE l.lead_origin = 'sales_module' AND l.is_booking = FALSE
                 AND COALESCE(l.occasion, 'Birthday') = 'Birthday'""")
        by = collections.defaultdict(list)
        for d in db:
            by[d["p"]].append(d)
        today = D.datetime.now(IST).date()
        async with con.transaction():
            for r in rows:
                leads = by.get(r["phone"])
                if not leads:
                    stats["new lead created"] += 1
                    print(f'  NEW  {r["phone"]} {r["name"]} ({r["status"]})')
                    if dry:
                        continue
                    ld = D.datetime.combine(D.date.fromisoformat(r["lead_date"]), D.time(), tzinfo=IST) if r["lead_date"] else None
                    lid = await con.fetchval(
                        """INSERT INTO leads (parent_name, phone, child_genders, venue, kids_count, theme, event_date, lead_origin,
                                              lead_source, status, is_booking, event_sales_lead, lead_generated_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,'sales_module','Instagram',$8,FALSE,$9,$10) RETURNING lead_id""",
                        r["name"] or "(confirm)", r["phone"], r["gender"], r["venue"], r["kids"], r["theme"],
                        D.date.fromisoformat(r["event_date"]) if r["event_date"] and r["event_date"] >= today.isoformat() else None,
                        "Initial Discussions Done" if r["status"] == "Followup Required" else "New", r["by"], ld)
                    await con.execute(
                        "INSERT INTO lead_sales_playbook (lead_id, requirements, created_by, call_log, venue_type) VALUES ($1, '{}', 'Sheet sync', $2::jsonb, $3)",
                        lid, json.dumps(build_log([], r)), r["venue_type"])
                    continue
                # the team's own portal lead first, else the imported one
                tgt = sorted(leads, key=lambda d: (d["earlier_conversations"] is not None, d["created_on"]))[0]
                for d in leads:
                    sets, vals = [], []
                    def S(col, v):
                        sets.append(f"{col} = ${len(vals) + 2}"); vals.append(v)
                    if r["by"] in ("Mitika", "Sidhant", "Shruti") and (d["event_sales_lead"] or "") != r["by"]:
                        S("event_sales_lead", r["by"]); stats["sales lead set"] += 1
                    if (d["lead_source"] or "") != "Instagram":
                        S("lead_source", "Instagram"); stats["lead source -> Instagram"] += 1
                    if d is tgt:
                        if r["gender"] and not d["child_genders"]:
                            S("child_genders", r["gender"]); stats["gender filled"] += 1
                        if r["venue"] and not d["venue"]:
                            S("venue", r["venue"]); stats["venue filled"] += 1
                        if r["kids"] and not d["kids_count"]:
                            S("kids_count", r["kids"]); stats["kids filled"] += 1
                        if r["theme"] and not d["theme"]:
                            S("theme", r["theme"]); stats["theme filled"] += 1
                        if r["event_date"] and r["event_date"] >= today.isoformat() and str(d["event_date"] or "") != r["event_date"]:
                            S("event_date", D.date.fromisoformat(r["event_date"])); stats["event date set"] += 1
                        if d["status"] in ("New", "Re-engage later") and r["status"] in OPEN:
                            ns = "Initial Discussions Done" if r["status"] == "Followup Required" else "New"
                            if ns != d["status"]:
                                S("status", ns); stats[f"status -> {ns}"] += 1
                    if sets and not dry:
                        await con.execute(f"UPDATE leads SET {', '.join(sets)} WHERE lead_id = $1", d["lead_id"], *vals)
                    if d is tgt:
                        old = d["call_log"]
                        old = json.loads(old) if isinstance(old, str) else (old or [])
                        new = build_log([dict(e) for e in old], r)
                        if new != old:
                            stats["call log updated"] += 1
                            if any(e.get("followup_at", "") and str(e.get("followup_at")).endswith("T09:00") for e in new[-1:]):
                                stats["follow-up set (9 AM)"] += 1
                            if not dry:
                                await con.execute("UPDATE lead_sales_playbook SET call_log = $2::jsonb, updated_at = NOW() WHERE id = $1",
                                                  d["pid"], json.dumps(new))
                        if r["venue_type"] and not d["venue_type"]:
                            stats["venue type filled"] += 1
                            if not dry:
                                await con.execute("UPDATE lead_sales_playbook SET venue_type = $2 WHERE id = $1", d["pid"], r["venue_type"])
        for k, v in stats.most_common():
            print(f"{k}: {v}")
        print("Dry run - nothing changed." if dry else "Done.")
    finally:
        await con.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], "--dry-run" in sys.argv))
