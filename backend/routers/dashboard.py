"""
Admin performance dashboard (2026-09-11, per Shruti — CGO review: "do we
have enough system in place to track website performance"). Read-only:
this router only ever selects.

Two independent halves:
  1. Booking/lead metrics — straight from the `leads` table (bookings this
     week vs. last week vs. target, weekly trend, AOV, lead-to-booking
     conversion, repeat-customer rate). No external dependency, always on.
  2. GA4 traffic + builder-funnel numbers — via the GA4 Data API
     (ga4_client.py). Off (dashboard shows "not connected yet") until
     settings.GA4_PROPERTY_ID / GA4_SERVICE_ACCOUNT_JSON are set — see
     backend/GA4_SETUP.md.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header

from database import database
from config import settings
from routers.admin import _require_admin
import ga4_client

router = APIRouter()
logger = logging.getLogger(__name__)

WEEKS_OF_TREND = 12
_WEEKS_PER_MONTH = 4.345  # average weeks/month — see config.py's MONTHLY_REVENUE_TARGET comment


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
