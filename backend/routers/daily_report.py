"""
Daily business update on Slack (2026-10-20, per Shruti).

Posts once a day (DAILY_REPORT_TIME, IST, default 21:00) to SLACK_REPORT_CHANNEL
using the existing Wondershop Slack bot (SLACK_BOT_TOKEN, see slack_leads.py).
The bot must be invited to that channel (/invite @<bot> in Slack).

  GET  /api/admin/daily-report          preview the message (admin only)
  POST /api/admin/daily-report/send     post it now (admin only)

Definitions - same as the Sales Dashboard (routers/sales_dashboard.py) and the
monthly admin dashboard (routers/dashboard.py), so the numbers agree:
  Today, new leads   leads received today (IST), excluding WSR Repeat.
  Called             a call logged today on the portal.
  Warm               status Initial Discussions Done / Proposal Sent / Negotiations Ongoing.
  Converted          became a booking (not cancelled).
  Not converted      Not Interested / DND / Did not Enquire.
  Repeat leads       lead_source = 'WSR Repeat' with a call logged today.
  Realized revenue   event already happened AND payment amount + mode confirmed.
  Booked revenue     every other confirmed booking in the month.
  Potential revenue  warm leads whose event date is in the window, at their budget.
  Revenue            Sales Quote (client_budget) else order Grand Total.
"""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from config import settings
from database import database
from routers.admin import _require_admin
from routers.sales_dashboard import _load, IST, INTERESTED
from routers.slack_leads import slack_api

router = APIRouter()
logger = logging.getLogger(__name__)

REPEAT = "WSR Repeat"
LOST = {"Not Interested", "DND", "Did not Enquire"}


def _inr(v) -> str:
    v = round(float(v or 0))
    s = str(abs(v))
    if len(s) > 3:   # Indian grouping: 12,34,567
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-₹" if v < 0 else "₹") + s


def _pct(a, b) -> str:
    return f"{round(100 * a / b)}%" if b else "–"


async def _bookings(start: date, end: date):
    """Non-cancelled bookings with event_date in [start, end)."""
    return await database.fetch_all(
        """SELECT l.lead_id, l.event_date, l.parent_name, l.child_names, l.theme, l.venue, l.event_sales_lead,
                  COALESCE(l.client_budget, l.order_grand_total, 0) AS revenue,
                  amt.customer_choice_override AS pay_amt, mode.customer_choice_override AS pay_mode
           FROM leads l
           LEFT JOIN booking_field_overrides amt ON amt.lead_id = l.lead_id AND amt.field_key = 'event_payment_confirmed_amount'
           LEFT JOIN booking_field_overrides mode ON mode.lead_id = l.lead_id AND mode.field_key = 'event_payment_confirmed_mode'
           WHERE l.is_booking = TRUE AND l.status != 'Cancelled' AND l.event_date >= :s AND l.event_date < :e
           ORDER BY l.event_date, l.lead_id""",
        values={"s": start, "e": end})


async def _warm(start: date, end: date):
    r = await database.fetch_one(
        """SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(client_budget, order_grand_total, 0)), 0) AS rev
           FROM leads WHERE is_booking = FALSE AND status = ANY(:st) AND COALESCE(hidden_from_team, FALSE) = FALSE
             AND event_date >= :s AND event_date < :e""",
        values={"st": list(INTERESTED), "s": start, "e": end})
    return int(r["n"] or 0), float(r["rev"] or 0)


