"""
Customer quotation PDF for the Sales Quotation Module (2026-10-03).

Per Shruti: the sales person picks the client's options (decor, activities,
host, music, gifts...) in sales-leads.html, then downloads a branded PDF —
pictures, a price for each item and a grand total estimate — and sends it
to the customer on WhatsApp. Every category from the confirmation email's
"Services Booked" list is always shown, in the same order; one that wasn't
picked says "Not selected" instead of being left out.

Same split as invoice_builder.py: this module takes plain primitives only
(a dict assembled by routers/sales_leads.py's quotation endpoint) and never
touches the database. Image bytes are fetched up front with fetch_images()
and handed in; the builder never does network I/O itself.

Fonts: DM Sans (body) and Lora Bold (headings) — the site's own pair —
shipped in assets/fonts under the SIL Open Font License. DM Sans carries
the ₹ glyph, so amounts print as ₹ rather than the invoice's "Rs.".
"""
import asyncio
import io
import os
import urllib.parse
from datetime import datetime
from typing import Dict, Iterable, Optional

import httpx
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether,
)

from catalogue_data import SITE_BASE_URL

# ─── brand tokens (site CSS variables / invoice_builder.py) ───────────────
PURPLE = colors.HexColor("#8A67BE")
PURPLE_DARK = colors.HexColor("#6C4AB6")
PINK = colors.HexColor("#E65A96")
PINK_DARK = colors.HexColor("#C2427A")
INK = colors.HexColor("#2D2140")
MUTED = colors.HexColor("#6B6480")
FAINT = colors.HexColor("#A79FB8")
LAV_BAND = colors.HexColor("#F5F0FF")
LAV_CARD = colors.HexColor("#EDE6FA")
LAV_RULE = colors.HexColor("#E4DAF5")
PINK_CARD = colors.HexColor("#FBECF1")
WHITE = colors.white

BUSINESS_NAME = "Wondershop Experiences"
BUSINESS_ADDRESS = "409, Ajmera Sikova, Ghatkopar West, Mumbai – 400086"
BUSINESS_PHONES = "+91 90044 35362 · +91 97422 40477"
BUSINESS_EMAIL = "contact@wondershopexperiences.com"
BUSINESS_WEB = "www.wondershopexperiences.com"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(_HERE, "assets")
_LOGO_PATH = os.path.join(_ASSETS, "logo-horizontal.png")
# Repo root when running from a full checkout (local dev) — lets
# fetch_images() read img/... straight off disk instead of over HTTP. On
# Railway only backend/ is deployed, so this simply doesn't exist there.
_SITE_ROOT = os.path.dirname(_HERE)

# Section icons — the same colour illustrations the homepage uses.
SECTION_ICONS = {
    "Decor": "img/icons/icon-decor.png",
    "Activities": "img/icons/icon-activities.png",
    "Host": "img/icons/icon-host.png",
    "Music": "img/icons/icon-dj.png",
    "Pinata": "img/icons/icon-pinata.png",
    "E-Invite": "img/icons/icon-invite.png",
    "Photographer": "img/icons/icon-photographer.png",
    "Return Gifts": "img/icons/icon-gift.png",
}
MASCOT_PATH = "img/icons/icon-mascot-kids.png"

# ─── fonts ─────────────────────────────────────────────────────────────
_FONTS_READY = False
BODY, BODY_BOLD, HEAD = "Helvetica", "Helvetica-Bold", "Helvetica-Bold"
RUPEE = "Rs. "


