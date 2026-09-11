"""
Admin performance dashboard (2026-09-11, per Shruti — CGO review: "do we
have enough system in place to track website performance"; then "we would
look at monthly revenue... add some graphics around target achieved").
Read-only except the one manual-override endpoint at the bottom.

Three sections:
  1. Weekly trend — straight from the `leads` table (bookings this week vs.
     last week vs. target, 12-week trend, AOV, lead-to-booking conversion,
     repeat-customer rate). No external dependency, always on.
  2. Monthly overview — the view Shruti actually works from day to day:
     this month's bookings/revenue/AOV against a per-month target, a
     run-rate "estimated" full-month projection, a 6-month trend table, and
     a leads funnel by channel (Website + Repeat computed from `leads`;
     Instagram + Carried Forward are entered by hand — see
     dashboard_monthly_overrides below, neither channel is logged in
     `leads` today).
  3. GA4 traffic + builder-funnel numbers — via the GA4 Data API
     (ga4_client.py). Off (dashboard shows "not connected yet") until
     settings.GA4_PROPERTY_ID / GA4_SERVICE_ACCOUNT_JSON are set — see
     backend/GA4_SETUP.md.
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


# ─── Monthly overview ──────────────────────────────────────────────────────

def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(month_start: datetime, n: int) -> datetime:
    total = month_start.month - 1 + n
    year = month_start.year + total // 12
    month = total % 12 + 1
    return month_start.replace(year=year, month=month)


def _days_in_month(month_start: datetime) -> int:
    return calendar.monthrange(month_start.year, month_start.month)[1]


def _days_elapsed(month_start: datetime, now: datetime) -> int:
    """How many days of month_start have actually happened as of `now` — the
    full month if it's already in the past, or today's day-of-month if it's
    the current month. Used to project a run-rate 'estimated full month'
    revenue: a half-finished month isn't behind target, it's just not over
    yet, and this is what tells the two apart."""
    if (month_start.year, month_start.month) == (now.year, now.month):
        return now.day
    if month_start < _month_start(now):
        return _days_in_month(month_start)
    return 0  # a future month — shouldn't be requested, but don't divide by zero


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


def _channel_metrics(leads_count: int, converted: int, revenue: float) -> dict:
    return {
        "leads": leads_count,
        "converted": converted,
        "conversion_pct": round(converted / leads_count * 100, 1) if leads_count else None,
        # 1 confirmed booking == 1 order in this system today, so "orders"
        # and "converted" are the same count — kept as separate keys because
        # that's how Shruti's tracker lays the funnel out (Converted Leads /
        # Orders as two rows).
        "orders": converted,
        "revenue": round(revenue, 2) if revenue else 0.0,
        "aov": round(revenue / converted, 2) if converted else None,
    }


async def _leads_funnel(month_start: datetime, month_end: datetime) -> dict:
    """Website + Repeat, computed from real `leads` rows. Every row in
    `leads` is captured through the site builder (lead_source always starts
    'Website - ...'), so 'Website leads' is just every lead created in the
    month; 'Repeat leads' is the subset from a phone number that already
    had an earlier CONFIRMED booking. These are two overlapping lenses on
    the same leads, not a partition — a repeat customer's lead still counts
    toward Website leads too. (Instagram / Carried Forward aren't in this
    table at all yet — see dashboard_monthly_overrides.)"""
    leads_rows = await database.fetch_all(
        """
        SELECT phone, created_on, is_booking, status,
               COALESCE(client_budget, order_grand_total) AS revenue
        FROM leads
        WHERE created_on >= :start AND created_on < :end
        """,
        values={"start": month_start, "end": month_end},
    )
    first_booking_rows = await database.fetch_all(
        """
        SELECT phone, MIN(created_on) AS first_booking_on
        FROM leads
        WHERE is_booking = TRUE AND status != 'Cancelled' AND phone IS NOT NULL AND phone != ''
        GROUP BY phone
        """
    )
    first_booking_by_phone = {r["phone"]: r["first_booking_on"] for r in first_booking_rows}

    web_leads = web_converted = web_revenue = 0
    rep_leads = rep_converted = rep_revenue = 0
    for r in leads_rows:
        converted = bool(r["is_booking"] and r["status"] != "Cancelled")
        revenue = float(r["revenue"] or 0) if converted else 0.0

        web_leads += 1
        if converted:
            web_converted += 1
            web_revenue += revenue

        first_booking_on = first_booking_by_phone.get(r["phone"])
        if first_booking_on is not None:
            if first_booking_on.tzinfo is None:
                first_booking_on = first_booking_on.replace(tzinfo=timezone.utc)
            if first_booking_on < month_start:
                rep_leads += 1
                if converted:
                    rep_converted += 1
                    rep_revenue += revenue

    return {
        "website": _channel_metrics(web_leads, web_converted, web_revenue),
        "repeat": _channel_metrics(rep_leads, rep_converted, rep_revenue),
    }


def _manual_channel(ov: Optional[dict], prefix: str) -> dict:
    if not ov:
        return {"leads": None, "converted": None, "conversion_pct": None, "orders": None, "revenue": None, "aov": None, "source": "manual"}
    leads_n = ov[f"{prefix}_leads"]
    converted_n = ov[f"{prefix}_converted"]
    revenue_n = float(ov[f"{prefix}_revenue"]) if ov[f"{prefix}_revenue"] is not None else None
    return {
        "leads": leads_n,
        "converted": converted_n,
        "conversion_pct": round(converted_n / leads_n * 100, 1) if leads_n else None,
        "orders": converted_n,
        "revenue": revenue_n,
        "aov": round(revenue_n / converted_n, 2) if (converted_n and revenue_n is not None) else None,
        "source": "manual",
    }


async def _month_actuals(month_start: datetime, now: datetime) -> dict:
    month_end = _add_months(month_start, 1)
    row = await database.fetch_one(
        """
        SELECT COUNT(*) FILTER (WHERE is_booking AND status != 'Cancelled') AS bookings,
               COALESCE(SUM(COALESCE(client_budget, order_grand_total))
                         FILTER (WHERE is_booking AND status != 'Cancelled'), 0) AS revenue
        FROM leads
        WHERE created_on >= :start AND created_on < :end
        """,
        values={"start": month_start, "end": month_end},
    )
    bookings = row["bookings"] or 0
    revenue = float(row["revenue"] or 0)
    days_elapsed = _days_elapsed(month_start, now)
    days_total = _days_in_month(month_start)
    estimated_revenue = (
        round(revenue * days_total / days_elapsed, 2) if days_elapsed else revenue
    )
    return {
        "month": _month_key(month_start),
        "days_elapsed": days_elapsed,
        "days_in_month": days_total,
        "bookings": bookings,
        "actual_revenue": round(revenue, 2),
        "estimated_revenue": estimated_revenue,
        "aov": round(revenue / bookings, 2) if bookings else None,
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
        actuals = await _month_actuals(m, now)
        ov = overrides_by_month.get(m.date().isoformat())
        target = float(ov["monthly_target"]) if (ov and ov["monthly_target"] is not None) else (
            settings.MONTHLY_REVENUE_TARGET if m.year == now.year and m.month == now.month else None
        )
        pct_target = round(actuals["estimated_revenue"] / target * 100, 1) if target else None
        trend.append({**actuals, "target": target, "pct_target": pct_target})

    this_month_actuals = await _month_actuals(requested_month, now)
    this_ov = overrides_by_month.get(requested_month.date().isoformat())
    if this_ov is None:
        this_ov_row = await database.fetch_one(
            "SELECT * FROM dashboard_monthly_overrides WHERE month_start = :m",
            values={"m": requested_month.date()},
        )
        this_ov = dict(this_ov_row) if this_ov_row else None

    is_current_month = (requested_month.year, requested_month.month) == (now.year, now.month)
    target = float(this_ov["monthly_target"]) if (this_ov and this_ov["monthly_target"] is not None) else (
        settings.MONTHLY_REVENUE_TARGET if is_current_month else None
    )
    target_is_override = bool(this_ov and this_ov["monthly_target"] is not None)
    pct_target = round(this_month_actuals["estimated_revenue"] / target * 100, 1) if target else None

    funnel = await _leads_funnel(requested_month, _add_months(requested_month, 1))
    funnel["instagram"] = _manual_channel(this_ov, "instagram")
    funnel["carried_forward"] = _manual_channel(this_ov, "carried_forward")

    return {
        "month": _month_key(requested_month),
        "generated_at": now.isoformat(),
        **this_month_actuals,
        "target": target,
        "target_is_override": target_is_override,
        "pct_target": pct_target,
        "trend": trend,
        "leads_funnel": funnel,
        "updated_by": this_ov["updated_by"] if this_ov else None,
        "updated_on": this_ov["updated_on"].isoformat() if (this_ov and this_ov["updated_on"]) else None,
    }


class ChannelOverrideIn(BaseModel):
    leads: Optional[int] = None
    converted: Optional[int] = None
    revenue: Optional[float] = None


class MonthlyOverrideRequest(BaseModel):
    month: str  # "YYYY-MM"
    monthly_target: Optional[float] = None
    instagram: Optional[ChannelOverrideIn] = None
    carried_forward: Optional[ChannelOverrideIn] = None
    updated_by: str


@router.put("/dashboard/monthly-overrides")
async def save_monthly_overrides(body: MonthlyOverrideRequest, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    try:
        y, m = body.month.split("-")
        month_start = datetime(int(y), int(m), 1).date()
    except Exception:
        return {"error": "invalid month, expected YYYY-MM"}

    instagram = body.instagram or ChannelOverrideIn()
    carried = body.carried_forward or ChannelOverrideIn()
    now = datetime.now(timezone.utc)

    await database.execute(
        """
        INSERT INTO dashboard_monthly_overrides
            (month_start, monthly_target,
             instagram_leads, instagram_converted, instagram_revenue,
             carried_forward_leads, carried_forward_converted, carried_forward_revenue,
             updated_by, updated_on)
        VALUES
            (:month_start, :target,
             :ig_leads, :ig_converted, :ig_revenue,
             :cf_leads, :cf_converted, :cf_revenue,
             :updated_by, :now)
        ON CONFLICT (month_start) DO UPDATE SET
            monthly_target = EXCLUDED.monthly_target,
            instagram_leads = EXCLUDED.instagram_leads,
            instagram_converted = EXCLUDED.instagram_converted,
            instagram_revenue = EXCLUDED.instagram_revenue,
            carried_forward_leads = EXCLUDED.carried_forward_leads,
            carried_forward_converted = EXCLUDED.carried_forward_converted,
            carried_forward_revenue = EXCLUDED.carried_forward_revenue,
            updated_by = EXCLUDED.updated_by,
            updated_on = EXCLUDED.updated_on
        """,
        values={
            "month_start": month_start,
            "target": body.monthly_target,
            "ig_leads": instagram.leads, "ig_converted": instagram.converted, "ig_revenue": instagram.revenue,
            "cf_leads": carried.leads, "cf_converted": carried.converted, "cf_revenue": carried.revenue,
            "updated_by": body.updated_by, "now": now,
        },
    )
    return {"ok": True}
