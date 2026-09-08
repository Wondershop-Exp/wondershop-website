"""
Packaging assist module (2026-09-08, per Shruti).

Digitizes the packing list she currently types per confirmed party and
sends over WhatsApp, with staff manually checking items off (she'd been
marking these by hand with ✅ inline in the WhatsApp text). See the
migration (020_packaging_module.sql) header for the full design rationale
— short version: these lists are bespoke per event (ad hoc headers,
numbered activity "stations", hand-written quantities/colours), so this is
a paste-and-parse digitization of Shruti's real format, not an
auto-composed-from-catalogue system. A reusable snippet library
(packaging_templates) lets recurring blocks get dropped in instead of
retyped.

Two very different trust models share this file:
  - /admin/packaging/... — team-only, same shared-password gate as the rest
    of admin.html (_require_admin, reused from routers.admin).
  - /pack/{share_token} — the staff-facing tablet endpoints. No login: the
    long random share_token IS the access control, same trust level as
    the WhatsApp link Shruti sends today. Never list/enumerate packaging
    lists from this side — only ever look one up by its exact token.

Quantities + remarks (2026-09-08, migration 021): each item can carry an
optional qty (set by whoever composes the list, shown as a badge) and a
free-text remark (left by staff from the tablet view — "didn't find this",
"packed something different"). Remarks are edited only via the dedicated
/pack/.../remark endpoint below; the admin composer shows them read-only
and they survive re-saves of the list content the same way checked state
does (matched by section header + item text in _write_sections).
"""
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import database
from routers.admin import _require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


def _to_ist_str(dt) -> Optional[str]:
    if not dt:
        return None
    ist = dt + IST_OFFSET
    return ist.strftime("%d %b %Y, %I:%M %p") + " IST"


# ─── request/response models ──────────────────────────────────────────────

class TemplateIn(BaseModel):
    name: str
    category: str = "other"
    items: List[str] = []
    created_by: Optional[str] = None


class ItemIn(BaseModel):
    text: str
    checked: bool = False
    qty: Optional[int] = None


class SectionIn(BaseModel):
    header: str
    items: List[ItemIn] = []


class ListCreateIn(BaseModel):
    title: str
    lead_id: Optional[int] = None
    event_lead: Optional[str] = None
    sections: List[SectionIn] = []
    created_by: Optional[str] = None


class ListMetaIn(BaseModel):
    title: Optional[str] = None
    event_lead: Optional[str] = None


class ListContentIn(BaseModel):
    sections: List[SectionIn] = []
    updated_by: Optional[str] = None


class CheckIn(BaseModel):
    checked: bool
    checked_by: Optional[str] = None


class RemarkIn(BaseModel):
    remark: str = ""
    remark_by: Optional[str] = None


# ─── templates (admin) ────────────────────────────────────────────────────

