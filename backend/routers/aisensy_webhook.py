"""
Instagram ad leads from AiSensy -> Leads (2026-10-12, per Shruti).

  "We run Insta Ads on AISensy. When potential customers click on the ad,
   they are redirected to WhatsApp and we receive a WhatsApp from them with
   their names and number ... I want the name and number along with the
   lead generation date to directly flow into the Admin Panel Lead
   Management System so that my team can directly pick up the leads from
   there." Captured: Lead Generation Date + Time, Name, Phone Number,
   Lead Source ("Insta"), Lead Source Platform ("AISensy"), Ad shown.

How it works
  AiSensy calls POST /api/integrations/aisensy/webhook?token=<secret> for
  WhatsApp events (set up once in AiSensy -> Developer/Integrations ->
  Webhooks; see TASKS.md). For an INCOMING message from a number we don't
  already have an open lead for, this creates:
    * a row in `leads` — lead_origin='sales_module', lead_source='Insta',
      lead_source_platform='AISensy', ad_shown/ad_id/ad_source_url from the
      Click-to-WhatsApp ad details AiSensy passes along, lead_generated_at
      (= created_on) = when they messaged, status 'New', no sales lead yet;
    * its lead_sales_playbook row, so it opens in the Sales Quotation Module
      (call log, quotation, convert to booking) like any lead the team
      registered — and therefore shows in BOTH the admin Leads tab and the
      Sales module list, with their "Instagram" filter.
  Then the Google Sheet row is written (sheet_sync), same as any other lead.

Not a new lead (logged as "duplicate", nothing created) when the number
already has: an open lead, an upcoming booking, or any lead from the last 30
days — each message in a WhatsApp chat fires the webhook again, so this is
what keeps one person = one lead. If they click a (new) ad again, that's
noted in the lead's edit history. Known partner (vendor) numbers and
anything that isn't an incoming customer message (delivery/read receipts,
our own replies, broadcasts) are ignored.

AiSensy's exact JSON isn't published in a fixed form, so fields are found by
name anywhere in the payload (AiSensy's own "topic"/"data" shape and Meta's
raw WhatsApp "entry/changes/value" shape both work). Every call is kept in
aisensy_webhook_log for 60 days with the raw payload and what happened —
GET /api/admin/integrations/aisensy/log (admin login) shows the latest, so
if a field ever comes through empty we can see what AiSensy actually sent.

The webhook always answers 200 once the token is right (even if one message
couldn't be processed) so AiSensy never retries in a loop; failures are in
the log.
"""
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException, Query, Request

from config import settings
from database import database
import sheet_sync
from routers.admin import _require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)
CREATED_BY = "AISensy (Instagram ad)"
CLOSED_STATUSES = ("Not Interested", "DND", "Did not Enquire", "Completed", "Cancelled")
RECENT_DAYS = 30            # any lead this recent with the same number = same person
LOG_KEEP_DAYS = 60

# ─── payload reading ────────────────────────────────────────────────────────

PHONE_KEYS = ("wa_id", "waId", "from", "phone_number", "phoneNumber", "phone", "mobile",
              "mobile_number", "mobileNumber", "user_number", "userNumber", "contact_number",
              "customer_number", "sender_phone")
NAME_KEYS = ("userName", "user_name", "username", "contact_name", "contactName", "full_name",
             "fullName", "customer_name", "customerName", "profile_name", "profileName", "pushName")
NAME_PARENTS = ("profile", "contact", "user", "customer", "sender", "contacts")
TIME_KEYS = ("timestamp", "created_at", "createdAt", "sent_at", "sentAt", "received_at",
             "receivedAt", "time", "date")
REFERRAL_KEYS = ("referral", "ad", "ad_data", "adData", "ad_referral", "adReferral", "ctwa",
                 "ctwa_referral", "ctwaReferral", "ad_details", "adDetails")
TEXT_KEYS = ("text", "body", "message_content", "messageContent", "content", "message")
INBOUND_TOPICS = ("message.sender.user", "contact.created", "message.received", "message_received",
                  "incoming_message", "incoming", "contact_created", "new_contact", "user_message")
INBOUND_SENDERS = ("user", "customer", "incoming", "inbound", "contact", "end_user")
OUTBOUND_SENDERS = ("agent", "bot", "system", "business", "outgoing", "outbound", "api",
                    "campaign", "broadcast", "operator", "admin", "chatbot", "flow")
