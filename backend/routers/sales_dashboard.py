"""Sales Dashboard (2026-10-16, per Shruti) - sales-dashboard.html.

  GET /api/admin/sales-dashboard?month=YYYY-MM&source=...&day=YYYY-MM-DD
      funnel (12 months), lead-source distribution, daily summary per sales
      person, month summary (leads by status with names), sales person x status.
      Admin and sales logins; marketing spend, revenue-based ratios (ROAS,
      ACOS) and spend-based ones (CPL, CAC) are only sent to the admin login.
  GET /api/admin/sales-dashboard/spend?months=12   admin only
  PUT /api/admin/sales-dashboard/spend             admin only

Definitions (one place):
  lead date   COALESCE(lead_generated_at, created_on), IST; next-year leads made
              from a booking (source_booking_id) are not counted as received.
  source      leads.lead_source, else "Sales Team" (portal) / "Website".
  called      a call logged on the portal, or call history from the old sheet,
              or a status other than New.
  converted   became a booking (is_booking) and not cancelled.
  revenue     Sales Quote (client_budget) else order Grand Total.
"""
import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
REPS = ["Mitika", "Sidhant", "Shruti"]
FOUNDERS = {"Shruti", "Sidhant"}
INTERESTED = {"Initial Discussions Done", "Proposal Sent", "Negotiations Ongoing"}


def _rep(name) -> str:
    n = str(name or "").strip()
    for r in REPS:
        if n.lower().startswith(r.lower()):
            return r
    return n or "Unassigned"


def _src(r) -> str:
    s = (r.get("lead_source") or "").strip()
    if s.lower() in ("insta",):
        s = "Instagram"
    return s or ("Sales Team" if r.get("lead_origin") == "sales_module" else "Website")


def _ist_date(dt) -> Optional[date]:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def _log(v) -> list:
    if not v:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return []
    return [e for e in v if isinstance(e, dict)]


def _aware(dt):
    if dt is None or not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _call_dt(e) -> Optional[datetime]:
    """When a logged call was made: its date + time (IST); a call without a
    time uses when it was entered if that was the same day, else 9 AM."""
    ds = str(e.get("date") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ds):
        return None
    t = str(e.get("time") or "")[:5]
    if re.fullmatch(r"\d{2}:\d{2}", t):
        return datetime.fromisoformat(f"{ds}T{t}").replace(tzinfo=IST)
    try:
        at = datetime.fromisoformat(str(e.get("at") or "").replace("Z", "+00:00"))
        if at.astimezone(IST).date().isoformat() == ds:
            return at
    except Exception:
        pass
    return datetime.fromisoformat(f"{ds}T09:00").replace(tzinfo=IST)


def _first_call_dt(log) -> Optional[datetime]:
    ts = [t for t in (_call_dt(e) for e in log) if t]
    return min(ts) if ts else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


NOT_ANSWERED = {"unanswered", "wrong number"}
LOST_STATUSES = {"Not Interested", "DND", "Did not Enquire"}


def _lost_reasons(L) -> list:
    """Why leads didn't book: the not-converted reason on lost leads."""
    cnt: Dict[str, list] = {}
    for d in L:
        if d["converted"] or (d["status"] or "") not in LOST_STATUSES:
            continue
        r = (d.get("non_convert_reason") or "").strip() or "No reason given"
        if r == "Others" and (d.get("non_convert_reason_other") or "").strip():
            r = "Other: " + d["non_convert_reason_other"].strip()[:40]
        cnt.setdefault(r, []).append(d["lead_id"])
    return [{"reason": k, "count": len(v), "ids": v} for k, v in sorted(cnt.items(), key=lambda kv: -len(kv[1]))]


def _ratio(a, b):
    return round(a / b, 2) if b else None


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


