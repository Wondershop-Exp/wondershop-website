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


# ─── GA4 funnels (Traffic & Leads, Landing-to-Checkout, Builder Start &
# Completion) — 2026-09-12, per Shruti completing the one-time GA4 setup
# (backend/GA4_SETUP.md). All four numbers this section needs come from ONE
# GA4 fetch (_ga4_funnel_raw_sync, run in a thread since the GA4 SDK is
# synchronous) bucketed three ways (day/week/month) so the dashboard's
# period toggle is instant client-side — no re-fetch on every pill click.
# ─────────────────────────────────────────────────────────────────────────

GA4_DAY_GRAIN_DAYS = 14  # 'day' grain window; 'week'/'month' reuse WEEKS_OF_TREND/MONTHS_OF_TREND above
FUNNEL_WINDOW_DAYS = 30  # fixed window for the two funnel cards (matches the design mockup's "(last 30 days)")

# The one builder step used for "Reached Review Cart" / Completion Rate —
# must match SNAMES[9] in builder.html's wsTrackScreen() exactly.
STEP_REVIEW_NAME = "Review"


def _ga4_funnel_raw_sync(range_start, today):
    """Runs entirely in a worker thread (asyncio.to_thread) — every
    ga4_client call here is synchronous. One traffic/events fetch + one
    daily-events-by-name fetch + one daily-Review-views fetch + one fixed
    30-day step-funnel fetch, all over the same lookback window."""
    traffic = ga4_client.fetch_traffic_and_events(range_start, today)
    daily_events = ga4_client.fetch_daily_events(range_start, today, list(ga4_client.FUNNEL_EVENTS))
    review_views = ga4_client.fetch_daily_step_views(range_start, today, STEP_REVIEW_NAME)
    step_funnel = ga4_client.fetch_step_funnel(today - timedelta(days=FUNNEL_WINDOW_DAYS), today)
    return {
        "daily_traffic": traffic["daily_traffic"],
        "daily_events": daily_events,
        "review_views": review_views,
        "step_funnel": step_funnel,
    }


def _step_data_ready(step_funnel) -> bool:
    """True once step_name/step_number are actually populating real values
    — i.e. at least one row isn't GA4's "(not set)" placeholder. GA4 does
    not backfill custom dimensions onto events recorded before the
    dimension was registered, so right after setup every row reads back as
    "(not set)" until enough new events accumulate (see GA4_SETUP.md's
    troubleshooting section) — that state is expected, not an error."""
    if not step_funnel:
        return False
    return any(s.get("step_name") not in (None, "(not set)", "") for s in step_funnel)


def _bucket_series(daily_values: dict, grain: str, now: datetime) -> list:
    """daily_values: {"YYYY-MM-DD": number}. Returns [{label, value}]
    oldest-first for the requested grain — day: last GA4_DAY_GRAIN_DAYS
    individual days; week: last WEEKS_OF_TREND Monday-start weeks (same
    definition as _week_start above); month: last MONTHS_OF_TREND calendar
    months (same as the revenue MoM trend). ISO date strings compare
    correctly as plain strings, so no date parsing is needed to bucket."""
    if grain == "day":
        days = [(now - timedelta(days=i)).date() for i in range(GA4_DAY_GRAIN_DAYS - 1, -1, -1)]
        return [{"label": d.isoformat(), "value": daily_values.get(d.isoformat(), 0)} for d in days]
    if grain == "month":
        months = [_add_months(_month_start(now), -(MONTHS_OF_TREND - 1) + i) for i in range(MONTHS_OF_TREND)]
        out = []
        for m in months:
            m_end = _add_months(m, 1)
            lo, hi = m.date().isoformat(), m_end.date().isoformat()
            total = sum(v for d, v in daily_values.items() if lo <= d < hi)
            out.append({"label": _month_key(m), "value": total})
        return out
    # 'week' (default)
    this_week = _week_start(now)
    weeks = [this_week - timedelta(weeks=i) for i in range(WEEKS_OF_TREND - 1, -1, -1)]
    out = []
    for ws in weeks:
        we = ws + timedelta(days=7)
        lo, hi = ws.date().isoformat(), we.date().isoformat()
        total = sum(v for d, v in daily_values.items() if lo <= d < hi)
        out.append({"label": ws.date().isoformat(), "value": total})
    return out


def _rate_series(numerator_series: list, denominator_series: list) -> list:
    """Elementwise numerator/denominator*100 per bucket (same label order —
    both series always come from _bucket_series with the same grain/now, so
    they line up positionally). None (not 0) when the denominator is 0, so
    the frontend can draw a gap instead of a misleading flat 0%."""
    out = []
    for num, den in zip(numerator_series, denominator_series):
        value = round(num["value"] / den["value"] * 100, 1) if den["value"] else None
        out.append({"label": den["label"], "value": value})
    return out