SENDER_KEYS = ("sender", "sender_type", "senderType", "from_type", "fromType", "direction",
               "message_direction", "author_type", "authorType", "sent_by", "sentBy")


def _walk(obj, parent: str = "") -> Iterable[Tuple[str, dict]]:
    """Every dict inside obj, with the key it was found under."""
    if isinstance(obj, dict):
        yield parent, obj
        for k, v in obj.items():
            yield from _walk(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, parent)


def _str(v) -> str:
    return v.strip() if isinstance(v, str) else (str(v) if isinstance(v, (int, float)) else "")


def _digits(v) -> str:
    return re.sub(r"\D", "", _str(v))


def normalise_phone(raw) -> Optional[str]:
    """Indian numbers -> 10 digits (how the website stores them, so the same
    person matches across sources); anything else -> +<country code><number>."""
    d = _digits(raw)
    if len(d) == 12 and d.startswith("91"):
        return d[2:]
    if len(d) == 11 and d.startswith("0"):
        return d[1:]
    if len(d) == 10:
        return d
    if 11 <= len(d) <= 15:
        return "+" + d
    return None


def _find_phone(payload) -> Optional[str]:
    for _p, d in _walk(payload):
        for k in PHONE_KEYS:
            if k in d and not isinstance(d[k], (dict, list)):
                ph = normalise_phone(d[k])
                if ph:
                    return ph
    return None


def _find_name(payload) -> Optional[str]:
    for _p, d in _walk(payload):
        for k in NAME_KEYS:
            v = _str(d.get(k))
            if v:
                return v[:255]
    for parent, d in _walk(payload):
        if parent in NAME_PARENTS or any(k in d for k in PHONE_KEYS):
            v = _str(d.get("name"))
            if v and not re.fullmatch(r"[\d\s+().-]+", v):   # not just a number
                return v[:255]
    return None