async def _load():
    rows = await database.fetch_all(
        """SELECT l.lead_id, l.parent_name, l.phone, l.lead_source, l.lead_origin, l.status, l.is_booking,
                  l.lead_generated_at, l.created_on, l.event_date, l.event_sales_lead, l.client_budget,
                  l.order_grand_total, l.earlier_conversations, l.source_booking_id, l.converted_on,
                  l.non_convert_reason, l.non_convert_reason_other,
                  p.call_log
           FROM leads l LEFT JOIN lead_sales_playbook p ON p.lead_id = l.lead_id"""
    )
    out = []
    for r in rows:
        d = dict(r)
        d["src"] = _src(d)
        d["lead_day"] = _ist_date(d["lead_generated_at"] or d["created_on"])
        d["log"] = _log(d.pop("call_log"))
        conv = d.get("earlier_conversations") or ""
        d["called"] = bool(d["log"]) or bool(re.search(r"Called by|First call|Last call", conv)) \
            or (d["status"] or "New") != "New" or bool(d["is_booking"])
        d["converted"] = bool(d["is_booking"]) and (d["status"] or "") != "Cancelled"
        rev = d["client_budget"] if d["client_budget"] is not None else d["order_grand_total"]
        d["revenue"] = float(rev or 0) if d["converted"] else 0.0
        if d["converted"]:   # 2026-10-28: live Grand Total, same as the booking page / Finance
            from routers.finance import live_grand_total
            d["revenue"] = await live_grand_total(d["lead_id"], d["revenue"])
        d["counted"] = d["source_booking_id"] is None and d["lead_day"] is not None
        d["rep"] = _rep(d["event_sales_lead"])
        # FRT / DRT (2026-10-20, per Shruti): hours from the lead's generated
        # time to its first logged call; days from it to the booking.
        lead_t = _aware(d["lead_generated_at"] or d["created_on"])
        fc = _first_call_dt(d["log"])
        d["first_call_at"] = fc
        d["frt_hours"] = round((fc - lead_t).total_seconds() / 3600, 2) if (fc and lead_t and fc >= lead_t) else None
        conv_t = _aware(d["converted_on"])
        d["drt_days"] = round((conv_t - lead_t).total_seconds() / 86400, 1) if (d["converted"] and conv_t and lead_t and conv_t >= lead_t) else None
        out.append(d)
    return out


def _ym(d: date) -> str:
    return f"{d.year}{d.month:02d}"


def _months_back(n: int, end: date) -> List[str]:
    y, m = end.year, end.month
    res = []
    for _ in range(n):
        res.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(res))


BRAND = "Brand / general"


async def _spend(yms: List[str]) -> Dict[str, Dict[str, float]]:
    """Marketing spend by month and lead source - read from the Finance page's
    marketing costs (finance_costs, category 'mkt'), the single source of truth
    (2026-10-16, per Shruti). A cost with no lead source = Brand / general."""
    rows = await database.fetch_all(
        """SELECT ym, COALESCE(NULLIF(TRIM(lead_source), ''), :b) AS source, SUM(amount) AS amount
           FROM finance_costs WHERE category = 'mkt' AND ym = ANY(:yms) GROUP BY 1, 2""",
        values={"yms": yms, "b": BRAND})
    out: Dict[str, Dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["ym"], {})[r["source"]] = float(r["amount"] or 0)
    return out


def _status_label(d) -> str:
    if d["is_booking"]:
        return "Cancelled booking" if (d["status"] or "") == "Cancelled" else "Converted"
    return d["status"] or "New"


def _outcome(d, last) -> str:
    st = d["status"] or "New"
    if d["converted"]:
        return "Converted"
    if st in ("Not Interested", "DND", "Did not Enquire"):
        return "Not interested"
    if st in INTERESTED:
        return "Interested"
    disp = (last.get("disposition") or "").lower()
    if disp == "unanswered":
        return "Unanswered"
    if disp == "answered":
        return "Answered"
    if disp == "wrong number":
        return "Wrong number"
    if last.get("followup_at"):
        return "Follow-up set"
    return "Other"


