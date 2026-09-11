"""
Customer invoice generator (reportlab) — "Wondershop Playful" (lavender)
design, per Shruti's pick from the 3 canvas directions (2026-09-11).

V1 scope: sent as a PDF attachment on the confirmation email the moment a
booking is confirmed (see routers/leads.py's _send_user_ack), and re-sendable
on demand from the admin panel once billing figures change (see routers/
admin.py's POST /bookings/{lead_id}/invoice/send, which calls
routers.leads._resend_invoice). Not GST-registered yet — GST_ENABLED stays
False in config.py until Shruti registers; every GST row below is written
now so flipping that one setting (plus GSTIN + GST_RATE_PCT) is enough to
switch it on later with no further code changes.

This module deliberately takes only plain primitives in — no
LeadSubmitRequest, no DB Record — so it never needs to import from
routers.leads (which would be a circular import: leads.py imports FROM
here, mirroring the existing order_form_builder.py <-> leads.py split).
Both call sites (the live booking-time req, and the admin resend's DB row)
assemble their own primitives and hand them to assemble_invoice_data().
"""
import io
import os
import re
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

# ─── brand tokens (matches the site's CSS variables + the chosen canvas) ────
_LAVENDER_BAND   = colors.HexColor("#F5F0FF")   # --li3, header band / mat
_LAVENDER_CARD   = colors.HexColor("#EDE6FA")   # --li2, "Billed To" card
_LAVENDER_TEXT   = colors.HexColor("#7B5DAE")   # darker lavender for on-card labels
_PINK_CARD       = colors.HexColor("#FBECF1")   # light pink, "Event Details" card
_PINK_TEXT       = colors.HexColor("#C2427A")   # darker pink for on-card labels + badge/total bg
_INK             = colors.HexColor("#191919")
_GRAY            = colors.HexColor("#6B7280")
_LIGHT_GRAY_ROW  = colors.HexColor("#FAFAFA")
_GREEN           = colors.HexColor("#1E8A4C")

# Plain hex strings (not colors.HexColor objects) — these get spliced
# straight into Paragraph HTML as <font color="#...">, which needs a hex
# string, not a reportlab Color object. Matches the chosen (lavender)
# canvas direction's per-category dot colors exactly.
_CATEGORY_HEX = {
    "Decor":         "#B59DDE",
    "Activities":    "#B8860B",  # Activities' dot is the bright #FFC200 — too low-contrast to use as body text, so this is a darker gold at the same hue for the printed category label
    "Host":          "#5B8EDD",
    "Music":         "#52C470",
    "Pinata":        "#F57A1A",
    "E-Invite":      "#C2427A",  # the dot itself is a light pink (#F5C3D7) — too low-contrast for text, so darkened for the label
    "Photographer":  "#E65A96",
    "Return Gifts":  "#B59DDE",
    "Bonus Service": "#1E8A4C",
}

_BUSINESS_NAME    = "Wondershop Experiences"
_BUSINESS_ADDRESS = "Godrej Platinum, Vikhroli East, Mumbai, Maharashtra, India"
_BUSINESS_PHONE   = "+91 97422 40477"
_BUSINESS_EMAIL   = "contact@wondershopexperiences.com"

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo-horizontal.png")

_PAYMENT_METHOD_LABELS = {
    "online":  "UPI / Bank Transfer",
    "branch":  "Cash Deposit at Branch",
    "collect": "Cash Collection at Venue",
}


def _fmt_rupees(amount) -> str:
    if amount is None:
        return "—"
    try:
        return f"Rs. {float(amount):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_date_long(d) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        return d
    if isinstance(d, date):
        return f"{d.day} {d.strftime('%B %Y')}"
    return str(d)


def payment_method_label(payment_method: Optional[str]) -> str:
    return _PAYMENT_METHOD_LABELS.get(payment_method or "", payment_method or "—")


def _line_items_from_services_detail(services_detail: list) -> list:
    """Turns leads.py's _services_detail_list() output into flat invoice
    rows: {label, description, amount (float or None), free (bool)}. Skips
    any category the customer didn't book at all (_services_detail_list
    marks those not_selected=True for the confirmation email's benefit —
    an invoice should only ever itemise what was actually charged)."""
    rows = []
    for entry in services_detail or []:
        if entry.get("not_selected"):
            continue
        label = entry.get("label", "")
        if "items" in entry:
            # Activities / Return Gifts — a list of {name, price|total, qty?}.
            items = entry["items"] or []
            names = []
            total = 0.0
            any_amount = False
            for it in items:
                name = it.get("name") or ""
                qty = it.get("qty")
                if qty:
                    names.append(f"{name} × {qty}")
                else:
                    names.append(name)
                amt = it.get("total", it.get("price"))
                if amt is not None:
                    total += float(amt)
                    any_amount = True
            rows.append({
                "label": label,
                "description": ", ".join(n for n in names if n) or "—",
                "amount": total if any_amount else None,
                "free": not any_amount,
            })
        else:
            price = entry.get("price")
            rows.append({
                "label": label,
                "description": entry.get("name") or "—",
                "amount": float(price) if price is not None else None,
                "free": entry.get("free", price is None),
            })
    return rows