def _parse_time(v) -> Optional[datetime]:
    if v is None or isinstance(v, (dict, list, bool)):
        return None
    s = _str(v)
    if not s:
        return None
    if re.fullmatch(r"\d{9,13}(\.\d+)?", s):
        n = float(s)
        if n > 1e12:
            n /= 1000.0
        return datetime.fromtimestamp(n, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:          # AiSensy's naive times are taken as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _find_time(payload) -> datetime:
    now = datetime.now(timezone.utc)
    for _p, d in _walk(payload):
        for k in TIME_KEYS:
            dt = _parse_time(d.get(k))
            # a value way off (bad parse, test payload) -> use arrival time
            if dt and now - timedelta(days=7) <= dt <= now + timedelta(hours=1):
                return dt
    return now


def _find_referral(payload) -> Dict[str, Optional[str]]:
    """The Click-to-WhatsApp ad the person came from (Meta passes it along
    with their first message as `referral`: headline, body, source_id = ad
    ID, source_url, source_type 'ad')."""
    ref: Dict[str, Any] = {}
    for parent, d in _walk(payload):
        if parent in REFERRAL_KEYS and d:
            ref = d
            break
    pick = lambda *ks: next((_str(ref.get(k)) for k in ks if _str(ref.get(k))), None)
    out = {
        "ad_name": pick("ad_name", "adName", "ad_title", "adTitle", "name", "campaign_name", "campaignName"),
        "headline": pick("headline", "title"),
        "body": pick("body", "description", "text"),
        "ad_id": pick("source_id", "sourceId", "ad_id", "adId", "id"),
        "source_url": pick("source_url", "sourceUrl", "url", "link"),
        "source_type": pick("source_type", "sourceType", "type"),
    }
    # Some BSPs flatten the ad name onto the message/contact itself.
    if not out["ad_name"]:
        for _p, d in _walk(payload):
            v = _str(d.get("ad_name") or d.get("adName") or d.get("ctwa_ad_name"))
            if v:
                out["ad_name"] = v
                break
    out["present"] = bool(ref) or bool(out["ad_name"])
    return out


def ad_shown_text(ref: Dict[str, Optional[str]]) -> Optional[str]:
    t = ref.get("ad_name") or ref.get("headline") or (ref.get("body") or "")[:200] or None
    if not t and ref.get("ad_id"):
        t = f"Ad #{ref['ad_id']}"
    return t[:500] if t else None


def _find_text(payload) -> Optional[str]:
    for parent, d in _walk(payload):
        if parent in REFERRAL_KEYS:
            continue
        for k in TEXT_KEYS:
            v = d.get(k)
            if isinstance(v, dict):
                v = v.get("body") or v.get("text")
            v = _str(v)
            if v:
                return v[:300]
    return None


def _topic(payload) -> str:
    if isinstance(payload, dict):
        for k in ("topic", "event", "event_type", "eventType", "type"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def classify(payload) -> Tuple[bool, str]:
    """(is an incoming customer message/new contact?, reason)."""
    topic = _topic(payload).lower()
    if "status" in topic or topic in ("message.delivered", "message.read", "message.sent", "message.failed"):
        return False, f"status update ({topic})"
    if isinstance(payload, dict) and payload.get("_meta_statuses_only"):
        return False, "status update"
    for _p, d in _walk(payload):
        for k in SENDER_KEYS:
            v = _str(d.get(k)).lower()
            if not v:
                continue
            if v in OUTBOUND_SENDERS or v.startswith(("agent", "bot")):
                return False, f"sent by us ({k}={v})"
            if v in INBOUND_SENDERS:
                return True, f"{k}={v}"
    if topic in INBOUND_TOPICS or ".sender.user" in topic or topic.endswith("contact.created"):
        return True, topic
    if isinstance(payload, dict) and payload.get("_meta_message"):
        return True, "WhatsApp message"
    if _find_referral(payload)["present"]:
        return True, "carries ad details"
    return False, f"not an incoming customer message (topic '{topic or '-'}')"


def split_events(payload) -> List[Any]:
    """Meta's raw format batches several messages in one call; AiSensy's
    sends one event per call. Returns one payload per event."""
    if isinstance(payload, list):
        out = []
        for p in payload:
            out.extend(split_events(p))
        return out
    if isinstance(payload, dict) and isinstance(payload.get("entry"), list):
        out = []
        for entry in payload["entry"]:
            for ch in (entry or {}).get("changes") or []:
                val = (ch or {}).get("value") or {}
                msgs = val.get("messages") or []
                for m in msgs:
                    out.append({"_meta_message": True, "contacts": val.get("contacts") or [], "messages": [m]})
                if not msgs and val.get("statuses"):
                    out.append({"_meta_statuses_only": True, "statuses": val.get("statuses")})
        return out or [payload]
    return [payload]


# ─── helpers ────────────────────────────────────────────────────────────────

def _ist(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return (dt + IST_OFFSET).strftime("%d %b %Y, %I:%M %p") + " IST"


_calls = 0


async def _log_call(topic, phone, lead_id, outcome, detail, payload) -> None:
    global _calls
    try:
        raw = json.dumps(payload, default=str)
        if len(raw) > 100_000:
            raw = json.dumps({"truncated": raw[:100_000]})
        await database.execute(
            "INSERT INTO aisensy_webhook_log (topic, phone, lead_id, outcome, detail, payload) "
            "VALUES (:t, :p, :l, :o, :d, CAST(:pl AS JSONB))",
            values={"t": (topic or None) and topic[:100], "p": phone, "l": lead_id, "o": outcome,
                    "d": (detail or "")[:1000] or None, "pl": raw},
        )
        _calls += 1
        if _calls % 200 == 1:
            await database.execute(
                f"DELETE FROM aisensy_webhook_log WHERE received_at < NOW() - INTERVAL '{LOG_KEEP_DAYS} days'")
    except Exception:
        logger.exception("AiSensy webhook: couldn't write the log row")


async def _is_partner(phone: str) -> bool:
    last10 = _digits(phone)[-10:]
    try:
        row = await database.fetch_one(
            "SELECT 1 FROM vendor_master WHERE RIGHT(regexp_replace(COALESCE(primary_mobile,''), '\\D', '', 'g'), 10) = :p "
            "OR RIGHT(regexp_replace(COALESCE(alternate_mobile,''), '\\D', '', 'g'), 10) = :p LIMIT 1",
            values={"p": last10})
        return bool(row)
    except Exception:
        return False


async def _existing_lead(phone: str):
    """The lead this number already belongs to, if it should NOT get a new one."""
    return await database.fetch_one(
        f"""SELECT lead_id, lead_origin, lead_source_platform, ad_shown FROM leads
            WHERE RIGHT(regexp_replace(COALESCE(phone,''), '\\D', '', 'g'), 10) = :p
              AND (
                    (NOT is_booking AND status NOT IN ({", ".join(f"'{s}'" for s in CLOSED_STATUSES)}))
                 OR (is_booking AND status <> 'Cancelled' AND (event_date IS NULL OR event_date >= CURRENT_DATE))
                 OR created_on >= NOW() - INTERVAL '{RECENT_DAYS} days'
              )
            ORDER BY created_on DESC LIMIT 1""",
        values={"p": _digits(phone)[-10:]},
    )


async def _playbook_id(lead_id: int) -> Optional[int]:
    row = await database.fetch_one("SELECT id FROM lead_sales_playbook WHERE lead_id = :id", values={"id": lead_id})
    return row["id"] if row else None


async def _playbook_log(pid: Optional[int], action: str, detail: str) -> None:
    if pid:
        await database.execute(
            "INSERT INTO lead_sales_playbook_log (playbook_id, actor, action, detail) VALUES (:pid, :a, :ac, :d)",
            values={"pid": pid, "a": CREATED_BY, "ac": action, "d": detail[:2000]})


# ─── processing one event ──────────────────────────────────────────────────

async def process_event(event) -> Dict[str, Any]:
    topic = _topic(event)
    phone = _find_phone(event)
    inbound, why = classify(event)
    if not inbound:
        await _log_call(topic, phone, None, "ignored", why, event)
        return {"outcome": "ignored", "reason": why}
    if not phone:
        await _log_call(topic, None, None, "ignored", "no phone number found in the payload", event)
        return {"outcome": "ignored", "reason": "no phone number"}

    ref = _find_referral(event)
    ad = ad_shown_text(ref)
    if settings.AISENSY_REQUIRE_AD and not ref["present"]:
        await _log_call(topic, phone, None, "ignored", "no ad details (AISENSY_REQUIRE_AD is on)", event)
        return {"outcome": "ignored", "reason": "not from an ad"}
    if await _is_partner(phone):
        await _log_call(topic, phone, None, "ignored", "number belongs to a partner (vendor)", event)
        return {"outcome": "ignored", "reason": "partner number"}

    name = _find_name(event)
    generated_at = _find_time(event)
    first_text = _find_text(event)

    async with database.transaction():
        # One webhook per message, and AiSensy can send two for the same
        # first message (message + new contact) at the same moment — this
        # lock makes the second wait and then see the first one's lead.
        await database.execute("SELECT pg_advisory_xact_lock(hashtext(:k))", values={"k": "aisensy:" + phone})
        existing = await _existing_lead(phone)
        if existing:
            lead_id = existing["lead_id"]
            note = None
            if ref["present"]:
                if existing["lead_source_platform"] == settings.AISENSY_LEAD_PLATFORM and not existing["ad_shown"] and ad:
                    await database.execute(
                        "UPDATE leads SET ad_shown = :a, ad_id = :i, ad_source_url = :u WHERE lead_id = :id",
                        values={"a": ad, "i": ref.get("ad_id"), "u": ref.get("source_url"), "id": lead_id})
                note = f"Messaged again on WhatsApp after clicking an Instagram ad{(': ' + ad) if ad else ''}"
                await _playbook_log(await _playbook_id(lead_id), "updated", note)
            result = {"outcome": "duplicate", "lead_id": lead_id}
            detail = f"already lead #{lead_id}" + (f" — {note}" if note else "")
        else:
            lead_id = await database.execute(
                """INSERT INTO leads
                     (parent_name, phone, lead_origin, lead_source, lead_source_detail, lead_source_platform,
                      ad_shown, ad_id, ad_source_url, lead_generated_at, created_on, status, is_booking)
                   VALUES
                     (:name, :phone, 'sales_module', :src, :detail, :platform,
                      :ad, :ad_id, :ad_url, :gen, :gen, 'New', FALSE)
                   RETURNING lead_id""",
                values={
                    "name": name or "Instagram lead (name not shared)",
                    "phone": phone,
                    "src": settings.AISENSY_LEAD_SOURCE,
                    # Shown in the Google Sheet's "Lead Source Detail" column.
                    "detail": (settings.AISENSY_LEAD_PLATFORM + (f" · Ad: {ad}" if ad else ""))[:255],
                    "platform": settings.AISENSY_LEAD_PLATFORM,
                    "ad": ad, "ad_id": (ref.get("ad_id") or None) and ref["ad_id"][:100],
                    "ad_url": ref.get("source_url"),
                    "gen": generated_at,
                },
            )
            pid = await database.execute(
                "INSERT INTO lead_sales_playbook (lead_id, created_by) VALUES (:id, :by) RETURNING id",
                values={"id": lead_id, "by": CREATED_BY})
            bits = [f"New lead from {settings.AISENSY_LEAD_SOURCE} via {settings.AISENSY_LEAD_PLATFORM}"]
            if ad:
                bits.append(f"Ad shown: {ad}")
            if first_text:
                bits.append(f"First message: “{first_text}”")
            await _playbook_log(pid, "created", " · ".join(bits))
            result = {"outcome": "created", "lead_id": lead_id}
            detail = f"created lead #{lead_id}" + (f" (ad: {ad})" if ad else " (no ad details in payload)")

    await _log_call(topic, phone, lead_id, result["outcome"], detail, event)
    if result["outcome"] == "created":
        logger.info(f"AiSensy: new Instagram lead #{lead_id} ({phone})")
        sheet_sync.schedule_sync(lead_id)
    return result


# ─── endpoints ─────────────────────────────────────────────────────────────

def _token_ok(token: Optional[str]) -> bool:
    secret = settings.AISENSY_WEBHOOK_TOKEN
    return bool(secret and token) and hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8"))


@router.get("/integrations/aisensy/webhook")
async def webhook_check(token: Optional[str] = Query(None), x_webhook_token: Optional[str] = Header(None),
                        hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
                        hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")):
    """Some webhook set-up screens 'ping' the URL first (and Meta-style ones
    echo back hub.challenge)."""
    if not settings.AISENSY_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="AiSensy webhook is not configured.")
    if not (_token_ok(token) or _token_ok(x_webhook_token) or _token_ok(hub_verify_token)):
        raise HTTPException(status_code=401, detail="Wrong token.")
    if hub_challenge:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(hub_challenge)
    return {"ok": True}


@router.post("/integrations/aisensy/webhook")
async def webhook(request: Request, token: Optional[str] = Query(None),
                  x_webhook_token: Optional[str] = Header(None)):
    if not settings.AISENSY_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="AiSensy webhook is not configured.")
    if not (_token_ok(token) or _token_ok(x_webhook_token)):
        raise HTTPException(status_code=401, detail="Wrong token.")
    try:
        payload = await request.json()
    except Exception:
        try:
            payload = dict(await request.form())
        except Exception:
            payload = {"raw": (await request.body()).decode("utf-8", "replace")[:20000]}

    results = []
    for event in split_events(payload):
        try:
            results.append(await process_event(event))
        except Exception as exc:
            logger.exception("AiSensy webhook: couldn't process an event")
            await _log_call(_topic(event), _find_phone(event), None, "error", repr(exc), event)
            results.append({"outcome": "error"})
    return {"ok": True, "results": results}


@router.get("/admin/integrations/aisensy/log")
async def webhook_log(limit: int = 50, outcome: Optional[str] = None,
                      x_admin_password: Optional[str] = Header(None)):
    """Latest webhook calls with their raw payloads (admin login only)."""
    if _require_admin(x_admin_password) != "admin":
        raise HTTPException(status_code=403, detail="Admin login only.")
    where, values = "", {"lim": max(1, min(limit, 500))}
    if outcome:
        where, values["o"] = "WHERE outcome = :o", outcome
    rows = await database.fetch_all(
        f"SELECT * FROM aisensy_webhook_log {where} ORDER BY received_at DESC LIMIT :lim", values=values)
    out = []
    for r in rows:
        d = dict(r)
        pl = d.get("payload")
        out.append({
            "id": d["id"], "received_at": _ist(d["received_at"]), "topic": d["topic"], "phone": d["phone"],
            "lead_id": d["lead_id"], "outcome": d["outcome"], "detail": d["detail"],
            "payload": json.loads(pl) if isinstance(pl, str) else pl,
        })
    return {"configured": bool(settings.AISENSY_WEBHOOK_TOKEN), "rows": out}