OUTCOMES = ["Unanswered", "Answered", "Follow-up set", "Interested", "Converted", "Not interested", "Wrong number", "Other"]


def _daily(leads, day: date, today: date) -> dict:
    ds = day.isoformat()
    reps: Dict[str, dict] = {}

    def R(name):
        return reps.setdefault(name, {"rep": name, "received": 0, "new_called": 0, "existing_called": 0,
                                      "new": {k: 0 for k in OUTCOMES}, "existing": {k: 0 for k in OUTCOMES},
                                      "calls": 0, "fu_due": 0, "fu_done": 0, "fu_missed": 0, "overdue": 0,
                                      "reengage_called": 0, "speed_hours": []})
    for d in leads:
        if d["lead_day"] == day and d["counted"]:
            R(d["rep"])["received"] += 1
        log = sorted(d["log"], key=lambda e: (str(e.get("date") or ""), str(e.get("at") or "")))
        todays = [e for e in log if str(e.get("date") or "")[:10] == ds]
        if todays:
            last = todays[-1]
            rr = R(_rep(last.get("by") or d["event_sales_lead"]))
            rr["calls"] += len(todays)
            is_new = d["lead_day"] == day
            rr["new_called" if is_new else "existing_called"] += 1
            rr["new" if is_new else "existing"][_outcome(d, last)] += 1
            if not is_new and (d["source_booking_id"] or d["earlier_conversations"]):
                rr["reengage_called"] += 1
            if is_new and d["lead_generated_at"] and log and log[0].get("at"):
                try:
                    first = datetime.fromisoformat(str(log[0]["at"]).replace("Z", "+00:00"))
                    lg = d["lead_generated_at"] if d["lead_generated_at"].tzinfo else d["lead_generated_at"].replace(tzinfo=timezone.utc)
                    h = (first - lg).total_seconds() / 3600
                    if h >= 0:
                        rr["speed_hours"].append(h)
                except Exception:
                    pass
        # follow-ups due on this day: still pending at the start of the day
        before = [e for e in log if str(e.get("date") or "")[:10] < ds]
        if before and str(before[-1].get("followup_at") or "")[:10] == ds and not d["is_booking"]:
            rr = R(d["rep"] if d["rep"] != "Unassigned" else _rep(before[-1].get("by")))
            rr["fu_due"] += 1
            if todays:
                rr["fu_done"] += 1
            elif day <= today:
                rr["fu_missed"] += 1
        if day == today and log and not d["is_booking"] and (d["status"] or "New") not in ("Not Interested", "DND", "Did not Enquire"):
            fu = str(log[-1].get("followup_at") or "")[:10]
            if fu and fu < ds:
                R(d["rep"] if d["rep"] != "Unassigned" else _rep(log[-1].get("by")))["overdue"] += 1
    rows = []
    # 2026-10-16, per Shruti — co-founders (Shruti, Sidhant) also talk to and
    # convert customers but have no daily targets: left out of the daily
    # summary (columns AND team total). Every other team member shows.
    for name in [r for r in REPS if r not in FOUNDERS] + sorted(k for k in reps if k not in REPS):
        if name not in reps:
            R(name)
        r = reps[name]
        sh = r.pop("speed_hours")
        r["speed_to_lead_hours"] = round(statistics.median(sh), 1) if sh else None
        rows.append(r)
    total = {"rep": "Team total"}
    for k in ("received", "new_called", "existing_called", "calls", "fu_due", "fu_done", "fu_missed", "overdue", "reengage_called"):
        total[k] = sum(r[k] for r in rows)
    for g in ("new", "existing"):
        total[g] = {k: sum(r[g][k] for r in rows) for k in OUTCOMES}
    total["speed_to_lead_hours"] = None
    return {"day": ds, "outcomes": OUTCOMES, "reps": rows, "total": total}


