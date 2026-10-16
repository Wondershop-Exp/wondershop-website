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


def _ratio(a, b):
    return round(a / b, 2) if b else None


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


async def _load():
    rows = await database.fetch_all(
        """SELECT l.lead_id, l.parent_name, l.phone, l.lead_source, l.lead_origin, l.status, l.is_booking,
                  l.lead_generated_at, l.created_on, l.event_date, l.event_sales_lead, l.client_budget,
                  l.order_grand_total, l.earlier_conversations, l.source_booking_id, l.converted_on,
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
        d["counted"] = d["source_booking_id"] is None and d["lead_day"] is not None
        d["rep"] = _rep(d["event_sales_lead"])
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
    if disp == "wrong number":
        return "Wrong number"
    if last.get("followup_at"):
        return "Follow-up set"
    return "Other"


OUTCOMES = ["Unanswered", "Follow-up set", "Interested", "Converted", "Not interested", "Wrong number", "Other"]


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
               "converted": con, "converted_pct": _pct(con, rec), "revenue": rev}
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
