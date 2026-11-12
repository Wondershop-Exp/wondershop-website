"""
Vendor catalogue reader (2026-11-12, per Shruti).

  "can I upload the vendor catalogs via bot and then you read and update their
  catalogs in the vendor item master, where you upload photo, name, size,
  price etc. - whatever is available."

A partner's catalogue (a PDF, or photos of its pages) goes in from Slack
#vendor-contacts (routers/slack_vendors.py) or from the partner's page in the
admin Partners tab (routers/vendors.py). This module:

  1. sends the catalogue to Claude, a few pages at a time, and gets back every
     item on it: name, category, size, price (+ what the price is per), notes,
     item code, age group, capacity, and where its photo sits on the page;
  2. takes each item's photo out of the PDF — the embedded picture with the
     most pixels that matches where Claude saw the photo (catalogue pages often
     have a blurred copy behind the real photo; the blurred one has far fewer
     pixels), or, for flattened pages / photos, a crop of the page itself;
  3. saves the items in vendor_items (migrations/084), one row per item name
     per partner: reading the same catalogue again updates the items instead
     of adding them twice, and never wipes a value with a blank.

Nothing on the website uses these photos; they are for the team.
"""
import asyncio
import base64
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings
from database import database

logger = logging.getLogger(__name__)

PAGES_PER_CALL = 12
MAX_PAGES = 120
PHOTO_EDGE = 1600

PROMPT = """This is part of a supplier's catalogue for Wondershop Experiences, a kids' party and events company in Mumbai. The supplier is: {vendor}.
{note}
List EVERY product / service shown (a ride, game, stall, inflatable, prop, decor item, gift ...). Skip covers, index pages, terms and contact pages, but use their prices / terms if they apply to items.

For each item give:
- page: the page number within THIS file (first page = 1)
- name: the item name in Title Case, as the catalogue calls it
- category: a short group, e.g. "Ride", "Inflatable", "Game", "Train", "Food stall", "Art & craft", "Decor", "Return gift", "Show"
- size: dimensions / size exactly as written (e.g. "40 ft L x 14 ft W x 8 ft H"), else null
- price: the number only (rupees), else null. Never guess a price.
- price_unit: what the price is for, e.g. "per day", "per 4 hours", "per piece", "per child", else null
- price_note: anything else about price or terms for this item (GST, transport, minimum hours), else null
- description: one or two short lines on what it is / features, only if written, else null
- item_code: the supplier's code / SKU, else null
- age_group: if written, else null
- capacity: riders / kids at a time / pieces etc., if written, else null
- photo_box: where this item's MAIN photo is on its page, as fractions of the page [left, top, right, bottom] from the top-left corner (e.g. [0.07, 0.18, 0.93, 0.86]); null if it has no photo

Only report what is actually in the catalogue. Reply with ONLY JSON: {{"items": [ ... ]}}"""


# ─── PDF helpers (pypdfium2, Apache/BSD licensed) ─────────────────────────
def _pdf_chunks(pdf: bytes) -> Tuple[int, List[Tuple[int, bytes]]]:
    """(page count, [(first page index, sub-PDF bytes)])."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    n = min(len(doc), MAX_PAGES)
    out = []
    for start in range(0, n, PAGES_PER_CALL):
        sub = pdfium.PdfDocument.new()
        sub.import_pages(doc, list(range(start, min(n, start + PAGES_PER_CALL))))
        buf = io.BytesIO()
        sub.save(buf)
        out.append((start, buf.getvalue()))
    return len(doc), out


def _jpeg(im, edge: int = PHOTO_EDGE) -> bytes:
    im = im.convert("RGB")
    im.thumbnail((edge, edge))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def _box(v) -> Optional[Tuple[float, float, float, float]]:
    try:
        b = [min(1.0, max(0.0, float(x))) for x in v][:4]
        return tuple(b) if len(b) == 4 and b[2] - b[0] > 0.03 and b[3] - b[1] > 0.03 else None
    except (TypeError, ValueError):
        return None


def _page_photos(pdf: bytes, page_items: Dict[int, List[Dict[str, Any]]]) -> None:
    """Sets item["_photo"] (JPEG bytes) for items on each page, in place."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    doc = pdfium.PdfDocument(pdf)
    for pidx, items in page_items.items():
        if pidx < 0 or pidx >= len(doc):
            continue
        page = doc[pidx]
        pw, ph = page.get_size()
        cands = []
        for o in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=4):
            try:
                w, h = o.get_px_size()
                l, b, r, t = o.get_bounds()
                if w * h < 150 * 150:
                    continue
                box = (l / pw, 1 - t / ph, r / pw, 1 - b / ph)   # top-left fractions
                if (box[2] - box[0]) * (box[3] - box[1]) < 0.02:
                    continue
                cands.append((w * h, box, o))
            except Exception:
                continue
        rendered = None
        for it in items:
            want = _box(it.get("photo_box"))
            pick = None
            if cands and len(items) == 1:
                pick = max(cands, key=lambda c: c[0])
            elif cands and want:
                scored = [(_iou(c[1], want), c[0], c) for c in cands]
                best = max(scored, key=lambda s: (round(s[0], 1), s[1]))
                pick = best[2] if best[0] >= 0.2 else None
            try:
                if pick is not None:
                    it["_photo"] = _jpeg(pick[2].get_bitmap(render=False).to_pil())
                    continue
            except Exception:
                logger.info("Catalogue: couldn't take out an embedded photo; cropping the page instead")
            if want or len(items) == 1:
                if rendered is None:
                    rendered = page.render(scale=2).to_pil()
                W, H = rendered.size
                b = want or (0, 0, 1, 1)
                it["_photo"] = _jpeg(rendered.crop((int(b[0] * W), int(b[1] * H), int(b[2] * W), int(b[3] * H))))


