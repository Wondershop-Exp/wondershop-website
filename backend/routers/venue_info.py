"""
Venue & society information form — 2026-10-31, per Shruti (replaces the
Google Form "Venue & Society Information Form"):

  "this should be asked at the time of booking or can be shared separately
  to the customer - whether it's website booking or backend booking ... like
  ikea, we would like this info to plan our events better. T&C would be the
  latest T&C updated on the website. also give an option to upload venue pics
  and videos and option to add tags like decor placement, DJ placement,
  return gift placement ... booking details should be shown on this form."

One link per booking (table venue_info, migration 080): venue.html?t=<token>.

Venue recce (2026-11-12, per Shruti — "venue recce - add it to the venue
information form. also, our volunteer can fill the form on behalf of the
customer as well"): the same link with &recce=1 shows the customer questions
(which the volunteer can fill or correct) plus the team-only RECCE_SECTIONS
(decor area, ceiling height, plug points incl. 16 amp for LED decor and live
T-shirt printing, medical kit, ...). A recce save needs no T&C tick (that stays
the customer's) and is stamped _recce_by / _recce_at in the answers. Training
guide: training-venue-recce.html.
Answers save as the customer goes (nothing is required to save); the page and
the bookings panel show what's still missing. Photos are shrunk in the
browser before upload; videos are capped at 30 MB each, 3 per booking. Files
live in Postgres (venue_media.data, BYTEA) like the other uploads.

Created automatically when a website booking is placed (the link is shown on
the order confirmation page and in the confirmation email) or from the
booking page (email / WhatsApp buttons) for bookings made in the panel.

Public:
  GET    /api/venue-info/{token}                      form data + booking details
  POST   /api/venue-info/{token}                      save answers (+ accept T&C / submit)
  POST   /api/venue-info/{token}/media                upload one photo / video (multipart)
  GET    /api/venue-info/{token}/media/{id}           the file (Range supported, for video)
  POST   /api/venue-info/{token}/media/{id}           change its tags / caption
  DELETE /api/venue-info/{token}/media/{id}           remove it
Admin (X-Admin-Password; sales login allowed — see security.py):
  GET    /api/admin/bookings/{lead_id}/venue-info               link, status, answers, media
  GET    /api/admin/bookings/{lead_id}/venue-info/media/{id}    a file
  POST   /api/admin/bookings/{lead_id}/venue-info/email         email the link
  POST   /api/admin/bookings/{lead_id}/venue-info/whatsapp      note it was sent on WhatsApp
"""
import json
import logging
import re
import secrets
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin, _to_ist_str
from catalogue_data import greeting_name

logger = logging.getLogger(__name__)
router = APIRouter()

SITE_BASE_URL = "https://www.wondershopexperiences.com"
TNC_URL = SITE_BASE_URL + "/terms.html"

MAX_IMAGE_BYTES = 10 * 1024 * 1024    # the page shrinks photos to ~1 MB before upload
MAX_VIDEO_BYTES = 30 * 1024 * 1024
MAX_IMAGES = 40   # raised from 20 for the recce photos (2026-11-12)
MAX_VIDEOS = 5

