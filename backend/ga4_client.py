"""
GA4 Data API client — read-only traffic + builder-funnel numbers for the
admin dashboard (backend/routers/dashboard.py). Deliberately isolated in
its own module: the google-analytics-data SDK is synchronous, so every
function here is meant to be called via asyncio.to_thread() from the
async route, never awaited directly.

Configuration: settings.GA4_PROPERTY_ID (bare numeric id, e.g. "123456789"
— "properties/123456789" also accepted) and settings.GA4_SERVICE_ACCOUNT_JSON
(the full JSON key file content for a service account with Viewer access
on that GA4 property, pasted as one env var — Railway has no file
uploads). Both blank = GA4 features are "not connected yet"; see
backend/GA4_SETUP.md for the one-time setup, including registering
step_name as an event-scoped custom dimension (needed for fetch_step_funnel
only — traffic and the named-event counts work without it).
"""
import json
import logging
from datetime import date
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.GA4_PROPERTY_ID and settings.GA4_SERVICE_ACCOUNT_JSON)


def _property_path() -> str:
    pid = settings.GA4_PROPERTY_ID.strip()
    return pid if pid.startswith("properties/") else f"properties/{pid}"


def _client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account
    info = json.loads(settings.GA4_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    return BetaAnalyticsDataClient(credentials=creds)


# Named builder-funnel events, matching the wsTrack() calls in builder.html
# (see "ANALYTICS: funnel event tracking (GA4)" in that file).
FUNNEL_EVENTS = ["builder_start", "begin_checkout", "booking_request_submitted", "generate_lead"]


def fetch_traffic_and_events(start: date, end: date) -> dict:
    """Daily sessions/activeUsers (bucketed into weeks by the caller, so
    week boundaries match the DB-side weekly trend exactly — GA4's own
    'week' dimension wouldn't necessarily agree with our Monday-start
    definition) plus total counts for each FUNNEL_EVENTS name over the
    whole window. Raises on any API/auth failure — the caller catches it
    and marks the GA4 section as 'configured but erroring' rather than
    failing the whole dashboard request."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter,
    )
    client = _client()

    traffic_req = RunReportRequest(
        property=_property_path(),
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
    )
    traffic_resp = client.run_report(traffic_req)
    daily = []
    for row in traffic_resp.rows:
        d = row.dimension_values[0].value  # YYYYMMDD
        sessions = int(row.metric_values[0].value)
        users = int(row.metric_values[1].value)
        daily.append({"date": f"{d[0:4]}-{d[4:6]}-{d[6:8]}", "sessions": sessions, "users": users})

    events_req = RunReportRequest(
        property=_property_path(),
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName",
            in_list_filter=Filter.InListFilter(values=FUNNEL_EVENTS),
        )),
    )
    events_resp = client.run_report(events_req)
    event_counts = {name: 0 for name in FUNNEL_EVENTS}
    for row in events_resp.rows:
        name = row.dimension_values[0].value
        count = int(row.metric_values[0].value)
        if name in event_counts:
            event_counts[name] = count

    return {"daily_traffic": daily, "event_counts": event_counts}


def fetch_daily_events(start: date, end: date, event_names: list) -> list:
    """Per-day event counts for the given event names (dimensions=[date,
    eventName]), used to build both day/week/month-bucketed series (Builder
    Start & Completion, Traffic & Leads Funnel) and fixed-window totals
    (sum the rows yourself over whatever sub-range you need) from a single
    GA4 report — cheaper than one API call per grain/window. Returns
    [{"date": "YYYY-MM-DD", "event_name": str, "count": int}, ...]; a day
    with zero occurrences of an event simply has no row (caller should
    default-fill with 0), matching how fetch_traffic_and_events' event_counts
    already behaves."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter,
    )
    client = _client()
    req = RunReportRequest(
        property=_property_path(),
        dimensions=[Dimension(name="date"), Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName",
            in_list_filter=Filter.InListFilter(values=event_names),
        )),
    )
    resp = client.run_report(req)
    out = []
    for row in resp.rows:
        d = row.dimension_values[0].value  # YYYYMMDD
        name = row.dimension_values[1].value
        count = int(row.metric_values[0].value)
        out.append({"date": f"{d[0:4]}-{d[4:6]}-{d[6:8]}", "event_name": name, "count": count})
    return out