def _image_photos(images: List[Tuple[bytes, str]], page_items: Dict[int, List[Dict[str, Any]]]) -> None:
    from PIL import Image
    for pidx, items in page_items.items():
        if pidx < 0 or pidx >= len(images):
            continue
        im = Image.open(io.BytesIO(images[pidx][0]))
        W, H = im.size
        for it in items:
            b = _box(it.get("photo_box")) or ((0, 0, 1, 1) if len(items) == 1 else None)
            if b:
                it["_photo"] = _jpeg(im.crop((int(b[0] * W), int(b[1] * H), int(b[2] * W), int(b[3] * H))))


# ─── Claude ───────────────────────────────────────────────────────────────
async def _ask(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.ANTHROPIC_MODEL, "max_tokens": 12000,
                  "messages": [{"role": "user", "content": content}]},
        )
    if r.status_code != 200:
        raise RuntimeError(f"Claude API error {r.status_code}: {r.text[:300]}")
    out = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("Couldn't read the catalogue (no data came back).")
    return [x for x in (json.loads(m.group(0)).get("items") or []) if isinstance(x, dict)]


def _num(v) -> Optional[float]:
    if v in (None, ""):
        return None
    s = str(v).lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(k|l|lakh|lac)?\b", s)
    if not m:
        return None
    n = float(m.group(1)) * {"k": 1000, "l": 100000, "lakh": 100000, "lac": 100000}.get(m.group(2) or "", 1)
    return n if 0 < n < 1e9 else None


def _t(v, n: int) -> Optional[str]:
    v = re.sub(r"\s+", " ", str(v)).strip() if v not in (None, "") else ""
    return v[:n] or None


def _clean_item(x: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = _t(x.get("name"), 150)
    if not name:
        return None
    return {"name": name, "category": _t(x.get("category"), 60), "size_text": _t(x.get("size"), 200),
            "price": _num(x.get("price")), "price_unit": _t(x.get("price_unit"), 40),
            "price_note": _t(x.get("price_note"), 300), "description": _t(x.get("description"), 2000),
            "item_code": _t(x.get("item_code"), 60), "age_group": _t(x.get("age_group"), 60),
            "capacity": _t(x.get("capacity"), 100), "photo_box": x.get("photo_box"), "page": x.get("page")}


async def read_catalogue(vendor: str, pdf: Optional[bytes] = None,
                         images: Optional[List[Tuple[bytes, str]]] = None, note: str = "") -> Dict[str, Any]:
    """-> {"items": [...cleaned items, with "_photo" bytes and "page" (1-based)], "pages": n}"""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY isn't set on Railway, so I can't read catalogues.")
    items: List[Dict[str, Any]] = []
    note_line = f"Note from the team: {note}\n" if note else ""
    if pdf:
        pages, chunks = await asyncio.to_thread(_pdf_chunks, pdf)
        for start, sub in chunks:
            got = await _ask([
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.b64encode(sub).decode()}},
                {"type": "text", "text": PROMPT.format(vendor=vendor, note=note_line)}])
            for x in got:
                c = _clean_item(x)
                if c:
                    try:
                        c["page"] = start + max(1, int(c.get("page") or 1))
                    except (TypeError, ValueError):
                        c["page"] = None
                    items.append(c)
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for it in items:
            if it.get("page"):
                by_page.setdefault(it["page"] - 1, []).append(it)
        await asyncio.to_thread(_page_photos, pdf, by_page)
    else:
        from routers.slack_leads import _shrink
        images = (images or [])[:20]
        pages = len(images)
        content: List[Dict[str, Any]] = []
        for data, mime in images:
            d, m = _shrink(data, mime)
            content.append({"type": "image", "source": {"type": "base64", "media_type": m,
                                                        "data": base64.b64encode(d).decode()}})
        content.append({"type": "text", "text": PROMPT.format(vendor=vendor, note=note_line)
                        + "\nEach photo above is one page, in order (first photo = page 1)."})
        for x in await _ask(content):
            c = _clean_item(x)
            if c:
                try:
                    c["page"] = max(1, int(c.get("page") or 1))
                except (TypeError, ValueError):
                    c["page"] = 1
                items.append(c)
        by_page = {}
        for it in items:
            by_page.setdefault(it["page"] - 1, []).append(it)
        await asyncio.to_thread(_image_photos, images, by_page)
    # The same item twice: one entry when it's the same thing (same or missing
    # size, e.g. an index page + its own page) — keep the fuller one. Two
    # different products with one name (another size) become "Name (2)".
    seen: Dict[str, Dict[str, Any]] = {}
    for it in items:
        k = it["name"].lower()
        prev = seen.get(k)
        if prev and it.get("size_text") and prev.get("size_text") and it["size_text"].lower() != prev["size_text"].lower():
            n = 2
            while f"{k} ({n})" in seen:
                n += 1
            it["name"] = f"{it['name']} ({n})"
            seen[it["name"].lower()] = it
        elif not prev or sum(v is not None for v in it.values()) > sum(v is not None for v in prev.values()):
            seen[k] = it
    return {"items": list(seen.values()), "pages": pages}


