"""
Admin performance dashboard (2026-09-11, per Shruti — CGO review: "do we
have enough system in place to track website performance"; then "we would
look at monthly revenue... add some graphics around target achieved"; then
the full rebuild spec: "revenue realized till now... revenue booked this
month... potential revenue" + a from-scratch layout reviewed via a design
mockup). Read-only except the one manual-target-override endpoint at the
bottom.

Two sections:
  1. Weekly trend — straight from the `leads` table (bookings this week vs.
     last week vs. target, 12-week trend, AOV, lead-to-booking conversion,
     repeat-customer rate). No external dependency, always on.
  2. Monthly overview — Realized / Booked / Potential revenue AND bookings,
     each against its own manually-set monthly target, a 6-month trend, and
     an "events confirmed in the next 14 days" count for the festivals
     strip. All from the `leads` table + the two event-payment-confirmation
     fields added to the admin panel (routers/admin.py's
     event_payment_confirmed_amount / event_payment_confirmed_mode) — see
     the classification rule in _classify_month() below.

GA4 traffic/builder-funnel numbers (Traffic & Leads Funnel, Builder
Start/Completion, Landing-to-Checkout Funnel in the new design) are NOT
built here yet — they need GA4_PROPERTY_ID/GA4_SERVICE_ACCOUNT_JSON
configured first (see backend/GA4_SETUP.md), which isn't done in production
as of this rebuild. _fetch_ga4_summary() below still powers the *weekly*
dashboard's GA4 card the same way it always has; the new monthly design's
GA4-dependent cards are wired up client-side to show a "not connected yet"
state until that setup happens and the day/week/month-grain queries get
built against real numbers.
"""
import asyncio
import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from database import database
from config import settings
from routers.admin import _require_admin
import ga4_client

router = APIRouter()
logger = logging.getLogger(__name__)

WEEKS_OF_TREND = 12
_WEEKS_PER_MONTH = 4.345  # average weeks/month — see config.py's MONTHLY_REVENUE_TARGET comment
MONTHS_OF_TREND = 6

# Warm-lead statuses that count as "Potential" — the team is actively
# working these, just not converted yet. Matches LEAD_STATUS_DROPDOWN_VALUES
# in routers/admin.py minus New/Converted/Not Interested/DND.
POTENTIAL_STATUSES = ("Initial Discussions Done", "Proposal Sent", "Negotiations Ongoing")


def _week_start(dt: datetime) -> datetime:
    """Monday 00:00 UTC of the week containing dt."""
    d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())


def _aov(bucket: dict) -> Optional[float]:
    return round(bucket["revenue"] / bucket["bookings"], 2) if bucket["bookings"] else None


def _conversion_pct(bucket: dict) -> Optional[float]:
    return round(bucket["bookings"] / bucket["leads"] * 100, 1) if bucket["leads"] else None


async def _fetch_ga4_summary(start, end) -> dict:
    if not ga4_client.is_configured():
        return {"configured": False}
    try:
        traffic = await asyncio.to_thread(ga4_client.fetch_traffic_and_events, start, end)
    except Exception as exc:
        logger.error(f"GA4 traffic/events fetch failed: {exc}")
        return {"configured": True, "error": str(exc)}
    try:
        step_funnel = await asyncio.to_thread(ga4_client.fetch_step_funnel, start, end)
    except Exception as exc:
        logger.error(f"GA4 step funnel fetch failed: {exc}")
        step_funnel = None
    return {
        "configured": True,
        "daily_traffic": traffic["daily_traffic"],
        "event_counts": traffic["event_counts"],
        "step_funnel": step_funnel,  # None => custom dimensions not registered yet
    }