def assemble_invoice_data(
    *,
    lead_id: int,
    invoice_number: str,
    invoice_date_str: str,
    parent_name: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    event_title: Optional[str],
    event_date_str: str,
    event_time: Optional[str],
    venue: Optional[str],
    city: Optional[str],
    services_detail: list,
    subtotal: Optional[float],
    discount_pct: Optional[float],
    grand_total: Optional[float],
    advance_paid: Optional[float],
    balance_due: Optional[float],
    total_savings: Optional[float] = None,
    freebies_text: Optional[str] = None,
    payment_method: Optional[str] = None,
    gst_enabled: bool = False,
    gstin: Optional[str] = None,
    gst_rate_pct: float = 0.0,
) -> dict:
    line_items = _line_items_from_services_detail(services_detail)

    discount_amt = None
    if subtotal is not None and grand_total is not None:
        discount_amt = max(0.0, subtotal - grand_total)

    gst_block = None
    total_payable = grand_total
    if gst_enabled and grand_total is not None and gst_rate_pct:
        half = gst_rate_pct / 2.0
        cgst = grand_total * half / 100.0
        sgst = grand_total * half / 100.0
        total_payable = grand_total + cgst + sgst
        gst_block = {"cgst_pct": half, "cgst_amt": cgst, "sgst_pct": half, "sgst_amt": sgst, "total_payable": total_payable}

    if balance_due is not None and balance_due <= 0.01:
        status_label = "PAID IN FULL"
    elif advance_paid:
        status_label = "PARTIALLY PAID"
    else:
        status_label = "PAYMENT PENDING"

    venue_line = ", ".join(v for v in [venue, city] if v)

    return {
        "lead_id": lead_id,
        "invoice_number": invoice_number,
        "invoice_date_str": invoice_date_str,
        "gstin": gstin or "—",
        "parent_name": parent_name or "—",
        "phone": phone or "—",
        "email": email or "—",
        "event_title": event_title or "—",
        "event_date_str": event_date_str,
        "event_time": event_time or "",
        "venue_line": venue_line or "—",
        "line_items": line_items,
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount_amt": discount_amt,
        "grand_total": grand_total,
        "gst_block": gst_block,
        "total_payable": total_payable,
        "advance_paid": advance_paid,
        "balance_due": balance_due,
        "total_savings": total_savings,
        "freebies_text": freebies_text,
        "payment_method_label": payment_method_label(payment_method),
        "status_label": status_label,
    }


def invoice_filename(data: dict) -> str:
    safe_number = re.sub(r"[^A-Za-z0-9_-]", "", data["invoice_number"])
    return f"Wondershop-Invoice-{safe_number}.pdf"


def _p(text: str, *, size=10, color=_INK, bold=False, align=None, leading=None) -> Paragraph:
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
        "custom", parent=styles["Normal"], fontSize=size, leading=leading or size * 1.4,
        textColor=color, fontName=("Helvetica-Bold" if bold else "Helvetica"),
        alignment=(TA_RIGHT if align == "right" else 0),
    )
    return Paragraph(text, style)