@router.get("/sales-dashboard")
async def sales_dashboard(month: Optional[str] = None, source: Optional[str] = None, day: Optional[str] = None,
                          x_admin_password: Optional[str] = Header(None)):
    role = _require_admin(x_admin_password)
    is_admin = role == "admin"
    today = datetime.now(IST).date()
    try:
        m_start = date(int(month[:4]), int(month[5:7]), 1) if month else today.replace(day=1)
        the_day = date.fromisoformat(day) if day else today
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM and day YYYY-MM-DD")
    ym = _ym(m_start)
    yms = _months_back(12, m_start)
    leads = await _load()
    spend = await _spend(yms) if is_admin else {}
    src_f = (source or "").strip()

    # 1. funnel, 12 months
    funnel = []
    for k in yms:
        L = [d for d in leads if d["counted"] and _ym(d["lead_day"]) == k and (not src_f or d["src"] == src_f)]
        rec, cal, con = len(L), sum(d["called"] for d in L), sum(d["converted"] for d in L)
        rev = sum(d["revenue"] for d in L)
        row = {"month": f"{k[:4]}-{k[4:]}", "received": rec, "called": cal, "called_pct": _pct(cal, rec),
               "converted": con, "converted_pct": _pct(con, rec), "revenue": rev,
               "avg_drt_days": _avg([d["drt_days"] for d in L]), "avg_frt_hours": _avg([d["frt_hours"] for d in L])}
        if is_admin:
            sp = sum(v for s, v in spend.get(k, {}).items() if not src_f or s == src_f)
            row.update({"spend": sp or None, "cpl": _ratio(sp, rec) if sp else None, "cac": _ratio(sp, con) if sp else None,
                        "roas": _ratio(rev, sp) if sp else None, "acos_pct": _pct(sp, rev) if sp else None})
        funnel.append(row)

    # 2. lead source distribution, selected month
    M = [d for d in leads if d["counted"] and _ym(d["lead_day"]) == ym]
    by_src: Dict[str, list] = {}
    for d in M:
        by_src.setdefault(d["src"], []).append(d)
    for s in spend.get(ym, {}):
        by_src.setdefault(s, [])
    sources = []
    for s, L in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        con = sum(d["converted"] for d in L)
        row = {"source": s, "leads": len(L), "share_pct": _pct(len(L), len(M)), "converted": con,
               "conversion_pct": _pct(con, len(L)), "revenue": sum(d["revenue"] for d in L)}
        if is_admin:
            sp = spend.get(ym, {}).get(s, 0.0)
            row.update({"spend": sp or None, "cpl": _ratio(sp, len(L)) if sp else None, "cac": _ratio(sp, con) if sp else None})
        sources.append(row)

    # 3. month summary (leads of the month by status, with names) and 4. sales person x status
    summary: Dict[str, list] = {}
    matrix: Dict[str, Dict[str, int]] = {}
    for d in M:
        if src_f and d["src"] != src_f:
            continue
        lab = _status_label(d)
        val = d["client_budget"] if d["client_budget"] is not None else d["order_grand_total"]
        summary.setdefault(lab, []).append({"lead_id": d["lead_id"], "name": d["parent_name"], "rep": d["rep"],
                                            "source": d["src"], "value": float(val or 0)})
        matrix.setdefault(d["rep"], {}).setdefault(lab, 0)
        matrix[d["rep"]][lab] += 1
    statuses = sorted({s for v in matrix.values() for s in v}, key=lambda s: (s != "Converted", s))
    rep_rows = []
    for rep, cnt in sorted(matrix.items(), key=lambda kv: (kv[0] not in REPS, kv[0])):
        tot = sum(cnt.values())
        rep_rows.append({"rep": rep, "counts": cnt, "total": tot, "conversion_pct": _pct(cnt.get("Converted", 0), tot)})
    all_sources = sorted({d["src"] for d in leads if d["counted"]})
    return {
        "role": role, "month": m_start.strftime("%Y-%m"), "source": src_f or None, "sources": all_sources,
        "funnel": funnel, "lead_sources": sources,
        "month_summary": [{"status": k, "leads": sorted(v, key=lambda x: -x["value"]),
                           "total_value": sum(x["value"] for x in v)} for k, v in sorted(summary.items(), key=lambda kv: (kv[0] != "Converted", kv[0]))],
        "rep_status": {"statuses": statuses, "rows": rep_rows},
        "lost_reasons": _lost_reasons([d for d in M if not src_f or d["src"] == src_f]),
        "daily": _daily(leads, the_day, today),
    }