@router.get("/dashboard/ga4-funnels")
async def dashboard_ga4_funnels(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)

    if not ga4_client.is_configured():
        return {"configured": False}

    now = datetime.now(timezone.utc)
    today = now.date()
    range_start = _add_months(_month_start(now), -(MONTHS_OF_TREND - 1)).date()

    try:
        raw = await asyncio.to_thread(_ga4_funnel_raw_sync, range_start, today)
    except Exception as exc:
        logger.error(f"GA4 funnels fetch failed: {exc}")
        return {"configured": True, "error": str(exc)}

    sessions_by_day = {d["date"]: d["sessions"] for d in raw["daily_traffic"]}
    builder_start_by_day = {}
    for row in raw["daily_events"]:
        if row["event_name"] == "builder_start":
            builder_start_by_day[row["date"]] = builder_start_by_day.get(row["date"], 0) + row["count"]

    step_ready = _step_data_ready(raw["step_funnel"])
    review_by_day = {}
    if step_ready:
        for row in (raw["review_views"] or []):
            review_by_day[row["date"]] = review_by_day.get(row["date"], 0) + row["views"]

    grains = ("day", "week", "month")
    traffic = {g: _bucket_series(sessions_by_day, g, now) for g in grains}
    builder_start = {g: _bucket_series(builder_start_by_day, g, now) for g in grains}
    start_rate = {g: _rate_series(builder_start[g], traffic[g]) for g in grains}
    if step_ready:
        review = {g: _bucket_series(review_by_day, g, now) for g in grains}
        completion_rate = {g: _rate_series(review[g], builder_start[g]) for g in grains}
    else:
        completion_rate = None

    # ── Fixed 30-day totals, shared by both funnel cards below ──
    window_start = (today - timedelta(days=FUNNEL_WINDOW_DAYS)).isoformat()
    sessions_30d = sum(v for d, v in sessions_by_day.items() if d >= window_start)
    builder_start_30d = sum(v for d, v in builder_start_by_day.items() if d >= window_start)
    review_30d = sum(v for d, v in review_by_day.items() if d >= window_start) if step_ready else None
    event_totals_30d = {name: 0 for name in ga4_client.FUNNEL_EVENTS}
    for row in raw["daily_events"]:
        if row["date"] >= window_start and row["event_name"] in event_totals_30d:
            event_totals_30d[row["event_name"]] += row["count"]
    leads_30d = event_totals_30d["generate_lead"]
    checkout_30d = event_totals_30d["begin_checkout"]
    bookings_30d = event_totals_30d["booking_request_submitted"]

    # "Leads Captured" (generate_lead) is a SEPARATE, parallel capture path —
    # builder.html's wsTrackScreen fires it from an alternate "leave your
    # details" screen ('slead'/'sleadsent'), shown when someone doesn't
    # check out, not a stage strictly upstream of Checkout Started. So each
    # rate below reads against Website Sessions except the one pair that IS
    # genuinely sequential in the same session (Bookings Confirmed only
    # fires after Checkout Started) — this deliberately doesn't chain
    # Leads→Checkout→Bookings the way a strict funnel would, because that
    # would misrepresent two independent outcomes as one funnel.
    leads_funnel = [
        {"stage": "Website Sessions", "value": sessions_30d, "rate_label": None},
        {"stage": "Leads Captured", "value": leads_30d,
         "rate_label": (f"{round(leads_30d / sessions_30d * 100, 1)}% of sessions" if sessions_30d else None)},
        {"stage": "Checkout Started", "value": checkout_30d,
         "rate_label": (f"{round(checkout_30d / sessions_30d * 100, 1)}% of sessions" if sessions_30d else None)},
        {"stage": "Bookings Confirmed", "value": bookings_30d,
         "rate_label": (f"{round(bookings_30d / checkout_30d * 100, 1)}% of checkouts" if checkout_30d else None)},
    ]

    # Landing-to-Checkout core funnel — genuinely sequential (each stage is
    # a strict subset of the one above it in the real builder flow).
    core_funnel = {
        "ready": step_ready,
        "stages": [
            {"name": "Landed on Website", "value": sessions_30d},
            {"name": 'Clicked "Build a Birthday"', "value": builder_start_30d},
            {"name": "Reached Review Cart", "value": review_30d if step_ready else None},
            {"name": "Checkout / Booking Submitted", "value": bookings_30d},
        ],
    }

    return {
        "configured": True,
        "traffic": traffic,
        "start_rate": start_rate,
        "completion_rate": completion_rate,
        "step_ready": step_ready,
        "step_funnel": raw["step_funnel"] if step_ready else None,
        "leads_funnel": leads_funnel,
        "core_funnel": core_funnel,
        "window_days": FUNNEL_WINDOW_DAYS,
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