# ─── Saving ───────────────────────────────────────────────────────────────
FIELDS = ["category", "size_text", "price", "price_unit", "price_note", "description", "item_code", "age_group", "capacity"]


async def save_items(vendor_id: int, items: List[Dict[str, Any]], source: str, by: str) -> Dict[str, int]:
    """Upsert by item name for this partner. Returns counts."""
    added = updated = 0
    for it in items:
        ref = f"{source} p.{it['page']}" if it.get("page") else source
        row = await database.fetch_one(
            "SELECT id FROM vendor_items WHERE vendor_id = :v AND LOWER(name) = LOWER(:n)",
            {"v": vendor_id, "n": it["name"]})
        vals = {f: it.get(f) for f in FIELDS}
        if row:
            sets = [f"{f} = COALESCE(:{f}, {f})" for f in FIELDS]
            params = {"id": row["id"], "src": ref[:300], **vals}
            if it.get("_photo"):
                sets += ["photo_data = :pd", "photo_type = 'image/jpeg'"]
                params["pd"] = it["_photo"]
            await database.execute(
                f"UPDATE vendor_items SET {', '.join(sets)}, source_ref = :src, updated_on = NOW() WHERE id = :id", params)
            updated += 1
        else:
            await database.execute(
                f"INSERT INTO vendor_items (vendor_id, name, {', '.join(FIELDS)}, photo_data, photo_type, source_ref, created_by) "
                f"VALUES (:v, :n, {', '.join(':' + f for f in FIELDS)}, :pd, :pt, :src, :by)",
                {"v": vendor_id, "n": it["name"], **vals, "pd": it.get("_photo"),
                 "pt": "image/jpeg" if it.get("_photo") else None, "src": ref[:300], "by": (by or "")[:100]})
            added += 1
    return {"added": added, "updated": updated}


async def keep_file(vendor_id: int, data: bytes, mime: str, filename: str) -> None:
    """The catalogue itself goes with the partner's files (vendor_catalogues)."""
    fn = re.sub(r"[^A-Za-z0-9._ -]", "_", filename or "catalogue").strip(" .")[:120] or "catalogue"
    if await database.fetch_val("SELECT 1 FROM vendor_catalogues WHERE vendor_id = :v AND filename = :n AND size_bytes = :s",
                                {"v": vendor_id, "n": fn, "s": len(data)}):
        return   # the same file again
    await database.execute(
        "INSERT INTO vendor_catalogues (vendor_id, filename, content_type, size_bytes, file_data) VALUES (:v, :n, :t, :s, :d)",
        {"v": vendor_id, "n": fn, "t": mime, "s": len(data), "d": data})


async def import_catalogue(vendor_id: int, files: List[Tuple[bytes, str, str]], by: str, note: str = "") -> Dict[str, Any]:
    """files = [(bytes, mime, filename)]: PDFs are read one by one; photos together.
    -> {"items": [...saved items, no photo bytes], "added", "updated", "pages", "files"}"""
    vendor = await database.fetch_val("SELECT name FROM vendor_master WHERE vendor_id = :v", {"v": vendor_id}) or "the supplier"
    out_items: List[Dict[str, Any]] = []
    added = updated = pages = 0
    pdfs = [f for f in files if f[1] == "application/pdf"]
    pics = [f for f in files if f[1].startswith("image/")]
    jobs = [([p], p[2]) for p in pdfs] + ([(pics, pics[0][2] if len(pics) == 1 else f"{len(pics)} catalogue photos")] if pics else [])
    for group, label in jobs:
        for data, mime, fn in group:
            await keep_file(vendor_id, data, mime, fn)
        if group[0][1] == "application/pdf":
            res = await read_catalogue(vendor, pdf=group[0][0], note=note)
        else:
            res = await read_catalogue(vendor, images=[(d, m) for d, m, _ in group], note=note)
        counts = await save_items(vendor_id, res["items"], label, by)
        added, updated, pages = added + counts["added"], updated + counts["updated"], pages + res["pages"]
        out_items += [{k: v for k, v in it.items() if not k.startswith("_") and k != "photo_box"} | {"has_photo": bool(it.get("_photo"))}
                      for it in res["items"]]
    return {"items": out_items, "added": added, "updated": updated, "pages": pages, "files": len(files)}


def money(n) -> str:
    if n is None:
        return ""
    n = float(n)
    s = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
    # Indian grouping (1,25,000)
    whole = str(int(n))
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail + (s[s.index("."):] if "." in s else "")
    return "₹" + s