async def build_report(today: Optional[date] = None) -> str:
    today = today or datetime.now(IST).date()
    ds = today.isoformat()
    leads = await _load()

    def called_today(d):
        return any(str(e.get("date") or "")[:10] == ds for e in d["log"])

    def bucket(L):
        warm = sum(1 for d in L if not d["converted"] and (d["status"] or "") in INTERESTED)
        conv = sum(1 for d in L if d["converted"])
        lost = sum(1 for d in L if not d["converted"] and (d["status"] or "") in LOST)
        return warm, conv, lost

    new = [d for d in leads if d["counted"] and d["lead_day"] == today and d["src"] != REPEAT]
    new_called = [d for d in new if called_today(d) or d["called"]]
    worked = [d for d in leads if d["src"] != REPEAT and called_today(d)]
    w_warm, w_conv, w_lost = bucket(worked)
    rep = [d for d in leads if d["src"] == REPEAT and called_today(d)]
    r_warm, r_conv, _ = bucket(rep)

    # Month
    m_start = today.replace(day=1)
    m_end = (m_start + timedelta(days=32)).replace(day=1)
    mb = await _bookings(m_start, m_end)
    realized = sum(float(b["revenue"] or 0) for b in mb if b["event_date"] < today and b["pay_amt"] and b["pay_mode"])
    total = sum(float(b["revenue"] or 0) for b in mb)
    m_warm_n, m_warm_rev = await _warm(m_start, m_end)

    # Next 30 days
    n30 = await _bookings(today, today + timedelta(days=30))
    n30_warm_n, n30_warm_rev = await _warm(today, today + timedelta(days=30))
    # Next 2 weeks list
    n14 = [b for b in n30 if b["event_date"] < today + timedelta(days=14)]

    mon = today.strftime("%B")
    L = [f"*Wondershop daily update — {today.strftime('%a %d %b %Y')}*", "",
         "*Today*",
         f"• New leads received: *{len(new)}*  (called {len(new_called)} · {_pct(len(new_called), len(new))})",
         f"• Leads called today: *{len(worked)}*  → warm {w_warm} · converted {w_conv} · not converted {w_lost}",
         f"• Repeat (WSR) leads called: *{len(rep)}*  → warm {r_warm} · converted {r_conv} ({_pct(r_conv, len(rep))})",
         "",
         f"*{mon} so far*",
         f"• Total revenue: *{_inr(total)}*  (realized {_inr(realized)} · booked {_inr(total - realized)})",
         f"• Potential (warm leads): {_inr(m_warm_rev)} from {m_warm_n} leads",
         f"• Confirmed parties this month: *{len(mb)}*",
         "",
         "*Next 30 days*",
         f"• Confirmed parties: *{len(n30)}* · confirmed revenue {_inr(sum(float(b['revenue'] or 0) for b in n30))}",
         f"• Warm leads: *{n30_warm_n}* · potential revenue {_inr(n30_warm_rev)}",
         "",
         f"*Upcoming events — next 2 weeks ({len(n14)})*"]
    if not n14:
        L.append("• None booked yet")
    for b in n14:
        who = (b["child_names"] or "").strip() or (b["parent_name"] or "").strip() or f"#{b['lead_id']}"
        bits = [x for x in [(b["theme"] or "").strip(), (b["venue"] or "").strip()] if x]
        L.append(f"• {b['event_date'].strftime('%a %d %b')} — {who}"
                 + (f" ({b['parent_name']})" if b["child_names"] and b["parent_name"] else "")
                 + (f" · {' · '.join(bits)}" if bits else "")
                 + f" · {_inr(b['revenue'])}"
                 + (f" · {b['event_sales_lead']}" if b["event_sales_lead"] else ""))
    return "\n".join(L)


async def send_report(today: Optional[date] = None) -> dict:
    if not (settings.SLACK_BOT_TOKEN and settings.SLACK_REPORT_CHANNEL):
        raise HTTPException(status_code=503, detail="Set SLACK_BOT_TOKEN and SLACK_REPORT_CHANNEL on Railway first.")
    text = await build_report(today)
    d = await slack_api("chat.postMessage", channel=settings.SLACK_REPORT_CHANNEL, text=text, unfurl_links=False, mrkdwn=True)
    if not d.get("ok"):
        raise HTTPException(status_code=502, detail=f"Slack said: {d.get('error')}")
    return {"ok": True}


def _admin_only(pw):
    if _require_admin(pw) != "admin":
        raise HTTPException(status_code=403, detail="Admin login only.")