@router.get("/sales-dashboard/spend")
async def get_spend(months: int = 12, x_admin_password: Optional[str] = Header(None)):
    """Read-only: marketing spend per month x lead source, from the Finance page."""
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    today = datetime.now(IST).date()
    yms = _months_back(max(1, min(months, 36)), today.replace(day=1))
    sp = await _spend(yms)
    return {"months": [f"{y[:4]}-{y[4:]}" for y in yms],
            "sources": sorted({s for v in sp.values() for s in v}, key=lambda x: (x == BRAND, x)),
            "spend": [{"month": f"{k[:4]}-{k[4:]}", "source": s, "amount": a} for k, v in sp.items() for s, a in v.items()]}


# ─── Sales performance (2026-10-20, per Shruti) — sales-performance.html ─────
# Landing page for the sales login. One person's (or the whole team's) numbers
# for leads whose lead date falls in [from, to]; every number carries the lead
# ids behind it so the page can open exactly those leads in the sales list.
#   received      leads with a lead date in the range
#   called        of those, leads with a call logged (or worked, see _load)
#   in follow-up  open leads whose latest call has a follow-up date
#   converted     became a booking; revenue = its Sales Quote / Grand Total
#   conversion %  converted ÷ received
#   FRT           lead generated time -> first logged call (hours)
#   DRT           lead generated time -> booking (days)
#   answered      calls whose disposition isn't Unanswered / Wrong number
@router.get("/sales-performance")
async def sales_performance(start: Optional[str] = None, end: Optional[str] = None, rep: Optional[str] = None,
                            x_admin_password: Optional[str] = Header(None)):
    role = _require_admin(x_admin_password)
    today = datetime.now(IST).date()
    try:
        d0 = date.fromisoformat(start) if start else today.replace(day=1)
        d1 = date.fromisoformat(end) if end else today
    except Exception:
        raise HTTPException(status_code=400, detail="start / end must be YYYY-MM-DD")
    if d1 < d0:
        d0, d1 = d1, d0
    who = _rep(rep) if (rep or "").strip() else ""
    if role != "admin":
        # The sales login sees only its own numbers (2026-10-20, per Shruti).
        if not who:
            raise HTTPException(status_code=400, detail="Set your name (Editing as) to see your numbers.")
    leads = await _load()
    mine = (lambda d: d["rep"] == who) if who else (lambda d: True)
    L = [d for d in leads if d["counted"] and mine(d) and d["lead_day"] and d0 <= d["lead_day"] <= d1]
    ids = lambda xs: [d["lead_id"] for d in xs]

    def last_call(d):
        lg = sorted(d["log"], key=lambda e: (_call_dt(e) or datetime.min.replace(tzinfo=IST)))
        return lg[-1] if lg else {}

    def is_open(d):
        return not d["is_booking"] and (d["status"] or "New") not in LOST_STATUSES

    called = [d for d in L if d["called"]]
    followup = [d for d in L if is_open(d) and last_call(d).get("followup_at")]
    # Converted = bookings made in the period, whatever the lead date
    # (2026-10-21, per Shruti: Sidhant's #1106, an older lead, converted today
    # didn't show). Conversion rate stays converted ÷ leads received.
    converted = [d for d in leads if d["converted"] and mine(d) and d["source_booking_id"] is None
                 and _ist_date(d["converted_on"]) and d0 <= _ist_date(d["converted_on"]) <= d1]
    answered_leads = [d for d in L if any((e.get("disposition") or "").lower() not in NOT_ANSWERED and e.get("disposition") for e in d["log"])]
    pipeline = [d for d in L if is_open(d) and (d["status"] or "") in INTERESTED and d["client_budget"]]

    # calls made in the range by this person (answer rate)
    calls_made = calls_ans = 0
    for d in leads:
        for e in d["log"]:
            cd = str(e.get("date") or "")[:10]
            if not (d0.isoformat() <= cd <= d1.isoformat()):
                continue
            if who and _rep(e.get("by") or d["event_sales_lead"]) != who:
                continue
            calls_made += 1
            dp = (e.get("disposition") or "").lower()
            if dp and dp not in NOT_ANSWERED:
                calls_ans += 1

    # today's to-do (all of this person's open leads, any lead date)
    ts = today.isoformat()
    open_all = [d for d in leads if mine(d) and is_open(d) and d["counted"]]
    overdue = [d for d in open_all if str(last_call(d).get("followup_at") or "")[:10] and str(last_call(d).get("followup_at"))[:10] < ts]
    due_today = [d for d in open_all if str(last_call(d).get("followup_at") or "")[:10] == ts]
    not_called = [d for d in open_all if not d["called"]]

    rev = sum(d["revenue"] for d in converted)
    summary = {
        "received": {"value": len(L), "ids": ids(L)},
        "called": {"value": len(called), "ids": ids(called), "pct": _pct(len(called), len(L))},
        "followup": {"value": len(followup), "ids": ids(followup)},
        "converted": {"value": len(converted), "ids": ids(converted)},
        "revenue": {"value": rev, "ids": ids(converted), "avg": round(rev / len(converted)) if converted else None},
        "conversion_pct": {"value": _pct(len(converted), len(L)), "ids": ids(converted)},
        "avg_frt_hours": {"value": _avg([d["frt_hours"] for d in L]), "ids": ids([d for d in L if d["frt_hours"] is not None])},
        "avg_drt_days": {"value": _avg([d["drt_days"] for d in converted]), "ids": ids(converted)},
        "pipeline": {"value": sum(float(d["client_budget"] or 0) for d in pipeline), "ids": ids(pipeline)},
        "answer_rate": {"value": _pct(calls_ans, calls_made), "calls": calls_made, "answered": calls_ans},
    }
    funnel = [{"label": "Received", "value": len(L), "ids": ids(L)},
              {"label": "Called", "value": len(called), "ids": ids(called)},
              {"label": "Answered", "value": len(answered_leads), "ids": ids(answered_leads)},
              {"label": "In follow-up", "value": len(followup), "ids": ids(followup)},
              {"label": "Converted", "value": len(converted), "ids": ids(converted)}]

    # day by day: new leads by lead date; calls by the day they were made
    days = []
    day = d1
    while day >= d0 and len(days) < 62:
        ds = day.isoformat()
        new = [d for d in L if d["lead_day"] == day]
        c_ids, a_ids, f_ids = set(), set(), set()
        for d in leads:
            for e in d["log"]:
                if str(e.get("date") or "")[:10] != ds:
                    continue
                if who and _rep(e.get("by") or d["event_sales_lead"]) != who:
                    continue
                c_ids.add(d["lead_id"])
                dp = (e.get("disposition") or "").lower()
                if dp and dp not in NOT_ANSWERED:
                    a_ids.add(d["lead_id"])
                if e.get("followup_at"):
                    f_ids.add(d["lead_id"])
        conv = [d for d in new if d["converted"]]
        days.append({"day": ds, "new": {"value": len(new), "ids": ids(new)},
                     "called": {"value": len(c_ids), "ids": sorted(c_ids)},
                     "answered": {"value": len(a_ids), "ids": sorted(a_ids)},
                     "answer_pct": _pct(len(a_ids), len(c_ids)),
                     "followup": {"value": len(f_ids), "ids": sorted(f_ids)},
                     "converted": {"value": len(conv), "ids": ids(conv)},
                     "conversion_pct": _pct(len(conv), len(new)),
                     "avg_frt_hours": _avg([d["frt_hours"] for d in new])})
        day -= timedelta(days=1)

    by_src: Dict[str, list] = {}
    for d in L:
        by_src.setdefault(d["src"], []).append(d)
    sources = [{"source": k, "leads": len(v), "converted": sum(x["converted"] for x in v), "ids": ids(v)}
               for k, v in sorted(by_src.items(), key=lambda kv: -len(kv[1]))]
    reps = sorted({d["rep"] for d in leads if d["counted"] and d["rep"] != "Unassigned"}, key=lambda r: (r not in REPS, r))
    earnings = await _earnings(leads, who, d0, d1, today) if who else None
    return {"earnings": earnings, "role": role, "rep": who or None, "reps": reps, "start": d0.isoformat(), "end": d1.isoformat(),
            "summary": summary, "funnel": funnel, "days": days, "lost_reasons": _lost_reasons(L), "sources": sources,
            "today": {"overdue": {"value": len(overdue), "ids": ids(overdue)},
                      "due_today": {"value": len(due_today), "ids": ids(due_today)},
                      "not_called": {"value": len(not_called), "ids": ids(not_called)}}}