@router.get("/dashboard/summary")
async def dashboard_summary(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    now = datetime.now(timezone.utc)
    this_week_start = _week_start(now)
    trend_start = this_week_start - timedelta(weeks=WEEKS_OF_TREND - 1)

    rows = await database.fetch_all(
        """
        SELECT created_on, is_booking, status,
               COALESCE(client_budget, order_grand_total) AS revenue
        FROM leads
        WHERE created_on >= :start
        """,
        values={"start": trend_start},
    )

    buckets = {}
    for i in range(WEEKS_OF_TREND):
        ws = trend_start + timedelta(weeks=i)
        buckets[ws.date().isoformat()] = {
            "week_start": ws.date().isoformat(), "bookings": 0, "revenue": 0.0, "leads": 0,
        }

    for r in rows:
        created = r["created_on"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        key = _week_start(created).date().isoformat()
        b = buckets.get(key)
        if b is None:
            continue  # outside the trend window due to a clock/timezone edge — ignore rather than crash
        b["leads"] += 1
        if r["is_booking"] and r["status"] != "Cancelled":
            b["bookings"] += 1
            b["revenue"] += float(r["revenue"] or 0)

    trend = [buckets[k] for k in sorted(buckets.keys())]
    for b in trend:
        b["aov"] = _aov(b)
        b["conversion_pct"] = _conversion_pct(b)

    this_key = this_week_start.date().isoformat()
    last_key = (this_week_start - timedelta(days=7)).date().isoformat()
    this_week = buckets.get(this_key, {"week_start": this_key, "bookings": 0, "revenue": 0.0, "leads": 0})
    last_week = buckets.get(last_key, {"week_start": last_key, "bookings": 0, "revenue": 0.0, "leads": 0})
    this_week = {**this_week, "aov": _aov(this_week), "conversion_pct": _conversion_pct(this_week)}
    last_week = {**last_week, "aov": _aov(last_week), "conversion_pct": _conversion_pct(last_week)}

    totals = await database.fetch_one(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_booking) AS bookings FROM leads"
    )
    all_time_conversion_pct = (
        round(totals["bookings"] / totals["total"] * 100, 1) if totals["total"] else None
    )

    repeat_rows = await database.fetch_all(
        """
        SELECT phone, COUNT(*) AS cnt
        FROM leads
        WHERE is_booking = TRUE AND status != 'Cancelled' AND phone IS NOT NULL AND phone != ''
        GROUP BY phone
        """
    )
    total_booking_customers = len(repeat_rows)
    repeat_customers = sum(1 for r in repeat_rows if r["cnt"] > 1)
    repeat_customer_rate_pct = (
        round(repeat_customers / total_booking_customers * 100, 1) if total_booking_customers else None
    )

    weekly_target_revenue = round(settings.MONTHLY_REVENUE_TARGET / _WEEKS_PER_MONTH, 2)

    return {
        "generated_at": now.isoformat(),
        "monthly_target_revenue": settings.MONTHLY_REVENUE_TARGET,
        "weekly_target_revenue": weekly_target_revenue,
        "this_week": this_week,
        "last_week": last_week,
        "trend": trend,
        "all_time_conversion_pct": all_time_conversion_pct,
        "repeat_customer_rate_pct": repeat_customer_rate_pct,
        "repeat_customers": repeat_customers,
        "total_booking_customers": total_booking_customers,
        "ga4": await _fetch_ga4_summary(trend_start.date(), now.date()),
    }


# ─── Monthly overview (Realized / Booked / Potential) ──────────────────────

def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(month_start: datetime, n: int) -> datetime:
    total = month_start.month - 1 + n
    year = month_start.year + total // 12
    month = total % 12 + 1
    return month_start.replace(year=year, month=month)


def _month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _parse_month_param(month: Optional[str], now: datetime) -> datetime:
    if not month:
        return _month_start(now)
    try:
        y, m = month.split("-")
        return datetime(int(y), int(m), 1, tzinfo=timezone.utc)
    except Exception:
        return _month_start(now)


async def _confirmed_bookings_in_month(month_start: datetime, month_end: datetime):
    """Every non-cancelled CONFIRMED booking whose event falls in this
    month, with the event-payment-confirmation fields joined in. Those two
    fields (added 2026-09-11 to routers/admin.py's FIELD_CATALOG,
    admin_only, Billing & Rewards section) are stored the same way every
    other admin-only field on the booking page is: as
    customer_choice_override in booking_field_overrides — see
    update_booking_field()'s override-based-fields branch. (The
    "assigned_value"/Updated Value column is a different concept — who's
    assigned to fulfil a customer's choice — not used for admin-only
    fields.)"""
    return await database.fetch_all(
        """
        SELECT l.lead_id, l.event_date, l.status,
               COALESCE(l.client_budget, l.order_grand_total, 0) AS revenue,
               amt.customer_choice_override AS payment_amount,
               mode.customer_choice_override AS payment_mode
        FROM leads l
        LEFT JOIN booking_field_overrides amt
          ON amt.lead_id = l.lead_id AND amt.field_key = 'event_payment_confirmed_amount'
        LEFT JOIN booking_field_overrides mode
          ON mode.lead_id = l.lead_id AND mode.field_key = 'event_payment_confirmed_mode'
        WHERE l.is_booking = TRUE AND l.status != 'Cancelled'
          AND l.event_date >= :start AND l.event_date < :end
        """,
        values={"start": month_start.date(), "end": month_end.date()},
    )


def _classify_month(rows, today) -> dict:
    """Realized = event already happened AND the event admin has confirmed
    both the payment amount and mode (per Shruti, 2026-09-11 — not just the
    date having passed). Everything else confirmed stays Booked, including
    an event that's already happened but hasn't been confirmed yet — that
    case is also counted in pending_confirm_count so it stays visible
    rather than silently sitting in Booked forever."""
    realized_n = booked_n = pending_n = 0
    realized_rev = booked_rev = 0.0
    for r in rows:
        rev = float(r["revenue"] or 0)
        confirmed = bool(r["payment_amount"]) and bool(r["payment_mode"])
        happened = r["event_date"] is not None and r["event_date"] < today
        if happened and confirmed:
            realized_n += 1
            realized_rev += rev
        else:
            booked_n += 1
            booked_rev += rev
            if happened and not confirmed:
                pending_n += 1
    return {
        "realized_bookings": realized_n, "realized_revenue": round(realized_rev, 2),
        "booked_bookings": booked_n, "booked_revenue": round(booked_rev, 2),
        "pending_confirm_count": pending_n,
    }


async def _potential_in_month(month_start: datetime, month_end: datetime) -> dict:
    """Warm leads (see POTENTIAL_STATUSES) whose event_date falls in this
    month, valued at the lead's own stated budget. A warm lead with no
    event_date yet isn't counted toward any month — there's nothing to
    bucket it by."""
    row = await database.fetch_one(
        """
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(COALESCE(client_budget, order_grand_total, 0)), 0) AS revenue
        FROM leads
        WHERE is_booking = FALSE AND status = ANY(:statuses)
          AND event_date >= :start AND event_date < :end
        """,
        values={"statuses": list(POTENTIAL_STATUSES), "start": month_start.date(), "end": month_end.date()},
    )
    return {
        "potential_bookings": row["cnt"] or 0,
        "potential_revenue": round(float(row["revenue"] or 0), 2),
    }


async def _month_summary(month_start: datetime, now: datetime) -> dict:
    month_end = _add_months(month_start, 1)
    today = now.date()

    rows = await _confirmed_bookings_in_month(month_start, month_end)
    classified = _classify_month(rows, today)
    potential = await _potential_in_month(month_start, month_end)

    total_bookings = classified["realized_bookings"] + classified["booked_bookings"] + potential["potential_bookings"]
    total_revenue = round(classified["realized_revenue"] + classified["booked_revenue"] + potential["potential_revenue"], 2)

    # "Actual" — Realized + Booked only, excluding Potential — is what
    # powers the MoM trend/table and AOV below, matching her original
    # spreadsheet's Actual Revenue/Bookings. Potential only shows as its
    # own line in the Monthly Overview stat row (and inside Total
    # Projected), never blended into "actual".
    actual_bookings = classified["realized_bookings"] + classified["booked_bookings"]
    actual_revenue = round(classified["realized_revenue"] + classified["booked_revenue"], 2)

    return {
        "month": _month_key(month_start),
        **classified,
        **potential,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "actual_bookings": actual_bookings,
        "actual_revenue": actual_revenue,
        "aov": round(actual_revenue / actual_bookings, 2) if actual_bookings else None,
    }


@router.get("/dashboard/monthly")
async def dashboard_monthly(month: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    now = datetime.now(timezone.utc)
    requested_month = _parse_month_param(month, now)

    overrides_rows = await database.fetch_all(
        "SELECT * FROM dashboard_monthly_overrides WHERE month_start >= :start",
        values={"start": _add_months(_month_start(now), -(MONTHS_OF_TREND - 1)).date()},
    )
    overrides_by_month = {r["month_start"].isoformat(): dict(r) for r in overrides_rows}

    trend = []
    for i in range(MONTHS_OF_TREND):
        m = _add_months(_month_start(now), -(MONTHS_OF_TREND - 1) + i)
        summary = await _month_summary(m, now)
        ov = overrides_by_month.get(m.date().isoformat())
        target = float(ov["monthly_target"]) if (ov and ov["monthly_target"] is not None) else None
        pct_target = round(summary["actual_revenue"] / target * 100, 1) if target else None
        trend.append({**summary, "target": target, "pct_target": pct_target})

    this_summary = await _month_summary(requested_month, now)
    this_ov = overrides_by_month.get(requested_month.date().isoformat())
    if this_ov is None:
        this_ov_row = await database.fetch_one(
            "SELECT * FROM dashboard_monthly_overrides WHERE month_start = :m",
            values={"m": requested_month.date()},
        )
        this_ov = dict(this_ov_row) if this_ov_row else None

    revenue_target = float(this_ov["monthly_target"]) if (this_ov and this_ov["monthly_target"] is not None) else None
    bookings_target = (
        int(this_ov["bookings_target"])
        if (this_ov and this_ov.get("bookings_target") is not None)
        else None
    )
    revenue_target_pct = round(this_summary["total_revenue"] / revenue_target * 100) if revenue_target else None
    bookings_target_pct = round(this_summary["total_bookings"] / bookings_target * 100) if bookings_target else None

    confirmed_events_row = await database.fetch_one(
        """
        SELECT COUNT(*) AS cnt FROM leads
        WHERE is_booking = TRUE AND status != 'Cancelled'
          AND event_date >= :today AND event_date < :in14
        """,
        values={"today": now.date(), "in14": (now + timedelta(days=14)).date()},
    )

    return {
        "month": _month_key(requested_month),
        "generated_at": now.isoformat(),
        **this_summary,
        "revenue_target": revenue_target,
        "bookings_target": bookings_target,
        "revenue_target_pct": revenue_target_pct,
        "bookings_target_pct": bookings_target_pct,
        "trend": trend,
        "confirmed_events_next_14d": confirmed_events_row["cnt"] or 0,
        "updated_by": this_ov["updated_by"] if this_ov else None,
        "updated_on": this_ov["updated_on"].isoformat() if (this_ov and this_ov["updated_on"]) else None,
    }


class MonthlyOverrideRequest(BaseModel):
    month: str  # "YYYY-MM"
    monthly_target: Optional[float] = None
    bookings_target: Optional[int] = None
    updated_by: str


@router.put("/dashboard/monthly-overrides")
async def save_monthly_overrides(body: MonthlyOverrideRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    try:
        y, m = body.month.split("-")
        month_start = datetime(int(y), int(m), 1).date()
    except Exception:
        return {"error": "invalid month, expected YYYY-MM"}

    now = datetime.now(timezone.utc)

    await database.execute(
        """
        INSERT INTO dashboard_monthly_overrides
            (month_start, monthly_target, bookings_target, updated_by, updated_on)
        VALUES
            (:month_start, :target, :bookings_target, :updated_by, :now)
        ON CONFLICT (month_start) DO UPDATE SET
            monthly_target = EXCLUDED.monthly_target,
            bookings_target = EXCLUDED.bookings_target,
            updated_by = EXCLUDED.updated_by,
            updated_on = EXCLUDED.updated_on
        """,
        values={
            "month_start": month_start,
            "target": body.monthly_target,
            "bookings_target": body.bookings_target,
            "updated_by": body.updated_by, "now": now,
        },
    )
    return {"ok": True}