def build_invoice_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    page_w, page_h = A4
    margin = 10 * mm
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=f"Wondershop Invoice {data['invoice_number']}",
    )
    usable_w = page_w - 2 * margin
    story = []

    # ── Header band ──────────────────────────────────────────────────────
    logo_cell = ""
    if os.path.isfile(_LOGO_PATH):
        try:
            logo_cell = Image(_LOGO_PATH, width=42 * mm, height=16.4 * mm)
        except Exception:
            logo_cell = _p(_BUSINESS_NAME, size=16, bold=True)
    else:
        logo_cell = _p(_BUSINESS_NAME, size=16, bold=True)

    address_p = _p(f"{_BUSINESS_ADDRESS}<br/>{_BUSINESS_PHONE} &middot; {_BUSINESS_EMAIL}"
                   f"<br/><font color='#9CA3AF'>GSTIN: {data['gstin']}</font>", size=8, color=_GRAY, leading=12)

    badge_tbl = Table([[_p(data["status_label"], size=9, bold=True, color=colors.white, align="right")]],
                       colWidths=[38 * mm])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PINK_TEXT),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
    ]))

    right_col = [
        _p("Invoice", size=22, bold=True, align="right"),
        Spacer(1, 3),
        _p(f"<b>{data['invoice_number']}</b><br/>{data['invoice_date_str']}", size=9, color=_GRAY, align="right", leading=13),
        Spacer(1, 5),
        badge_tbl,
    ]

    header_tbl = Table([[[logo_cell, Spacer(1, 6), address_p], right_col]],
                        colWidths=[usable_w * 0.56, usable_w * 0.44])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _LAVENDER_BAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))

    # ── Billed To / Event Details cards ──────────────────────────────────
    bill_card = [
        _p("BILLED TO", size=8, bold=True, color=_LAVENDER_TEXT),
        Spacer(1, 5),
        _p(f"<b>{data['parent_name']}</b><br/>{data['phone']}<br/>{data['email']}", size=10, leading=15),
    ]
    event_card = [
        _p("EVENT DETAILS", size=8, bold=True, color=_PINK_TEXT),
        Spacer(1, 5),
        _p(f"<b>{data['event_title']}</b><br/>{data['event_date_str']}"
           f"{(' &middot; ' + data['event_time']) if data['event_time'] else ''}<br/>{data['venue_line']}",
           size=10, leading=15),
    ]
    cards_tbl = Table([[bill_card, event_card]], colWidths=[usable_w * 0.5 - 4, usable_w * 0.5 - 4],
                       spaceBefore=0)
    cards_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), _LAVENDER_CARD),
        ("BACKGROUND", (1, 0), (1, 0), _PINK_CARD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (1, 0), (1, 0), 20),
    ]))
    story.append(cards_tbl)
    story.append(Spacer(1, 8))

    # ── Line items ────────────────────────────────────────────────────────
    story.append(_p("SERVICES BOOKED", size=8, bold=True, color=colors.HexColor("#9CA3AF")))
    story.append(Spacer(1, 4))
    item_rows = []
    for row in data["line_items"]:
        cat_hex = _CATEGORY_HEX.get(row["label"], "#191919")
        left = _p(f"<font color='{cat_hex}'><b>{row['label']}</b></font><br/>"
                  f"<font color='#6B7280' size='9'>{row['description']}</font>", size=10, leading=14)
        amt_text = "Free" if row["free"] or row["amount"] is None else _fmt_rupees(row["amount"])
        amt_color = _GREEN if (row["free"] or row["amount"] is None) else _INK
        right = _p(amt_text, size=10, bold=True, color=amt_color, align="right")
        item_rows.append([left, right])
    items_tbl = Table(item_rows, colWidths=[usable_w * 0.72, usable_w * 0.28])
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GRAY_ROW),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_LIGHT_GRAY_ROW]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.white),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 6))

    # ── Summary ───────────────────────────────────────────────────────────
    summary_rows = []
    summary_rows.append([_p("Subtotal", size=10, color=_GRAY), _p(_fmt_rupees(data["subtotal"]), size=10, align="right")])
    if data["discount_pct"]:
        summary_rows.append([_p(f"Discount ({data['discount_pct']:.0f}%)", size=10, color=_GRAY),
                              _p(f"−{_fmt_rupees(data['discount_amt'])}", size=10, align="right")])
    summary_rows.append([_p("Grand Total", size=10, bold=True), _p(_fmt_rupees(data["grand_total"]), size=10, bold=True, align="right")])
    if data["gst_block"]:
        g = data["gst_block"]
        summary_rows.append([_p(f"CGST ({g['cgst_pct']:.1f}%)", size=10, color=_GRAY), _p(_fmt_rupees(g["cgst_amt"]), size=10, align="right")])
        summary_rows.append([_p(f"SGST ({g['sgst_pct']:.1f}%)", size=10, color=_GRAY), _p(_fmt_rupees(g["sgst_amt"]), size=10, align="right")])
        summary_rows.append([_p("Total Payable (incl. GST)", size=10, bold=True), _p(_fmt_rupees(g["total_payable"]), size=10, bold=True, align="right")])
    if data["advance_paid"]:
        summary_rows.append([_p("Advance Paid", size=10, color=_GRAY), _p(f"−{_fmt_rupees(data['advance_paid'])}", size=10, color=_GREEN, align="right")])
    summary_tbl = Table(summary_rows, colWidths=[usable_w * 0.55, usable_w * 0.45])
    summary_tbl.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    balance_tbl = Table([[_p("Balance Due", size=11, bold=True, color=colors.white),
                           _p(_fmt_rupees(data["balance_due"]), size=13, bold=True, color=colors.white, align="right")]],
                         colWidths=[usable_w * 0.55, usable_w * 0.45])
    balance_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PINK_TEXT),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    wrap_tbl = Table([[summary_tbl], [Spacer(1, 6)], [balance_tbl]], colWidths=[usable_w])
    wrap_tbl.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT")]))
    story.append(wrap_tbl)
    story.append(Spacer(1, 4))

    # ── Footer ────────────────────────────────────────────────────────────
    footer_lines = [f"Payment Method: {data['payment_method_label']}"]
    if data["freebies_text"]:
        footer_lines.append(f"Free Perks Unlocked: {data['freebies_text']}")
    footer_lines.append("Thank you for booking with Wondershop Experiences — we can't wait to celebrate with you!")
    footer_lines.append("This is a system-generated invoice.")
    story.append(_p("<br/>".join(footer_lines), size=8, color=colors.HexColor("#9CA3AF"), leading=12))

    doc.build(story)
    return buf.getvalue()