def _register_fonts():
    global _FONTS_READY, BODY, BODY_BOLD, HEAD, RUPEE
    if _FONTS_READY:
        return
    _FONTS_READY = True
    fdir = os.path.join(_ASSETS, "fonts")
    try:
        pdfmetrics.registerFont(TTFont("WS-DMSans", os.path.join(fdir, "DMSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("WS-DMSans-Bold", os.path.join(fdir, "DMSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("WS-DMSans", normal="WS-DMSans", bold="WS-DMSans-Bold",
                                      italic="WS-DMSans", boldItalic="WS-DMSans-Bold")
        BODY, BODY_BOLD, RUPEE = "WS-DMSans", "WS-DMSans-Bold", "₹"
    except Exception:
        pass   # falls back to Helvetica + "Rs." — never fail a quote over a font
    try:
        pdfmetrics.registerFont(TTFont("WS-Lora-Bold", os.path.join(fdir, "Lora-Bold.ttf")))
        HEAD = "WS-Lora-Bold"
    except Exception:
        HEAD = BODY_BOLD


# ─── formatting helpers ──────────────────────────────────────────────────
def inr(amount) -> str:
    """Indian digit grouping: 123456 -> ₹1,23,456 (paise only when present)."""
    _register_fonts()
    if amount is None:
        return "—"
    v = float(amount)
    neg = v < 0
    v = abs(v)
    whole = int(v)
    paise = round((v - whole) * 100)
    if paise == 100:
        whole, paise = whole + 1, 0
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    out = f"{RUPEE}{s}" + (f".{paise:02d}" if paise else "")
    return ("−" + out) if neg else out


def _x(s) -> str:
    """Escape text for reportlab Paragraph markup."""
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _style(name, *, font=None, size=9.5, color=INK, leading=None, align=None, **kw):
    st = ParagraphStyle(name, fontName=font or BODY, fontSize=size, textColor=color,
                        leading=leading or size * 1.38, **kw)
    if align is not None:
        st.alignment = align
    return st


# ─── images ──────────────────────────────────────────────────────────────
_IMG_CACHE: Dict[str, bytes] = {}
_IMG_CACHE_MAX = 300


def _thumb(raw: bytes, size_px: int = 320, square: bool = True) -> Optional[bytes]:
    """Center-crop to a square (photos) and downscale, flattening any
    transparency onto white, so a quote with 20 photos stays a WhatsApp-
    friendly few hundred KB. Returns PNG for transparent art (icons), JPEG
    otherwise."""
    try:
        im = PILImage.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if square:
        w, h = im.size
        side = min(w, h)
        im = im.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
        im = im.resize((size_px, size_px), PILImage.LANCZOS)
    else:
        im.thumbnail((size_px, size_px), PILImage.LANCZOS)
    buf = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(buf, "PNG", optimize=True)
    else:
        im.convert("RGB").save(buf, "JPEG", quality=80, optimize=True)
    return buf.getvalue()


async def fetch_images(paths: Iterable[str], *, timeout: float = 8.0) -> Dict[str, bytes]:
    """Loads each site-relative image path (e.g. 'img/activity/act-slime.jpg')
    — from disk when this is a full checkout, otherwise from the live site —
    and returns {path: thumbnail bytes}. Anything that can't be loaded is
    simply missing from the result (the PDF then shows no picture for it);
    a slow or missing image never fails the quote."""
    wanted = [p for p in dict.fromkeys(p for p in paths if p)]
    out: Dict[str, bytes] = {}
    todo = []
    for p in wanted:
        if p in _IMG_CACHE:
            out[p] = _IMG_CACHE[p]
        else:
            todo.append(p)
    if not todo:
        return out

    async def one(client, path):
        raw = None
        local = os.path.join(_SITE_ROOT, *path.split("/"))
        if os.path.isfile(local):
            try:
                with open(local, "rb") as fh:
                    raw = fh.read()
            except OSError:
                raw = None
        if raw is None and client is not None:
            try:
                r = await client.get(f"{SITE_BASE_URL}/{urllib.parse.quote(path)}")
                if r.status_code == 200:
                    raw = r.content
            except Exception:
                raw = None
        if raw is None:
            return
        is_icon = path.startswith("img/icons/")
        th = _thumb(raw, size_px=220 if is_icon else 320, square=not is_icon)
        if th:
            if len(_IMG_CACHE) >= _IMG_CACHE_MAX:
                _IMG_CACHE.pop(next(iter(_IMG_CACHE)))
            _IMG_CACHE[path] = th
            out[path] = th

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        await asyncio.gather(*(one(client, p) for p in todo))
    return out


def _img(data: Optional[bytes], w_mm: float, h_mm: Optional[float] = None):
    if not data:
        return None
    try:
        if h_mm is None:
            iw, ih = PILImage.open(io.BytesIO(data)).size
            h_mm = w_mm * ih / iw
        return Image(io.BytesIO(data), width=w_mm * mm, height=h_mm * mm)
    except Exception:
        return None


# ─── PDF ─────────────────────────────────────────────────────────────────
def quotation_filename(data: dict) -> str:
    who = (data.get("child_first_name") or data.get("client_name") or "Client").strip()
    safe = "".join(c for c in who if c.isalnum() or c in " -_").strip().replace(" ", "-") or "Client"
    return f"Wondershop-Quotation-{safe}-{data.get('quote_no', '')}.pdf".replace("--", "-")


def build_quotation_pdf(data: dict, images: Dict[str, bytes]) -> bytes:
    """data — assembled by routers/sales_leads.py (_quotation_data):
      quote_no, issued_at_text, valid_until_text, prepared_by,
      party_title, client_name, details [(label, value)],
      sections [{label, not_selected, billed_separately, lines:[{name,
        details:[str], image, price, price_text, strike}]}],
      totals {subtotal, discount, estimate, gift_total, gift_mrp,
        has_unpriced}, extra_terms
    images — {site-relative path: bytes} from fetch_images()."""
    _register_fonts()
    buf = io.BytesIO()
    LM = RM = 14 * mm
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=LM, rightMargin=RM, topMargin=12 * mm, bottomMargin=20 * mm,
        title=f"Quotation {data.get('quote_no', '')} — {BUSINESS_NAME}",
        author=BUSINESS_NAME, subject=data.get("party_title") or "Party quotation",
    )
    W = A4[0] - LM - RM

    s_body = _style("body")
    s_small = _style("small", size=8.2, color=MUTED)
    s_tiny = _style("tiny", size=7.6, color=MUTED, leading=10.4)
    s_label = _style("label", size=7.6, color=colors.HexColor("#7B5DAE"), font=BODY_BOLD, leading=10)
    s_value = _style("value", size=9.6, font=BODY_BOLD, leading=12.4)
    s_h1 = _style("h1", font=HEAD, size=19, color=INK, leading=23)
    s_sec = _style("sec", font=HEAD, size=12.5, color=PURPLE_DARK, leading=15)
    s_item = _style("item", font=BODY_BOLD, size=10, leading=13)
    s_det = _style("det", size=8.4, color=MUTED, leading=11.4)
    s_price = _style("price", font=BODY_BOLD, size=10, align=TA_RIGHT, leading=13)
    s_price_note = _style("pnote", size=8, color=MUTED, align=TA_RIGHT, leading=10.5)

    story = []

    # ── header band: logo · QUOTATION meta ──────────────────────────────
    logo = None
    if os.path.isfile(_LOGO_PATH):
        try:
            logo = Image(_LOGO_PATH, width=46 * mm, height=46 * mm * 200 / 512)
        except Exception:
            logo = None
    left = [logo or Paragraph(_x(BUSINESS_NAME), _style("bn", font=HEAD, size=16)),
            Spacer(1, 2.5 * mm),
            Paragraph(f"{_x(BUSINESS_ADDRESS)}<br/>{_x(BUSINESS_PHONES)} · {_x(BUSINESS_EMAIL)}", s_tiny)]
    meta_rows = [
        [Paragraph("QUOTATION", _style("qt", font=HEAD, size=20, color=PURPLE_DARK, align=TA_RIGHT, leading=23))],
        [Paragraph(f"<font color='#7B5DAE'>Quote No.</font>&nbsp; <b>{_x(data.get('quote_no'))}</b>", _style("m1", size=8.8, align=TA_RIGHT))],
        [Paragraph(f"<font color='#7B5DAE'>Issued</font>&nbsp; {_x(data.get('issued_at_text'))}", _style("m2", size=8.8, align=TA_RIGHT))],
        [Paragraph(f"<b>Valid till {_x(data.get('valid_until_text'))}</b>", _style("m3", size=8.8, color=PINK_DARK, align=TA_RIGHT))],
    ]
    meta = Table(meta_rows, colWidths=[W * 0.46 - 10 * mm])
    meta.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0.6),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6)]))
    head = Table([[left, meta]], colWidths=[W * 0.54, W * 0.46])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LAV_BAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5 * mm),
        ("LINEBELOW", (0, 0), (-1, -1), 2.2, PINK),
    ]))
    story += [head, Spacer(1, 6 * mm)]

    # ── title + intro (mascot on the right) ─────────────────────────────
    title = data.get("party_title") or "Your Party Quotation"
    first = (data.get("client_first_name") or "").strip()
    intro = (
        (f"Hi {_x(first)}, thank you" if first else "Thank you")
        + " for considering Wondershop Experiences! Here is the party plan we have put together for you, "
          "with a picture and an estimate for each service. Anything marked <i>Not selected</i> can still be "
          "added — just let us know."
    )
    mascot = _img(images.get(MASCOT_PATH), 34)
    title_cell = [Paragraph(_x(title), s_h1), Spacer(1, 1.6 * mm), Paragraph(intro, _style("intro", size=9.4, color=MUTED, leading=13.4))]
    t = Table([[title_cell, mascot or ""]], colWidths=[W - 40 * mm, 40 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 5 * mm)]

    # ── event details card (3 pairs per row) ────────────────────────────
    details = [(l, v) for l, v in (data.get("details") or []) if v not in (None, "")]
    if details:
        per_row = 3
        cells, row = [], []
        for label, value in details:
            row.append([Paragraph(_x(label).upper(), s_label), Paragraph(_x(value), s_value)])
            if len(row) == per_row:
                cells.append(row)
                row = []
        if row:
            cells.append(row + [""] * (per_row - len(row)))
        card = Table(cells, colWidths=[W / per_row] * per_row)
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LAV_CARD),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        story += [card, Spacer(1, 6 * mm)]

    # ── "Your party plan" sections ──────────────────────────────────────
    story.append(Paragraph("YOUR PARTY PLAN", _style("pp", font=BODY_BOLD, size=9, color=PINK_DARK, leading=12)))
    story.append(Spacer(1, 2.5 * mm))

    IMG_W = 21 * mm
    PRICE_W = 33 * mm
    DESC_W = W - IMG_W - PRICE_W

    for sec in data.get("sections") or []:
        label = sec["label"]
        icon = _img(images.get(SECTION_ICONS.get(sec.get("icon_key") or label, "")), 9.5)
        hdr_txt = _x(label)
        empty = sec.get("not_selected") or not sec.get("lines")
        if sec.get("billed_separately") and not empty:
            hdr_txt += "&nbsp;&nbsp;<font name='%s' size='8' color='#C2427A'>BILLED SEPARATELY</font>" % BODY_BOLD
        if empty:
            # Nothing picked: one compact line — label and "Not selected".
            row = Table([[icon or "", Paragraph(hdr_txt, s_sec), Paragraph("Not selected", _style("nsr", size=9.2, color=FAINT, align=TA_RIGHT))]],
                        colWidths=[12 * mm, W - 12 * mm - PRICE_W, PRICE_W])
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, LAV_RULE),
            ]))
            story.append(row)
            story.append(Spacer(1, 3.2 * mm))
            continue
        hdr = Table([[icon or "", Paragraph(hdr_txt, s_sec)]], colWidths=[12 * mm, W - 12 * mm])
        hdr.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
            ("LINEBELOW", (0, 0), (-1, -1), 0.8, LAV_RULE),
        ]))
        rows = []
        for ln in sec["lines"]:
            desc = [Paragraph(_x(ln["name"]), s_item)]
            det = [d for d in (ln.get("details") or []) if d]
            if det:
                desc.append(Spacer(1, 0.8 * mm))
                desc.append(Paragraph("<br/>".join(_x(d) for d in det), s_det))
            price_cell = []
            if ln.get("price") is not None:
                price_cell.append(Paragraph(inr(ln["price"]), s_price))
            if ln.get("price_text"):
                price_cell.append(Paragraph(_x(ln["price_text"]), s_price_note if ln.get("price") is not None else
                                            _style("pt", font=BODY_BOLD, size=8.6, color=PURPLE_DARK, align=TA_RIGHT, leading=11)))
            rows.append([_img(images.get(ln.get("image") or ""), 18, 18) or "", desc, price_cell or ""])
        # Section header is row 0 of the same table (repeated if a long
        # section such as Activities runs onto the next page), so a heading
        # is never left alone at the bottom of a page.
        body = Table([[hdr, "", ""]] + rows, colWidths=[IMG_W, DESC_W, PRICE_W], repeatRows=1)
        st = [
            ("SPAN", (0, 0), (-1, 0)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (1, 1), (1, -1), 1.5 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ("TOPPADDING", (0, 0), (-1, 0), 0), ("BOTTOMPADDING", (0, 0), (-1, 0), 0.5 * mm),
        ]
        for i in range(1, len(rows)):
            st.append(("LINEBELOW", (0, i), (-1, i), 0.4, colors.HexColor("#F1ECF8")))
        body.setStyle(TableStyle(st))
        story.append(KeepTogether([body]) if len(rows) <= 4 else body)
        story.append(Spacer(1, 4.5 * mm))

    # ── totals ───────────────────────────────────────────────────────────
    T = data.get("totals") or {}
    s_tl = _style("tl", size=9.6, color=INK)
    s_tr = _style("tr", size=9.6, font=BODY_BOLD, align=TA_RIGHT)
    trows = [[Paragraph("Total (all selected services)", s_tl), Paragraph(inr(T.get("subtotal") or 0), s_tr)]]
    if T.get("discount"):
        d = float(T["discount"])
        if d > 0:
            trows.append([Paragraph("Special discount", _style("dl", size=9.6, color=colors.HexColor("#1E8A4C"))),
                          Paragraph("− " + inr(d), _style("dr", size=9.6, font=BODY_BOLD, align=TA_RIGHT, color=colors.HexColor("#1E8A4C")))])
        else:
            trows.append([Paragraph("Customisation &amp; other charges", s_tl), Paragraph("+ " + inr(-d), s_tr)])
    n_plain = len(trows)
    trows.append([Paragraph("Estimated Total", _style("gl", font=HEAD, size=13, color=WHITE, leading=16)),
                  Paragraph(inr(T.get("estimate") or 0), _style("gr", font=BODY_BOLD, size=15, color=WHITE, align=TA_RIGHT, leading=18))])
    tw = 96 * mm
    tt = Table(trows, colWidths=[tw * 0.58, tw * 0.42])
    tt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BACKGROUND", (0, 0), (-1, n_plain - 1), LAV_BAND),
        ("BACKGROUND", (0, n_plain), (-1, n_plain), PINK),
        ("TOPPADDING", (0, n_plain), (-1, n_plain), 3 * mm), ("BOTTOMPADDING", (0, n_plain), (-1, n_plain), 3 * mm),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    notes = []
    if T.get("gift_total"):
        notes.append(f"<b>Return gifts: {inr(T['gift_total'])}</b> — billed separately, after we confirm stock "
                     f"(not included in the Estimated Total).")
    if T.get("has_unpriced"):
        notes.append("Items marked <i>Price on request</i> or <i>To be confirmed</i> are not included in the "
                     "Estimated Total; your Party Experience Lead will confirm them.")
    notes.append("All prices are estimates for the details shown above (date, venue and number of kids).")
    note_p = Paragraph("<br/><br/>".join(notes), _style("tn", size=8.4, color=MUTED, leading=11.6))
    tot_wrap = Table([[note_p, tt]], colWidths=[W - tw - 6 * mm, tw + 6 * mm])
    tot_wrap.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 6 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([Spacer(1, 1 * mm), tot_wrap]))
    story.append(Spacer(1, 7 * mm))

    # ── terms ────────────────────────────────────────────────────────────
    terms = [
        "<b>Tentative pricing.</b> This quotation is an estimate. Prices and inclusions are tentative and may "
        "change due to availability of artists, materials or slots, venue requirements, or changes to the "
        "party details.",
        f"<b>Valid for {int(data.get('valid_hours') or 72)} hours.</b> The prices in this quotation are valid for "
        f"{int(data.get('valid_hours') or 72)} hours from the time of issue "
        f"(till {_x(data.get('valid_until_text'))}). After that, the quotation will need to be re-reviewed "
        f"by our team.",
        "<b>Confidential.</b> This quotation has been prepared exclusively for you. It is not to be shared, "
        "forwarded or published without prior permission from Wondershop Experiences.",
        f"Full terms &amp; conditions: {BUSINESS_WEB}/terms.html",
    ]
    extra = (data.get("extra_terms") or "").strip()
    if extra:
        terms.append("<b>Also agreed:</b> " + _x(extra).replace("\n", "<br/>"))
    s_term = _style("term", size=8.2, color=INK, leading=11.4)
    trs = [[Paragraph(f"{i}.", _style("tn%i" % i, size=8.2, color=PURPLE_DARK, font=BODY_BOLD, leading=11.4)),
            Paragraph(txt, s_term)] for i, txt in enumerate(terms, 1)]
    tbox = Table([[Paragraph("TERMS &amp; CONDITIONS", _style("th", font=BODY_BOLD, size=8.6, color=PINK_DARK, leading=11)), ""]] + trs,
                 colWidths=[10 * mm, W - 10 * mm])
    tbox.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.8, LAV_RULE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCFAFF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("RIGHTPADDING", (0, 1), (0, -1), 0.5 * mm), ("LEFTPADDING", (1, 1), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 3 * mm), ("BOTTOMPADDING", (0, -1), (-1, -1), 3 * mm),
    ]))
    tail = [tbox, Spacer(1, 5 * mm)]

    # ── sign-off ─────────────────────────────────────────────────────────
    by = (data.get("prepared_by") or "").strip()
    sign = (
        (f"Prepared by <b>{_x(by)}</b>, Wondershop Experiences. " if by else "")
        + f"Questions or changes? Call or WhatsApp us on <b>{_x(BUSINESS_PHONES)}</b> or write to {_x(BUSINESS_EMAIL)}."
    )
    tail.append(Paragraph(sign, _style("sign", size=8.8, color=MUTED, align=TA_CENTER, leading=12.4)))
    story.append(KeepTogether(tail))

    quote_no = data.get("quote_no") or ""

    def on_page(canvas, _doc):
        canvas.saveState()
        y = 11 * mm
        canvas.setStrokeColor(PINK)
        canvas.setLineWidth(0.8)
        canvas.line(LM, y + 4.2 * mm, A4[0] - RM, y + 4.2 * mm)
        canvas.setFont(BODY, 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(LM, y, "CONFIDENTIAL · Not to be shared without prior permission of Wondershop Experiences")
        canvas.drawRightString(A4[0] - RM, y, f"{quote_no} · Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