# ─── Earnings & targets (2026-10-20, per Shruti) ─────────────────────────────
# Sales commission on bookings the person converted (converted_on in the
# range), per event by slab: events 1-5 at 5%, 6-10 at 7.5%, 11+ at 10% of
# the booking value. Plus what they earned volunteering at events (Partners &
# Expenses rows in their name, by bill date or event date in the range).
COMMISSION_SLABS = [(5, 0.05), (10, 0.075), (None, 0.10)]


def _slab_rate(n: int) -> float:
    """Rate for the n-th booking (1-based)."""
    for upto, rate in COMMISSION_SLABS:
        if upto is None or n <= upto:
            return rate
    return COMMISSION_SLABS[-1][1]


async def _earnings(leads, who: str, d0: date, d1: date, today: date) -> dict:
    conv = [d for d in leads if d["converted"] and d["rep"] == who and _ist_date(d["converted_on"])
            and d0 <= _ist_date(d["converted_on"]) <= d1]
    conv.sort(key=lambda d: d["converted_on"])
    lines, total = [], 0.0
    adj = {}
    if conv:
        rows = await database.fetch_all(
            "SELECT lead_id, commission_base, commission_note, commission_set_by FROM leads WHERE lead_id = ANY(:ids)",
            values={"ids": [d["lead_id"] for d in conv]})
        adj = {r["lead_id"]: r for r in rows}
    for i, d in enumerate(conv, 1):
        rate = _slab_rate(i)
        a = adj.get(d["lead_id"])
        base = float(a["commission_base"]) if a and a["commission_base"] is not None else d["revenue"]
        c = round(base * rate, 2)
        total += c
        lines.append({"lead_id": d["lead_id"], "name": d["parent_name"], "value": d["revenue"], "base": base,
                      "adjusted": bool(a and a["commission_base"] is not None),
                      "note": (a["commission_note"] if a else None), "set_by": (a["commission_set_by"] if a else None),
                      "rate_pct": rate * 100, "commission": c})
    n = len(conv)
    avg_val = round(sum(d["revenue"] for d in conv) / n) if n else None
    if not avg_val:
        allv = [d["revenue"] for d in leads if d["converted"] and d["revenue"]]
        avg_val = round(sum(allv) / len(allv)) if allv else 30000
    next_rate = _slab_rate(n + 1)
    nxt_slab = next((upto for upto, _r in COMMISSION_SLABS if upto is not None and n < upto), None)
    # volunteering: Partners & Expenses rows in this person's name
    vol_rows = await database.fetch_all(
        """SELECT t.amount, t.paid, t.paid_via, t.bill_date, l.event_date, t.lead_id, l.parent_name
           FROM event_team t JOIN leads l ON l.lead_id = t.lead_id
           WHERE lower(trim(t.person_name)) LIKE :p""", values={"p": who.lower() + "%"})
    vol = [r for r in vol_rows if (r["bill_date"] or r["event_date"]) and d0 <= (r["bill_date"] or r["event_date"]) <= d1]
    v_total = sum(float(r["amount"] or 0) for r in vol)
    v_paid = sum(float(r["amount"] or 0) for r in vol
                 if r["paid"] or (r["paid_via"] or "").strip().lower() not in ("", "pending"))
    # this month's target (the month of the range's end)
    ym = f"{d1.year}{d1.month:02d}"
    t = await database.fetch_one("SELECT bookings_target, revenue_target FROM sales_targets WHERE rep = :r AND ym = :ym",
                                 values={"r": who, "ym": ym})
    return {
        "bookings": n, "commission": round(total, 2), "lines": lines,
        "slabs": [{"from": 1, "to": 5, "rate_pct": 5}, {"from": 6, "to": 10, "rate_pct": 7.5}, {"from": 11, "to": None, "rate_pct": 10}],
        "next_rate_pct": next_rate * 100, "to_next_slab": (nxt_slab - n + 1) if nxt_slab else None,
        "avg_booking": avg_val, "next_booking_commission": round(avg_val * next_rate),
        "volunteer": {"total": v_total, "paid": v_paid, "pending": round(v_total - v_paid, 2), "events": len(vol)},
        "total_earnings": round(total + v_total, 2),
        "target": {"ym": f"{ym[:4]}-{ym[4:]}", "bookings": t["bookings_target"] if t else None,
                   "revenue": float(t["revenue_target"]) if t and t["revenue_target"] is not None else None},
    }