@router.get("/admin/packaging/templates")
async def list_templates(x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    rows = await database.fetch_all("SELECT * FROM packaging_templates ORDER BY category, name")
    out = []
    for r in rows:
        d = dict(r)
        items = d.get("items")
        d["items"] = json.loads(items) if isinstance(items, str) else (items or [])
        out.append(d)
    return {"templates": out}


@router.post("/admin/packaging/templates")
async def create_template(body: TemplateIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Template name is required.")
    tid = await database.execute(
        """INSERT INTO packaging_templates (name, category, items, created_by)
           VALUES (:name, :category, :items, :created_by) RETURNING id""",
        values={"name": body.name.strip(), "category": body.category or "other",
                "items": json.dumps(body.items), "created_by": body.created_by},
    )
    return {"id": tid}


@router.put("/admin/packaging/templates/{template_id}")
async def update_template(template_id: int, body: TemplateIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one("SELECT id FROM packaging_templates WHERE id = :id", values={"id": template_id})
    if not row:
        raise HTTPException(status_code=404, detail="Template not found.")
    await database.execute(
        """UPDATE packaging_templates SET name = :name, category = :category,
           items = :items, updated_at = NOW() WHERE id = :id""",
        values={"id": template_id, "name": body.name.strip(), "category": body.category or "other",
                "items": json.dumps(body.items)},
    )
    return {"ok": True}


@router.delete("/admin/packaging/templates/{template_id}")
async def delete_template(template_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("DELETE FROM packaging_templates WHERE id = :id", values={"id": template_id})
    return {"ok": True}


# ─── lists (admin) ──────────────────────────────────────────────────────────

async def _full_list(list_id: int) -> Optional[dict]:
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE id = :id", values={"id": list_id})
    if not lst:
        return None
    return await _hydrate(lst)


async def _hydrate(lst) -> dict:
    d = dict(lst)
    sections = await database.fetch_all(
        "SELECT * FROM packaging_sections WHERE packaging_list_id = :lid ORDER BY sort_order, id",
        values={"lid": d["id"]},
    )
    sec_out = []
    total = 0
    checked_count = 0
    for s in sections:
        items = await database.fetch_all(
            "SELECT * FROM packaging_items WHERE section_id = :sid ORDER BY sort_order, id",
            values={"sid": s["id"]},
        )
        item_dicts = []
        for it in items:
            idd = dict(it)
            idd["checked_at"] = _to_ist_str(idd.get("checked_at"))
            idd["remark_at"] = _to_ist_str(idd.get("remark_at"))
            item_dicts.append(idd)
            total += 1
            if idd["checked"]:
                checked_count += 1
        sec_out.append({"id": s["id"], "header": s["header"], "sort_order": s["sort_order"], "items": item_dicts})
    d["sections"] = sec_out
    d["created_at"] = _to_ist_str(d.get("created_at"))
    d["updated_at"] = _to_ist_str(d.get("updated_at"))
    d["progress"] = {"checked": checked_count, "total": total}
    d["share_url"] = f"/pack.html?t={d['share_token']}"
    return d


@router.get("/admin/packaging/lists")
async def list_packaging_lists(search: Optional[str] = None, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if search:
        rows = await database.fetch_all(
            "SELECT * FROM packaging_lists WHERE title ILIKE :q ORDER BY created_at DESC LIMIT 100",
            values={"q": f"%{search}%"},
        )
    else:
        rows = await database.fetch_all("SELECT * FROM packaging_lists ORDER BY created_at DESC LIMIT 100")
    out = []
    for r in rows:
        d = dict(r)
        counts = await database.fetch_one(
            """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE i.checked) AS checked
               FROM packaging_items i JOIN packaging_sections s ON i.section_id = s.id
               WHERE s.packaging_list_id = :lid""",
            values={"lid": d["id"]},
        )
        d["progress"] = {"checked": counts["checked"], "total": counts["total"]}
        d["created_at"] = _to_ist_str(d.get("created_at"))
        d["share_url"] = f"/pack.html?t={d['share_token']}"
        out.append(d)
    return {"lists": out}


@router.post("/admin/packaging/lists")
async def create_list(body: ListCreateIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title is required.")
    token = secrets.token_urlsafe(18)
    list_id = await database.execute(
        """INSERT INTO packaging_lists (lead_id, title, event_lead, share_token, created_by)
           VALUES (:lead_id, :title, :event_lead, :token, :created_by) RETURNING id""",
        values={"lead_id": body.lead_id, "title": body.title.strip(), "event_lead": body.event_lead,
                "token": token, "created_by": body.created_by},
    )
    await _write_sections(list_id, body.sections, merge=False)
    return await _full_list(list_id)


@router.get("/admin/packaging/lists/{list_id}")
async def get_list(list_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    d = await _full_list(list_id)
    if not d:
        raise HTTPException(status_code=404, detail="Packaging list not found.")
    return d


@router.put("/admin/packaging/lists/{list_id}/meta")
async def update_list_meta(list_id: int, body: ListMetaIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one("SELECT id FROM packaging_lists WHERE id = :id", values={"id": list_id})
    if not row:
        raise HTTPException(status_code=404, detail="Packaging list not found.")
    sets, values = [], {"id": list_id}
    if body.title is not None:
        sets.append("title = :title"); values["title"] = body.title.strip()
    if body.event_lead is not None:
        sets.append("event_lead = :event_lead"); values["event_lead"] = body.event_lead
    if sets:
        sets.append("updated_at = NOW()")
        await database.execute(f"UPDATE packaging_lists SET {', '.join(sets)} WHERE id = :id", values=values)
    return await _full_list(list_id)


async def _write_sections(list_id: int, sections: List[SectionIn], merge: bool):
    """Replaces a list's whole section/item tree. When merge=True (editing
    an existing list, per PUT /lists/{id}/content below), carries over
    checked/checked_by/checked_at AND remark/remark_by/remark_at for any
    item whose text matches (case/whitespace-insensitive) an existing item
    under a section with the same header — so re-saving an edited list
    doesn't wipe out packing progress or staff notes already made on the
    unchanged items."""
    prior = {}
    if merge:
        existing_sections = await database.fetch_all(
            "SELECT * FROM packaging_sections WHERE packaging_list_id = :lid", values={"lid": list_id},
        )
        for s in existing_sections:
            items = await database.fetch_all(
                "SELECT * FROM packaging_items WHERE section_id = :sid", values={"sid": s["id"]},
            )
            key_header = (s["header"] or "").strip().lower()
            for it in items:
                key = (key_header, (it["text"] or "").strip().lower())
                prior[key] = {
                    "checked": it["checked"], "checked_by": it["checked_by"], "checked_at": it["checked_at"],
                    "remark": it["remark"], "remark_by": it["remark_by"], "remark_at": it["remark_at"],
                }
        await database.execute("DELETE FROM packaging_sections WHERE packaging_list_id = :lid", values={"lid": list_id})
    else:
        await database.execute("DELETE FROM packaging_sections WHERE packaging_list_id = :lid", values={"lid": list_id})

    for si, sec in enumerate(sections):
        header = (sec.header or "").strip() or "Items"
        sec_id = await database.execute(
            "INSERT INTO packaging_sections (packaging_list_id, header, sort_order) VALUES (:lid, :h, :o) RETURNING id",
            values={"lid": list_id, "h": header, "o": si},
        )
        key_header = header.lower()
        for ii, item in enumerate(sec.items):
            text = (item.text or "").strip()
            if not text:
                continue
            carry = prior.get((key_header, text.lower())) if merge else None
            checked = carry["checked"] if carry else item.checked
            checked_by = carry["checked_by"] if carry else None
            checked_at = carry["checked_at"] if carry else None
            remark = carry["remark"] if carry else None
            remark_by = carry["remark_by"] if carry else None
            remark_at = carry["remark_at"] if carry else None
            await database.execute(
                """INSERT INTO packaging_items
                   (section_id, text, sort_order, checked, checked_by, checked_at, qty, remark, remark_by, remark_at)
                   VALUES (:sid, :text, :o, :checked, :by, :at, :qty, :remark, :rby, :rat)""",
                values={"sid": sec_id, "text": text, "o": ii, "checked": checked, "by": checked_by, "at": checked_at,
                        "qty": item.qty, "remark": remark, "rby": remark_by, "rat": remark_at},
            )


@router.put("/admin/packaging/lists/{list_id}/content")
async def update_list_content(list_id: int, body: ListContentIn, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    row = await database.fetch_one("SELECT id FROM packaging_lists WHERE id = :id", values={"id": list_id})
    if not row:
        raise HTTPException(status_code=404, detail="Packaging list not found.")
    await _write_sections(list_id, body.sections, merge=True)
    await database.execute("UPDATE packaging_lists SET updated_at = NOW() WHERE id = :id", values={"id": list_id})
    return await _full_list(list_id)


@router.delete("/admin/packaging/lists/{list_id}")
async def delete_list(list_id: int, x_admin_password: Optional[str] = Header(None)):
    _require_admin(x_admin_password)
    await database.execute("DELETE FROM packaging_lists WHERE id = :id", values={"id": list_id})
    return {"ok": True}


# ─── staff tablet endpoints — token auth only, no admin password ──────────

@router.get("/pack/{share_token}")
async def get_pack_list(share_token: str):
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE share_token = :t", values={"t": share_token})
    if not lst:
        raise HTTPException(status_code=404, detail="This packing list link isn't valid — check the link and try again.")
    return await _hydrate(lst)


@router.patch("/pack/{share_token}/items/{item_id}")
async def toggle_pack_item(share_token: str, item_id: int, body: CheckIn):
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE share_token = :t", values={"t": share_token})
    if not lst:
        raise HTTPException(status_code=404, detail="This packing list link isn't valid.")
    item = await database.fetch_one(
        """SELECT i.* FROM packaging_items i JOIN packaging_sections s ON i.section_id = s.id
           WHERE i.id = :iid AND s.packaging_list_id = :lid""",
        values={"iid": item_id, "lid": lst["id"]},
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found on this list.")
    await database.execute(
        """UPDATE packaging_items SET checked = :checked, checked_by = :by,
           checked_at = CASE WHEN :checked THEN NOW() ELSE NULL END WHERE id = :id""",
        values={"id": item_id, "checked": body.checked, "by": (body.checked_by or None)},
    )
    await database.execute("UPDATE packaging_lists SET updated_at = NOW() WHERE id = :id", values={"id": lst["id"]})
    return {"ok": True}


@router.patch("/pack/{share_token}/items/{item_id}/remark")
async def set_pack_item_remark(share_token: str, item_id: int, body: RemarkIn):
    lst = await database.fetch_one("SELECT * FROM packaging_lists WHERE share_token = :t", values={"t": share_token})
    if not lst:
        raise HTTPException(status_code=404, detail="This packing list link isn't valid.")
    item = await database.fetch_one(
        """SELECT i.* FROM packaging_items i JOIN packaging_sections s ON i.section_id = s.id
           WHERE i.id = :iid AND s.packaging_list_id = :lid""",
        values={"iid": item_id, "lid": lst["id"]},
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found on this list.")
    remark = (body.remark or "").strip()
    await database.execute(
        """UPDATE packaging_items SET remark = :remark, remark_by = :by,
           remark_at = CASE WHEN :has_remark THEN NOW() ELSE NULL END WHERE id = :id""",
        values={
            "id": item_id,
            "remark": (remark or None),
            "by": (body.remark_by or None) if remark else None,
            "has_remark": bool(remark),
        },
    )
    await database.execute("UPDATE packaging_lists SET updated_at = NOW() WHERE id = :id", values={"id": lst["id"]})
    return {"ok": True}