# (key, label, type, options [(value, label)], required, follow-up)
# follow-up = (key, label, show when the answer is one of these values)
SECTIONS = [
    ("Timings", [
        ("event_start", "The party starts at", "time", None, True, None),
        ("event_end", "The party ends at", "time", None, True, None),
        ("setup_from", "Our team can enter the venue for setup from", "time", None, True, None),
        ("clear_by", "The venue must be cleared by", "time", None, True, None),
        ("other_event", "Is there another event at the venue that day?", "chips",
         [("none", "No"), ("before", "Before ours"), ("after", "After ours"), ("both", "Both")], True,
         ("other_event_note", "Its timing (e.g. till 3 PM)", ["before", "after", "both"])),
    ]),
    ("Getting our things in", [
        # Same values as the booking's Location Type (2026-10-31 — "what if the
        # venue is a restaurant or a banquet hall or turf?").
        ("venue_type", "What kind of venue is it?", "chips",
         [("Society Banquet Hall", "Society clubhouse / hall"), ("Society Banquet", "Banquet hall"), ("Restaurant", "Restaurant"),
          ("Turf", "Turf"), ("Club", "Club / resort"), ("Play Area", "Play area"), ("Home", "Home"), ("Other", "Other")], True, None),
        ("venue_address", "Venue name and full address", "short", None, True, None),
        ("maps_link", "Google Maps link of the venue", "url", None, True, None),
        ("floor", "Which floor is the party on?", "chips",
         [("ground", "Ground"), ("1-3", "1–3"), ("4-10", "4–10"), ("11+", "11+"), ("terrace", "Terrace")], True, None),
        ("vehicle", "Can our vehicle (car / tempo) reach the building?", "chips",
         [("yes", "Yes, till the entrance"), ("gate", "Only till the gate"), ("unsure", "Not sure")], True, None),
        ("parking", "Parking for our team", "chips",
         [("yes", "Yes"), ("paid", "Paid / outside"), ("no", "No")], True, None),
        ("unloading", "Distance from the unloading point to the venue", "chips",
         [("lt20", "Under 20 m"), ("20-50", "20–50 m"), ("gt50", "50 m+"), ("unsure", "Not sure")], True, None),
        ("route", "How do materials reach the venue?", "chips",
         [("service_lift", "Service lift"), ("passenger_lift", "Passenger lift"), ("stairs", "Stairs"),
          ("none", "No lift needed"), ("unsure", "Not sure")], True, None),
        ("lift_limits", "Any time limits for the lift or entry?", "chips",
         [("no", "No"), ("yes", "Yes")], True,
         ("lift_limits_note", "What are the timings?", ["yes"])),
        ("trolleys", "Are trolleys available?", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
    ]),
    # 2026-11-12, per Shruti — "venue should have location for all elements,
    # irrespective of who is doing it ... if possible mark the position on the
    # floor map". Shown to the customer and the team; all optional.
    ("Where things go", [
        ("loc_decor", "Main decor", "short", None, False, None),
        ("loc_welcome_board", "Welcome board", "short", None, False, None),
        ("loc_welcome_arch", "Welcome arch", "short", None, False, None),
        ("loc_music", "Music / DJ", "short", None, False, None),
        ("loc_buffet", "Buffet / food", "short", None, False, None),
        ("loc_adult_zone", "Adult hangout zone", "short", None, False, None),
        ("loc_seating", "Seating (if any)", "short", None, False, None),
        ("loc_return_gifts", "Return gifts table(s) — 1 table holds up to 30 gifts; live T-shirt printing needs 4 tables", "short", None, False, None),
        ("loc_gifts", "Gifts table(s) for presents — 1 table holds up to 30 gifts", "short", None, False, None),
        ("loc_spy", "Spy party only: registration desk and the 5 / 8 stations", "short", None, False, None),
        ("loc_other", "Anything else (cake table, show area, photo booth…)", "short", None, False, None),
        ("floor_map", "Floor map — mark where everything goes", "floormap", None, False, None),
    ]),
    ("Venue rules", [
        ("gate_pass", "Does the venue or building need an entry pass / permission for our team?", "chips",
         [("yes", "Yes, I'll arrange it"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("tape", "Can we use tape on the walls?", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("venue_contact_name", "Venue manager / contact person's name", "short", None, False, None),
        ("venue_contact_phone", "Venue manager / contact person's phone", "phone", None, False, None),
        ("venue_notes", "Anything else the venue told you? (rules, restrictions, timings)", "text", None, False, None),
    ]),
]

# Team-only questions, shown with &recce=1. "required" here = needed for the
# recce to be complete (does not affect the customer's progress).
RECCE_SECTIONS = [
    ("Recce · Decor area", [
        ("decor_area", "Where will the main decor go? (e.g. banquet hall, left wall)", "short", None, True, None),
        ("ceiling", "Floor-to-ceiling height at the decor area", "chips",
         [("lt9", "Under 9 ft"), ("9-10", "9–10 ft"), ("10-12", "10–12 ft"), ("12+", "12 ft+"), ("unsure", "Not sure")], True,
         ("ceiling_exact", "Exact height, if measured (e.g. 10 ft 6 in)", ["lt9", "9-10", "10-12", "12+"])),
        ("decor_width", "Width of the wall / space for the decor", "chips",
         [("lt8", "Under 8 ft"), ("8-12", "8–12 ft"), ("12-16", "12–16 ft"), ("16+", "16 ft+"), ("unsure", "Not sure")], True, None),
        ("plug_decor", "Normal plug point near the decor area", "chips",
         [("lt2", "Yes, within 2 m"), ("2-5", "Yes, 2–5 m away"), ("gt5", "Only 5 m+ away"), ("none", "No plug point")], True, None),
        ("plug16", "16 amp plug point (needed for LED decor and live T-shirt printing)", "chips",
         [("near_decor", "Yes, near the decor"), ("elsewhere", "Yes, somewhere else"), ("none", "No 16 amp point"),
          ("na", "Not needed for this party")], True,
         ("plug16_where", "Where exactly is it?", ["near_decor", "elsewhere"])),
        ("tables4", "Can 4 tables fit next to the 16 amp point? (live T-shirt printing)", "chips",
         [("yes", "Yes"), ("no", "No"), ("na", "Not needed for this party")], True, None),
        ("venue_tables", "Can the venue give us tables?", "chips",
         [("yes", "Yes"), ("no", "No, we bring our own"), ("unsure", "Not sure")], True,
         ("venue_tables_count", "How many?", ["yes"])),
        ("hanging", "Can we hang things from the ceiling?", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("decor_obstacles", "Anything in the way near the decor? (pillar, AC vent, fan, window behind)", "text", None, False, None),
    ]),
    ("Recce · Safety", [
        ("medkit", "First-aid / medical kit at the venue", "chips",
         [("yes", "Yes, venue has one"), ("no", "No — we must carry ours")], True,
         ("medkit_where", "Where is it kept?", ["yes"])),
        ("medkit_person", "Who is in charge of it on the day? (name and phone)", "short", None, True, None),
        ("hospital", "Nearest hospital / clinic and time to reach", "short", None, True, None),
        ("fire_exit", "Fire exits / emergency stairs checked?", "chips",
         [("yes", "Yes, noted"), ("no", "Couldn't find")], True, None),
        ("hazards", "Any dangers for kids nearby? (pool, balcony, steep stairs, glass, road)", "chips",
         [("none", "None"), ("yes", "Yes")], True,
         ("hazards_note", "What and where?", ["yes"])),
    ]),
    ("Recce · Shows, sound & team", [
        ("sound", "Music / sound rules", "chips",
         [("none", "No limits"), ("time", "Time limit"), ("volume", "Volume limit"), ("unsure", "Not sure")], True,
         ("sound_note", "Details (e.g. no music after 9 PM)", ["time", "volume"])),
        ("show_space", "Space for kids to sit on the floor in front of a show?", "chips",
         [("yes", "Yes"), ("tight", "Tight"), ("no", "No"), ("na", "No show booked")], True, None),
        ("team_room", "Room or corner for our team to keep bags and get ready?", "chips",
         [("yes", "Yes"), ("no", "No")], True, None),
        ("ac_control", "Can AC, fans and lights be controlled? (bubble show needs fans off)", "chips",
         [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")], True, None),
        ("walkthrough", "Full walkthrough video uploaded below?", "chips",
         [("yes", "Yes"), ("no", "Not yet")], True, None),
        ("recce_summary", "Summary and problems for the team", "text", None, False, None),
        ("recce_by", "Recce done by (your name)", "short", None, True, None),
    ]),
]
QUESTIONS = {q[0]: q for _s, qs in SECTIONS + RECCE_SECTIONS for q in qs}
FOLLOWUPS = {q[5][0]: q for q in QUESTIONS.values() if q[5]}
REQUIRED = [q[0] for _s, qs in SECTIONS for q in qs if q[4]]
RECCE_REQUIRED = [q[0] for _s, qs in RECCE_SECTIONS for q in qs if q[4]]
RECCE_KEYS = {q[0] for _s, qs in RECCE_SECTIONS for q in qs} | {q[5][0] for _s, qs in RECCE_SECTIONS for q in qs if q[5]}

TAGS = [("decor", "Decor"), ("dj", "DJ / music"), ("activity", "Activity area"), ("return_gifts", "Return gifts"),
        ("food", "Food"), ("cake", "Cake table"), ("entry", "Entry / welcome"), ("unloading", "Unloading / lift"),
        ("other", "Other")]
RECCE_TAGS = [("decor_front", "Decor – front"), ("decor_left", "Decor – left side"), ("decor_right", "Decor – right side"),
              ("decor_wide", "Wide – whole room"), ("plug", "Plug point"), ("plug16", "16 amp plug"),
              ("medical", "Medical kit"), ("walkthrough", "Walkthrough video")]
TAG_KEYS = [k for k, _ in TAGS + RECCE_TAGS]


def venue_url(token: str) -> str:
    return f"{SITE_BASE_URL}/venue.html?t={token}"


def _j(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def _first(s) -> str:
    return (str(s or "").split(",")[0]).strip()


async def _lead(lead_id: int) -> dict:
    r = await database.fetch_one(
        "SELECT lead_id, is_booking, parent_name, email, phone, child_names, child_ages, event_date, event_time, venue "
        "FROM leads WHERE lead_id = :id", values={"id": lead_id})
    if not r:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return dict(r)


async def ensure_venue_link(lead_id: int, by: Optional[str] = None) -> str:
    """The booking's venue form link, creating it the first time."""
    row = await database.fetch_one("SELECT token FROM venue_info WHERE lead_id = :id", values={"id": lead_id})
    if row:
        return venue_url(row["token"])
    tok = secrets.token_urlsafe(12)
    await database.execute(
        "INSERT INTO venue_info (lead_id, token, created_by) VALUES (:id, :t, :by) ON CONFLICT (lead_id) DO NOTHING",
        values={"id": lead_id, "t": tok, "by": (by or "")[:80] or None})
    row = await database.fetch_one("SELECT token FROM venue_info WHERE lead_id = :id", values={"id": lead_id})
    return venue_url(row["token"])


# ── Two-way sync with the booking (2026-10-31, per Shruti — "the information
# taken in this form should flow in the booking ... and vice versa. if the
# user has already input venue handover time and event start and end time -
# prefill it in this form"). The booking is the source of truth: what's on the
# booking is shown in the form, and anything the customer types here is
# written to the booking straight away (logged as "Customer (venue form)").
#   event_start <-> Event Time            (leads.event_time)
#   setup_from  <-> Venue Handover Time   (booking field / sales panel)
#   clear_by    <-> Packup Time           (booking field / sales panel)
#   event_end   <-> Event End Time        (sales panel playbook)
SYNC_WHO = "Customer (venue form)"


def _hhmm(v) -> Optional[str]:
    """'16:00', '16:00:00', '4:00 PM' or a time -> '16:00' (None if not a time)."""
    if v is None:
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?$", s)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ap == "PM" and h < 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}" if 0 <= h < 24 and 0 <= mi < 60 else None


async def booking_times(lead_id: int) -> dict:
    """The booking's current event start / end, handover and packup times."""
    out = {}
    lead = await database.fetch_one("SELECT event_time, venue_maps_link, location_type, venue, venue_contact_name, venue_contact_phone "
                                    "FROM leads WHERE lead_id = :id", values={"id": lead_id})
    for k, col in (("venue_address", "venue"), ("venue_contact_name", "venue_contact_name"), ("venue_contact_phone", "venue_contact_phone")):
        out[k] = ((lead[col] or "").strip() or None) if lead else None
    out["event_start"] = _hhmm(lead["event_time"]) if lead else None
    out["maps_link"] = ((lead["venue_maps_link"] or "").strip() or None) if lead else None
    lt = ((lead["location_type"] or "").strip() if lead else "")
    out["venue_type"] = lt if lt in {v for v, _ in QUESTIONS["venue_type"][3]} else None
    pb = None
    try:
        pb = await database.fetch_one(
            "SELECT event_end_time, venue_handover_time, packup_time, venue_type FROM lead_sales_playbook WHERE lead_id = :id",
            values={"id": lead_id})
    except Exception:
        pb = None
    out["event_end"] = _hhmm(pb["event_end_time"]) if pb else None
    # 2026-11-12, per Shruti — "if the client/sales team has filled in any
    # details earlier, please copy that in the form": the sales panel keeps
    # Venue Type on its own sheet, so use it when the booking has none.
    if not out.get("venue_type") and pb and pb["venue_type"] in {v for v, _ in QUESTIONS["venue_type"][3]}:
        out["venue_type"] = pb["venue_type"]
    for key, fk in (("setup_from", "venue_handover_time"), ("clear_by", "packup_time")):
        v = None
        try:
            ov = await database.fetch_one(
                "SELECT customer_choice_override, removed FROM booking_field_overrides WHERE lead_id = :id AND field_key = :k",
                values={"id": lead_id, "k": fk})
            if ov and not ov["removed"] and (ov["customer_choice_override"] or "").strip():
                v = _hhmm(ov["customer_choice_override"])
        except Exception:
            v = None
        if not v and pb:
            v = _hhmm(pb[fk])
        out[key] = v
    return out


async def _with_booking_times(lead_id: int, answers: dict) -> dict:
    a = dict(answers)
    for k, v in (await booking_times(lead_id)).items():
        if v:
            a[k] = v
    return a


async def push_times_to_booking(lead_id: int, answers: dict, keys, who: Optional[str] = None) -> None:
    """Writes the times the customer just gave into the booking."""
    from config import settings
    from routers.admin import update_booking_field, FieldUpdateRequest
    current = await booking_times(lead_id)
    for k in keys:
        v = (answers.get(k) or "").strip() if k in TEXT_SYNC else _hhmm(answers.get(k))
        if not v or v == current.get(k):
            continue
        # Sales-panel leads (not yet booked) read these from their own sheet:
        # keep it in step too, where the sheet exists (2026-11-12).
        pbcol = {"setup_from": "venue_handover_time", "clear_by": "packup_time", "venue_type": "venue_type"}.get(k)
        if pbcol:
            try:
                await database.execute(f"UPDATE lead_sales_playbook SET {pbcol} = :v WHERE lead_id = :id",
                                       values={"v": v, "id": lead_id})
            except Exception as exc:
                logger.warning(f"Lead #{lead_id}: venue form couldn't update the sales sheet's {pbcol} — {exc}")
        try:
            if k in TEXT_SYNC:
                await update_booking_field(lead_id, FieldUpdateRequest(
                    field_key=TEXT_SYNC[k], assigned_value=v, changed_by=who or SYNC_WHO), settings.ADMIN_PASSWORD)
            elif k == "event_start":
                await update_booking_field(lead_id, FieldUpdateRequest(
                    field_key="event_time", assigned_value=v, changed_by=who or SYNC_WHO), settings.ADMIN_PASSWORD)
            elif k in ("setup_from", "clear_by"):
                fk = "venue_handover_time" if k == "setup_from" else "packup_time"
                await update_booking_field(lead_id, FieldUpdateRequest(
                    field_key=fk, customer_choice_override=v, changed_by=who or SYNC_WHO), settings.ADMIN_PASSWORD)
            elif k == "event_end":
                n = await database.fetch_val("SELECT COUNT(*) FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
                # Only where a sales-panel sheet already exists — creating one
                # here would add the booking to the sales panel. Otherwise the
                # end time stays in the form's own answers.
                if n:
                    await database.execute("UPDATE lead_sales_playbook SET event_end_time = :v WHERE lead_id = :id",
                                           values={"v": v, "id": lead_id})
        except Exception as exc:   # e.g. a cancelled (locked) booking — the form still keeps the answer
            logger.warning(f"Lead #{lead_id}: venue form couldn't update {k} on the booking — {exc}")


SYNC_KEYS = ("event_start", "event_end", "setup_from", "clear_by", "maps_link", "venue_type",
             "venue_address", "venue_contact_name", "venue_contact_phone")
TEXT_SYNC = {"maps_link": "venue_maps_link", "venue_type": "location_type", "venue_address": "venue",
             "venue_contact_name": "venue_contact_name", "venue_contact_phone": "venue_contact_phone"}   # maps_link <-> Venue Maps Link


def _missing(answers: dict, keys=None) -> List[str]:
    out = []
    for k in (REQUIRED if keys is None else keys):
        if not str(answers.get(k) or "").strip():
            out.append(k)
    return out


def _label(key: str) -> str:
    q = QUESTIONS.get(key) or FOLLOWUPS.get(key)
    if key in FOLLOWUPS:
        return FOLLOWUPS[key][5][1]
    return q[1] if q else key


def _answer_text(key: str, val) -> str:
    q = QUESTIONS.get(key)
    if q and q[2] == "floormap":
        try:
            items = json.loads(val).get("items") or []
        except Exception:
            items = []
        return f"{len(items)} thing(s) marked on the map" if items else ""
    if q and q[3]:
        return dict(q[3]).get(val, str(val))
    if q and q[2] == "time":
        from routers.sales_leads import _fmt_time_12h
        return _fmt_time_12h(val) or str(val)
    return str(val)


def _booking_header(lead: dict) -> dict:
    from routers.sales_leads import _fmt_time_12h
    age = _first(lead.get("child_ages"))
    return {
        "lead_id": lead["lead_id"],
        "parent_name": (lead.get("parent_name") or "").strip(),
        "first_name": greeting_name(lead["parent_name"]) if lead.get("parent_name") else "",
        "child_name": _first(lead.get("child_names")),
        "child_age": age or None,
        "event_date": lead["event_date"].strftime("%a, %d %b %Y").replace(" 0", " ") if isinstance(lead.get("event_date"), date) else lead.get("event_date"),
        "event_time": _fmt_time_12h(lead.get("event_time")) if lead.get("event_time") else None,
        "venue": (lead.get("venue") or "").strip() or None,
    }


async def _media(lead_id: int, base: str) -> list:
    rows = await database.fetch_all(
        "SELECT id, kind, mime, filename, size_bytes, tags, caption, created_at FROM venue_media "
        "WHERE lead_id = :id ORDER BY id", values={"id": lead_id})
    return [{"id": r["id"], "kind": r["kind"], "mime": r["mime"], "filename": r["filename"],
             "size": r["size_bytes"], "tags": _j(r["tags"]) or [], "caption": r["caption"],
             "url": f"{base}/{r['id']}", "uploaded_at": _to_ist_str(r["created_at"])} for r in rows]


def _questions_out(recce: bool = False) -> list:
    out = []
    for title, qs in SECTIONS + (RECCE_SECTIONS if recce else []):
        out.append({"title": title, "team_only": title.startswith("Recce"), "questions": [
            {"key": k, "label": l, "type": t, "required": req,
             "options": [{"value": v, "label": ol} for v, ol in (opts or [])],
             "followup": ({"key": fu[0], "label": fu[1], "when": fu[2]} if fu else None)}
            for k, l, t, opts, req, fu in qs]})
    return out


def _range_response(data: bytes, mime: str, range_header: Optional[str]) -> Response:
    """Serves a file, honouring a single "bytes=a-b" range (Safari needs it for video)."""
    total = len(data)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    m = re.match(r"bytes=(\d*)-(\d*)$", (range_header or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else total - 1
        else:
            start = max(0, total - int(m.group(2)))
            end = total - 1
        end = min(end, total - 1)
        if start > end or start >= total:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(content=data[start:end + 1], status_code=206, media_type=mime, headers=headers)
    return Response(content=data, media_type=mime, headers=headers)


# ─── public ────────────────────────────────────────────────────────────────

async def _by_token(token: str) -> dict:
    try:
        row = await database.fetch_one("SELECT * FROM venue_info WHERE token = :t", values={"t": token})
    except Exception:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="This link isn't valid — please check the link we sent you.")
    return dict(row)


@router.get("/venue-info/{token}")
async def public_get(token: str, recce: bool = False):
    row = await _by_token(token)
    lead = await _lead(row["lead_id"])
    if not row["opened_at"]:
        await database.execute("UPDATE venue_info SET opened_at = NOW() WHERE id = :id", values={"id": row["id"]})
    answers = await _with_booking_times(row["lead_id"], _j(row["answers"]) or {})
    return {
        "booking": _booking_header(lead),
        "sections": _questions_out(recce),
        "answers": answers,
        "missing": _missing(answers),
        "recce": recce,
        "recce_missing": _missing(answers, RECCE_REQUIRED) if recce else [],
        "recce_at": answers.get("_recce_at"), "recce_by": answers.get("_recce_by"),
        "tags": [{"key": k, "label": l} for k, l in TAGS + (RECCE_TAGS if recce else [])],
        "media": await _media(row["lead_id"], f"/api/venue-info/{token}/media"),
        "limits": {"image_mb": MAX_IMAGE_BYTES // (1024 * 1024), "video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
                   "images": MAX_IMAGES, "videos": MAX_VIDEOS},
        "tnc_url": TNC_URL,
        "tnc_accepted": bool(row["tnc_accepted_at"]),
        "submitted_at": _to_ist_str(row["submitted_at"]),
    }


class VenueAnswers(BaseModel):
    answers: Dict[str, Optional[str]] = {}
    accept_tnc: Optional[bool] = None
    submit: bool = False
    recce: bool = False          # saved from the team's recce view (filled on the customer's behalf)
    recce_submit: bool = False   # "Save recce" button


def _clean_answers(raw: Dict[str, Optional[str]]) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        v = (str(v).strip() if v is not None else "")
        if k in QUESTIONS:
            q = QUESTIONS[k]
            if v and q[3] and v not in {o[0] for o in q[3]}:
                raise HTTPException(status_code=400, detail=f"Please pick one of the options for: {q[1]}")
            if v and q[2] == "time" and not re.fullmatch(r"\d{1,2}:\d{2}", v):
                raise HTTPException(status_code=400, detail=f"Please pick a time for: {q[1]}")
            if q[2] == "floormap":
                if v:
                    try:
                        fm = json.loads(v)
                        items = [{"k": str(i.get("k", ""))[:20], "l": str(i.get("l", ""))[:40],
                                  "x": max(0.0, min(1.0, float(i.get("x", 0)))), "y": max(0.0, min(1.0, float(i.get("y", 0))))}
                                 for i in (fm.get("items") or [])[:60]]
                        v = json.dumps({"shape": fm.get("shape") if fm.get("shape") in ("square", "wide", "long") else "wide",
                                        "items": items}, separators=(",", ":"))
                    except Exception:
                        raise HTTPException(status_code=400, detail="Couldn't read the floor map — please try again.")
                out[k] = v
                continue
            if v and q[2] == "url":
                m = re.search(r"https?://\S+", v)   # pasted share text often has words around the link
                if not m:
                    raise HTTPException(status_code=400, detail="Please paste the Google Maps link (it starts with https://).")
                v = m.group(0).rstrip(").,")
            out[k] = v[:1500]
        elif k in FOLLOWUPS:
            out[k] = v[:300]
    return out


@router.post("/venue-info/{token}")
async def public_save(token: str, body: VenueAnswers):
    row = await _by_token(token)
    answers = _j(row["answers"]) or {}
    cleaned = _clean_answers(body.answers)
    if not body.recce and any(k in RECCE_KEYS for k in cleaned):
        cleaned = {k: v for k, v in cleaned.items() if k not in RECCE_KEYS}
    answers.update(cleaned)
    if body.recce_submit:
        answers["_recce_at"] = _to_ist_str(datetime.now(timezone.utc))
        answers["_recce_by"] = (answers.get("recce_by") or "Team")[:80]
    answers = {k: v for k, v in answers.items() if v}
    who = f"{answers.get('recce_by') or 'Team'} (venue recce)" if body.recce else None
    await push_times_to_booking(row["lead_id"], answers, [k for k in SYNC_KEYS if cleaned.get(k)], who)
    answers = await _with_booking_times(row["lead_id"], answers)
    tnc = bool(row["tnc_accepted_at"]) if body.accept_tnc is None else bool(body.accept_tnc)
    if body.submit and not tnc and not body.recce:
        raise HTTPException(status_code=400, detail="Please tick that you've read the Terms & Conditions.")
    await database.execute(
        """UPDATE venue_info SET answers = CAST(:a AS JSONB), updated_at = NOW(),
                  tnc_accepted_at = CASE WHEN :tnc THEN COALESCE(tnc_accepted_at, NOW()) ELSE NULL END,
                  submitted_at = CASE WHEN :sub THEN NOW() ELSE submitted_at END
           WHERE id = :id""",
        values={"a": json.dumps(answers), "tnc": tnc, "sub": bool(body.submit), "id": row["id"]})
    if body.submit:
        logger.info(f"Lead #{row['lead_id']}: venue details submitted ({len(_missing(answers))} missing)")
    if body.recce_submit:
        logger.info(f"Lead #{row['lead_id']}: venue recce saved by {answers.get('_recce_by')}")
    return {"success": True, "answers": answers, "missing": _missing(answers), "tnc_accepted": tnc,
            "recce_missing": _missing(answers, RECCE_REQUIRED), "recce_at": answers.get("_recce_at")}


def _clean_tags(tags: str) -> list:
    return [t for t in TAG_KEYS if t in {x.strip() for x in (tags or "").split(",")}]


@router.post("/venue-info/{token}/media")
async def public_upload(token: str, file: UploadFile = File(...), tags: str = Form(""), caption: str = Form("")):
    row = await _by_token(token)
    mime = (file.content_type or "").lower()
    kind = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else None
    if not kind:
        raise HTTPException(status_code=400, detail="Please upload a photo or a video.")
    data = await file.read()
    cap = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    if len(data) > cap:
        raise HTTPException(status_code=413, detail=f"That {kind} is too large — up to {cap // (1024 * 1024)} MB please."
                            + (" Try a shorter clip." if kind == "video" else ""))
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    n = await database.fetch_val("SELECT COUNT(*) FROM venue_media WHERE lead_id = :id AND kind = :k",
                                 values={"id": row["lead_id"], "k": kind})
    if n >= (MAX_IMAGES if kind == "image" else MAX_VIDEOS):
        raise HTTPException(status_code=400, detail=f"You can add up to {MAX_IMAGES} photos and {MAX_VIDEOS} videos.")
    mid = await database.fetch_val(
        """INSERT INTO venue_media (lead_id, kind, mime, filename, size_bytes, data, tags, caption)
           VALUES (:id, :k, :m, :f, :s, :d, CAST(:t AS JSONB), :c) RETURNING id""",
        values={"id": row["lead_id"], "k": kind, "m": mime[:60], "f": (file.filename or "")[:120] or None,
                "s": len(data), "d": data, "t": json.dumps(_clean_tags(tags)), "c": (caption or "").strip()[:200] or None})
    await database.execute("UPDATE venue_info SET updated_at = NOW() WHERE id = :id", values={"id": row["id"]})
    media = await _media(row["lead_id"], f"/api/venue-info/{token}/media")
    return {"success": True, "id": mid, "media": media}


async def _media_row(lead_id: int, mid: int):
    r = await database.fetch_one("SELECT data, mime FROM venue_media WHERE id = :m AND lead_id = :id",
                                 values={"m": mid, "id": lead_id})
    if not r:
        raise HTTPException(status_code=404, detail="File not found.")
    return r


@router.get("/venue-info/{token}/media/{mid}")
async def public_media(token: str, mid: int, request: Request):
    row = await _by_token(token)
    r = await _media_row(row["lead_id"], mid)
    return _range_response(bytes(r["data"]), r["mime"], request.headers.get("range"))


class MediaEdit(BaseModel):
    tags: List[str] = []
    caption: Optional[str] = None


@router.post("/venue-info/{token}/media/{mid}")
async def public_media_edit(token: str, mid: int, body: MediaEdit):
    row = await _by_token(token)
    await _media_row(row["lead_id"], mid)
    await database.execute(
        "UPDATE venue_media SET tags = CAST(:t AS JSONB), caption = :c WHERE id = :m",
        values={"t": json.dumps(_clean_tags(",".join(body.tags or []))), "c": (body.caption or "").strip()[:200] or None, "m": mid})
    return {"success": True}


@router.delete("/venue-info/{token}/media/{mid}")
async def public_media_delete(token: str, mid: int):
    row = await _by_token(token)
    await database.execute("DELETE FROM venue_media WHERE id = :m AND lead_id = :id", values={"m": mid, "id": row["lead_id"]})
    return {"success": True}


# ─── admin ─────────────────────────────────────────────────────────────────

@router.get("/admin/bookings/{lead_id}/venue-info")
async def admin_get(lead_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    try:
        url = await ensure_venue_link(lead_id)
    except Exception:
        logger.exception("venue_info table missing (migration 080?)")
        raise HTTPException(status_code=500, detail="The venue form isn't set up yet — the server needs a restart to add its table.")
    row = dict(await database.fetch_one("SELECT * FROM venue_info WHERE lead_id = :id", values={"id": lead_id}))
    answers = await _with_booking_times(lead_id, _j(row["answers"]) or {})
    rows = []
    for title, qs in SECTIONS + RECCE_SECTIONS:
        for k, l, _t, _o, _req, fu in qs:
            v = answers.get(k)
            txt = _answer_text(k, v) if v else None
            if fu and answers.get(fu[0]) and v in fu[2]:
                txt = (txt or "") + " — " + answers[fu[0]]
            rows.append({"section": title, "key": k, "label": l, "answer": txt, "required": _req,
                         "team_only": title.startswith("Recce")})
    return {
        "url": url, "recce_url": url + "&recce=1", "booking": _booking_header(lead), "email": lead["email"], "phone": lead["phone"],
        "recce_at": answers.get("_recce_at"), "recce_by": answers.get("_recce_by"),
        "recce_missing": [_label(k) for k in _missing(answers, RECCE_REQUIRED)],
        "floor_map": answers.get("floor_map"),
        "rows": rows, "missing": [_label(k) for k in _missing(answers)],
        "answered": len(REQUIRED) - len(_missing(answers)), "total": len(REQUIRED),
        "tags": [{"key": k, "label": l} for k, l in TAGS + RECCE_TAGS],
        "media": await _media(lead_id, f"/api/admin/bookings/{lead_id}/venue-info/media"),
        "tnc_accepted_at": _to_ist_str(row["tnc_accepted_at"]),
        "opened_at": _to_ist_str(row["opened_at"]), "updated_at": _to_ist_str(row["updated_at"]),
        "submitted_at": _to_ist_str(row["submitted_at"]),
        "emailed_at": _to_ist_str(row["emailed_at"]), "whatsapp_at": _to_ist_str(row["whatsapp_at"]),
    }


@router.get("/admin/bookings/{lead_id}/venue-info/media/{mid}")
async def admin_media(lead_id: int, mid: int, request: Request, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    r = await _media_row(lead_id, mid)
    return _range_response(bytes(r["data"]), r["mime"], request.headers.get("range"))


def _email_html(first: str, child: str, url: str, hdr: dict) -> str:
    from routers.leads import MASCOT_URL, BRAND_PURPLE
    hi = f"Hi {first}," if first else "Hi,"
    party = f"{child}'s party" if child else "your party"
    when = " · ".join(x for x in [hdr.get("event_date"), hdr.get("event_time")] if x)
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#F5F0FF;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F0FF;padding:28px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(45,33,64,.08)">
<tr><td style="background:linear-gradient(135deg,#E65A96 0%,{BRAND_PURPLE} 100%);padding:26px;text-align:center">
<img src="{MASCOT_URL}" width="150" alt="" style="display:block;margin:0 auto 10px;border-radius:18px;background:#fff;padding:8px 12px">
<div style="font-family:Georgia,serif;font-size:21px;font-weight:700;color:#fff">A quick venue check for {party}</div></td></tr>
<tr><td style="padding:24px 26px;font-size:15px;line-height:1.6;color:#2D2140">
{hi}<br><br>To plan setup, timings and pack-up smoothly, please tell us a little about the venue —
timings, lift and parking, venue rules — and add a few photos of the space. It takes about 2 minutes,
and you can save and come back anytime.
<div style="margin:14px 0 0;font-size:13px;color:#6B6280">Booking #{hdr.get('lead_id')}{(' · ' + when) if when else ''}{(' · ' + hdr['venue']) if hdr.get('venue') else ''}</div>
<div style="text-align:center;margin:24px 0 8px">
<a href="{url}" style="display:inline-block;background:#E65A96;color:#fff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 28px;border-radius:999px">📍 Share venue details</a></div>
<div style="text-align:center;font-size:12px;color:#8B7FA0">Or open: <a href="{url}" style="color:{BRAND_PURPLE}">{url}</a></div>
</td></tr>
<tr><td style="padding:0 26px 24px;font-size:12.5px;color:#8B7FA0;text-align:center;border-top:1px solid #F0E9FA">
<br>Questions? +91 90044 35362 · +91 97422 40477</td></tr></table>
</td></tr></table></body></html>"""


class ChangedBy(BaseModel):
    changed_by: str = ""


@router.post("/admin/bookings/{lead_id}/venue-info/email")
async def admin_email(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    lead = await _lead(lead_id)
    if not lead["email"]:
        raise HTTPException(status_code=400, detail="This booking has no email on file.")
    url = await ensure_venue_link(lead_id, body.changed_by)
    from routers.leads import _gmail_send
    hdr = _booking_header(lead)
    child, first = hdr["child_name"], hdr["first_name"]
    subject = f"📍 Venue details for {child}'s party (Booking #{lead_id})" if child else f"📍 Venue details for your party (Booking #{lead_id})"
    text = (f"Hi {first},\n\n" if first else "Hi,\n\n") + \
        "To plan setup, timings and pack-up smoothly, please share a few details about the venue " \
        f"(about 2 minutes — you can save and come back anytime):\n{url}\n\n" \
        "Team Wondershop Experiences\n+91 90044 35362 · +91 97422 40477"
    try:
        await _gmail_send(lead["email"], subject, text, _email_html(first, child, url, hdr))
    except Exception as e:
        logger.exception(f"Lead #{lead_id}: venue form email failed")
        raise HTTPException(status_code=502, detail=f"Couldn't send the email: {e}")
    await database.execute("UPDATE venue_info SET emailed_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True, "sent_to": lead["email"]}


@router.post("/admin/bookings/{lead_id}/venue-info/whatsapp")
async def admin_whatsapp(lead_id: int, body: ChangedBy, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("UPDATE venue_info SET whatsapp_at = NOW() WHERE lead_id = :id", values={"id": lead_id})
    return {"success": True}