class CommissionBaseIn(BaseModel):
    lead_id: int
    base: Optional[float] = None        # None = back to the booking value
    note: Optional[str] = None
    changed_by: Optional[str] = None


@router.put("/sales-performance/commission-base")
async def set_commission_base(body: CommissionBaseIn, x_admin_password: Optional[str] = Header(None)):
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Only the admin adjusts commission.")
    if body.base is not None and body.base < 0:
        raise HTTPException(status_code=400, detail="Commission value can't be negative.")
    r = await database.execute(
        """UPDATE leads SET commission_base = :b, commission_note = :n, commission_set_by = :by WHERE lead_id = :id""",
        values={"b": body.base, "n": (body.note or "").strip() or None if body.base is not None else None,
                "by": body.changed_by if body.base is not None else None, "id": body.lead_id})
    return {"success": True}


class TargetIn(BaseModel):
    rep: str
    month: str                      # YYYY-MM
    bookings: Optional[int] = None
    revenue: Optional[float] = None
    changed_by: Optional[str] = None


@router.put("/sales-performance/target")
async def set_target(body: TargetIn, x_admin_password: Optional[str] = Header(None)):
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Only the admin sets targets.")
    if not re.fullmatch(r"\d{4}-\d{2}", body.month or "") or not _rep(body.rep) or _rep(body.rep) == "Unassigned":
        raise HTTPException(status_code=400, detail="Pick a sales person and month.")
    await database.execute(
        """INSERT INTO sales_targets (rep, ym, bookings_target, revenue_target, updated_by, updated_at)
           VALUES (:r, :ym, :b, :v, :by, NOW())
           ON CONFLICT (rep, ym) DO UPDATE SET bookings_target = EXCLUDED.bookings_target,
               revenue_target = EXCLUDED.revenue_target, updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
        values={"r": _rep(body.rep), "ym": body.month.replace("-", ""), "b": body.bookings, "v": body.revenue, "by": body.changed_by})
    return {"success": True}
