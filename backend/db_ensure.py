"""
Small, idempotent schema top-ups applied on every startup (2026-10-06).

Production missed migration 024 (packing-list event date/time/venue), which
made "Save & get staff link" fail with a 500. The migrations listed here only
ADD missing columns / tables (IF NOT EXISTS), so running them again is
harmless; anything that fails is logged and skipped - startup never stops.
"""
import logging
import os
import re

from database import database

logger = logging.getLogger(__name__)

SAFE_MIGRATIONS = [
    "023_packaging_submit.sql",
    "024_packaging_event_details.sql",
    "040_to_be_confirmed.sql",
    "041_decor_reference_images.sql",
    "042_status_did_not_enquire.sql",
    "043_sales_call_log.sql",
    "044_decor_rate_cards.sql",
    "045_activity_ref_images.sql",
    "046_volunteer_profile.sql",
]


def _statements(sql: str):
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]


async def ensure_schema() -> None:
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
    for name in SAFE_MIGRATIONS:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                stmts = _statements(fh.read())
        except OSError:
            logger.warning(f"ensure_schema: {name} not found - skipped")
            continue
        for st in stmts:
            try:
                await database.execute(st)
            except Exception as exc:
                logger.warning(f"ensure_schema: {name}: {exc}")
    logger.info("ensure_schema: done")
    try:
        await rename_activities()
    except Exception as exc:
        logger.warning(f"rename_activities: {exc}")


async def rename_activities() -> None:
    """2026-10-08 — activities renamed in catalogue_data.ACTIVITY_RENAMES
    (inflatables now carry their size). Bookings store activities by NAME
    (svc_activities "A, B x2", its assignments "A: vendor; B: vendor", the
    To be confirmed keys "act:<name>") and sales leads keep a name next to
    the id, so old names are rewritten to the new ones. Exact-name matches
    only, so running it again changes nothing."""
    import json
    from catalogue_data import ACTIVITY_RENAMES as REN, ACTIVITIES
    if not REN:
        return
    by_id = {aid: n for aid, n, _p, _f in ACTIVITIES}

    def csv_names(v, sep):
        if not v:
            return v
        out = []
        for seg in v.split(sep):
            core = seg.strip()
            m = re.match(r"^(.*?)(\s+x\d+)?$", core, flags=re.I)
            name, qty = m.group(1), m.group(2) or ""
            if sep == ";" and ":" in core:
                name, rest = core.split(":", 1)
                out.append(REN.get(name.strip(), name.strip()) + ":" + rest)
                continue
            out.append(REN.get(name, name) + qty if core else seg)
        return (sep + " ").join(x.strip() for x in out if x.strip())

    n_changed = 0
    rows = await database.fetch_all(
        "SELECT id, customer_choice_override, assigned_value FROM booking_field_overrides "
        "WHERE field_key = 'svc_activities'")
    for r in rows:
        cc, av = r["customer_choice_override"], r["assigned_value"]
        new_cc, new_av = csv_names(cc, ","), csv_names(av, ";")
        if (new_cc or None) != (cc or None) or (new_av or None) != (av or None):
            await database.execute(
                "UPDATE booking_field_overrides SET customer_choice_override = :cc, assigned_value = :av WHERE id = :id",
                values={"cc": new_cc if cc is not None else None, "av": new_av if av is not None else None, "id": r["id"]})
            n_changed += 1
    try:
        rows = await database.fetch_all("SELECT lead_id, tbc_items FROM leads WHERE tbc_items IS NOT NULL")
    except Exception:
        rows = []
    for r in rows:
        st = r["tbc_items"]
        st = json.loads(st) if isinstance(st, str) else st
        if not isinstance(st, dict):
            continue
        new = {(f"act:{REN[k[4:]]}" if k.startswith("act:") and k[4:] in REN else k): v for k, v in st.items()}
        if new != st:
            await database.execute("UPDATE leads SET tbc_items = CAST(:v AS JSONB) WHERE lead_id = :id",
                                   values={"v": json.dumps(new), "id": r["lead_id"]})
            n_changed += 1
    rows = await database.fetch_all("SELECT lead_id, activities FROM lead_sales_playbook WHERE activities IS NOT NULL")
    for r in rows:
        acts = r["activities"]
        acts = json.loads(acts) if isinstance(acts, str) else acts
        if not isinstance(acts, list):
            continue
        changed = False
        for a in acts:
            if isinstance(a, dict) and a.get("name") in REN and not a.get("custom"):
                a["name"] = by_id.get(a.get("id")) or REN[a["name"]]
                changed = True
        if changed:
            await database.execute("UPDATE lead_sales_playbook SET activities = CAST(:v AS JSONB) WHERE lead_id = :id",
                                   values={"v": json.dumps(acts), "id": r["lead_id"]})
            n_changed += 1
    if n_changed:
        logger.info(f"rename_activities: updated {n_changed} row(s) to the new activity names")