@router.get("/daily-report")
async def preview(day: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    _admin_only(x_admin_password)
    return {"text": await build_report(date.fromisoformat(day) if day else None)}


@router.post("/daily-report/send")
async def send_now(day: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    """Post now; ?day=YYYY-MM-DD posts the summary for that day (e.g. yesterday, to check)."""
    _admin_only(x_admin_password)
    return await send_report(date.fromisoformat(day) if day else None)


async def scheduler():
    """Background loop started from main.py. Posts once per IST day at
    DAILY_REPORT_TIME; app_flags stops a second post after a restart."""
    while True:
        try:
            if settings.SLACK_BOT_TOKEN and settings.SLACK_REPORT_CHANNEL:
                now = datetime.now(IST)
                hh, mm = (settings.DAILY_REPORT_TIME or "21:00").split(":")
                due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                flag = f"daily_report_{now.date().isoformat()}"
                if now >= due and not await database.fetch_one("SELECT key FROM app_flags WHERE key = :k", values={"k": flag}):
                    await database.execute("INSERT INTO app_flags (key) VALUES (:k) ON CONFLICT DO NOTHING", values={"k": flag})
                    await send_report(now.date())
                    logger.info("Daily Slack report posted")
        except Exception as exc:
            logger.warning(f"Daily Slack report failed: {exc}")
        await asyncio.sleep(60)


# ─── On-demand in Slack (2026-10-20, per Shruti) ─────────────────────────────
# Type in #business-performance (or any channel the bot is in):
#   summary | summary today | summary yesterday | summary 19 Oct | summary 2026-10-19
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_summary_request(text: str):
    """The day asked for, or None if the message isn't a summary request.

    2026-10-21, per Shruti ("Sid posted 'please share today's summary' — no
    response"): besides "summary" / "summary yesterday" / "summary 19 Oct",
    any SHORT message that asks for the summary / report / daily update in
    plain words works too — "please share today's summary", "can I get
    yesterday's report?", "summary for 19 Oct pls". Long messages and anything
    with a phone number or "=" (lead posts) are never taken as a request."""
    t = re.sub(r"<@[A-Z0-9]+>", "", text or "").strip().lower()
    m = re.fullmatch(r"(?:daily\s+)?(?:summary|update|report)\s*(.*)", t)
    if not m:
        words = re.findall(r"[a-z0-9']+", t)
        if (len(words) > 12 or "=" in t or re.search(r"\d{6,}", re.sub(r"\s", "", t))
                or not re.search(r"\b(summary|summery|report|daily update|business update)\b", t)):
            return None
        # the day: today / yesterday / a date anywhere in the message
        if re.search(r"\byesterday", t):
            arg = "yesterday"
        else:
            dm = (re.search(r"\b\d{4}-\d{2}-\d{2}\b", t)
                  or re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+\d{4})?\b", t))
            arg = re.sub(r"(\d)(st|nd|rd|th)", r"\1", dm.group(0)) if dm else "today"
        m = re.fullmatch(r"(.*)", arg)
    arg = m.group(1)
    arg = re.sub(r"\b(for|of|the|pls|plz|please|share|send|me|on|today's|todays)\b", " ", arg)
    arg = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", re.sub(r"\s+", " ", arg)).strip(" ?.!,")
    today = datetime.now(IST).date()
    if arg in ("", "today", "now"):
        return today
    if arg == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(arg)
    except ValueError:
        pass
    m2 = re.fullmatch(r"(\d{1,2})\s*([a-z]{3})[a-z]*(?:\s+(\d{4}))?", arg)
    if m2 and m2.group(2) in _MONTHS:
        try:
            d = date(int(m2.group(3) or today.year), _MONTHS[m2.group(2)], int(m2.group(1)))
            return d if d <= today or m2.group(3) else d.replace(year=d.year - 1)
        except ValueError:
            return None
    return None


async def reply_in_thread(channel: str, ts: str, day: date) -> None:
    try:
        text = await build_report(day)
    except Exception as exc:
        logger.exception("On-demand summary failed")
        text = f"Sorry, I couldn't build the summary ({exc})."
    await slack_api("chat.postMessage", channel=channel, thread_ts=ts, text=text, unfurl_links=False, mrkdwn=True)