def fetch_daily_step_views(start: date, end: date, step_name: str) -> Optional[list]:
    """Per-day view counts for ONE builder step (exact step_name match),
    used to track a grain-bucketed Completion Rate line on the dashboard
    (see dashboard.py's Builder Start & Completion section). Returns None
    (not an error) in the same case fetch_step_funnel does — the
    step_name/step_number custom dimensions aren't registered as valid GA4
    dimensions at all yet. An EMPTY LIST is a different, valid outcome and
    is ambiguous on its own: it means either "no one reached this step" or
    "these events predate the custom dimensions being registered, so they
    read back as step_name=(not set) and never match this filter" (GA4
    doesn't backfill custom dimensions onto historical events). The caller
    disambiguates using fetch_step_funnel's own "(not set)"-only signal
    rather than guessing from this function alone."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
        FilterExpression, FilterExpressionList, Filter,
    )
    client = _client()
    req = RunReportRequest(
        property=_property_path(),
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=FilterExpression(and_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="eventName", string_filter=Filter.StringFilter(value="builder_step_view"),
            )),
            FilterExpression(filter=Filter(
                field_name="customEvent:step_name", string_filter=Filter.StringFilter(value=step_name),
            )),
        ])),
    )
    try:
        resp = client.run_report(req)
    except Exception as exc:
        msg = str(exc).lower()
        if "step_name" in msg or "customevent" in msg or "does not exist" in msg or "invalid" in msg:
            logger.info(f"GA4 daily step views unavailable (custom dimension not registered yet?): {exc}")
            return None
        raise
    out = []
    for row in resp.rows:
        d = row.dimension_values[0].value
        out.append({"date": f"{d[0:4]}-{d[4:6]}-{d[6:8]}", "views": int(row.metric_values[0].value)})
    return out


def fetch_step_funnel(start: date, end: date) -> Optional[list]:
    """Per-step view counts + drop-off for the builder's 9 named steps,
    using the step_name/step_number event-scoped custom dimensions. Returns
    None (not an error — a configuration gap) if those dimensions aren't
    registered yet in the GA4 property (see backend/GA4_SETUP.md step 5);
    the dashboard shows a "register this to unlock per-step drop-off" note
    in that case instead of treating it as a failure."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter, OrderBy,
    )
    client = _client()
    req = RunReportRequest(
        property=_property_path(),
        dimensions=[Dimension(name="customEvent:step_name"), Dimension(name="customEvent:step_number")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(value="builder_step_view"),
        )),
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(
            dimension_name="customEvent:step_number",
            order_type=OrderBy.DimensionOrderBy.OrderType.NUMERIC,
        ))],
    )
    try:
        resp = client.run_report(req)
    except Exception as exc:
        msg = str(exc).lower()
        if "step_name" in msg or "step_number" in msg or "customevent" in msg or "does not exist" in msg or "invalid" in msg:
            logger.info(f"GA4 step funnel unavailable (custom dimensions not registered yet?): {exc}")
            return None
        raise

    steps = []
    for row in resp.rows:
        steps.append({
            "step_name": row.dimension_values[0].value,
            "step_number": row.dimension_values[1].value,
            "views": int(row.metric_values[0].value),
        })
    steps.sort(key=lambda s: int(s["step_number"]) if s["step_number"].lstrip("-").isdigit() else 0)
    for i, s in enumerate(steps):
        prev_views = steps[i - 1]["views"] if i > 0 else s["views"]
        s["drop_off_pct"] = round((1 - s["views"] / prev_views) * 100, 1) if (prev_views and i > 0) else 0.0
    return steps
