"""
Order execution form generator — Excel (openpyxl) + PDF (reportlab).

V1 scope, per Shruti (2026-08-12): print only what we already capture on a
booking — LeadSubmitRequest fields + builder_snapshot. Anything genuinely
manual (vendor assigned, Event Ops Lead, payment mode, pinata bags/fillings,
gift-wrap instructions, event schedule, inventory to pack) prints as a
blank line / empty grid for ops to fill by hand on the printout. No
separate internal tool needed for this cut — that can follow once this is
live and being used.
"""
import io
import re
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepInFrame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# ─── formatting helpers ──────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _fmt_date(d) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        return d
    try:
        return f"{_ordinal(d.day)} {d.strftime('%b %Y')}"
    except Exception:
        return str(d)


def _fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"Rs. {v:,.0f}"
    except Exception:
        return str(v)


def _child_age_gender(req) -> str:
    """'F5' style summary (first letter of gender + age), comma-joined for
    multiple kids. Degrades gracefully when either piece is missing."""
    ages = [a.strip() for a in (req.child_ages or "").split(",") if a.strip()]
    genders = [g.strip() for g in (req.child_genders or "").split(",") if g.strip()]
    if not ages and not genders:
        return "—"
    parts = []
    for i in range(max(len(ages), len(genders))):
        age = ages[i] if i < len(ages) else ""
        gen = genders[i] if i < len(genders) else ""
        letter = gen[:1].upper() if gen else ""
        parts.append((f"{letter}{age}".strip()) or "—")
    return ", ".join(parts) if parts else "—"


# ─── data assembly ────────────────────────────────────────────────────────

def assemble_order_form_data(req, lead_id: int, event_sales_lead: Optional[str],
                              reward_code: Optional[str] = None) -> dict:
    """Pulls together everything the order form needs straight from the
    booking payload already captured at checkout — no extra DB lookups."""
    snap = req.builder_snapshot or {}

    decor   = snap.get("decor") or {}
    host    = snap.get("host") or {}
    dj      = snap.get("dj") or {}
    photo   = snap.get("photo") or {}
    pinata  = snap.get("pinata") or {}
    einvite = snap.get("einvite") or {}
    activities = snap.get("activities") or []
    gifts      = snap.get("gifts") or []

    dj_addon_bits = []
    if getattr(req, "dj_lights_addon", False):
        dj_addon_bits.append("Lights")
    if getattr(req, "dj_smoke_machine_addon", False):
        dj_addon_bits.append("Smoke Machine")

    venue_type_address = " · ".join([v for v in [req.location_type, req.venue] if v]) or "—"
    venue_contact = " ".join([v for v in [
        req.venue_contact_name,
        f"({req.venue_contact_phone})" if req.venue_contact_phone else None,
    ] if v]) or "—"

    coupon = req.redeemed_coupon_code or getattr(req, "sales_lead_code", None) or None
    child_name = (req.child_names or "").split(",")[0].strip() or req.parent_name or "Guest"

    return {
        "lead_id": lead_id,
        "child_name": child_name,
        "client_name": req.parent_name or "—",
        "client_phone": req.phone or "—",
        "child_names": req.child_names or "—",
        "child_age_gender": _child_age_gender(req),
        "event_date": _fmt_date(req.event_date),
        "event_date_raw": req.event_date,
        "event_time": req.event_time or "—",
        "venue_type_address": venue_type_address,
        "venue_contact": venue_contact,
        "kids_count": req.kids_count or "—",
        "theme": req.theme or "—",
        "event_sales_lead": event_sales_lead or "—",
        "billing_amount": _fmt_money(req.order_grand_total),
        "advance_paid": _fmt_money(req.order_advance),
        "pending_amount": _fmt_money(req.order_balance),
        "coupon_code": coupon or "—",
        "remarks": req.remarks or "—",
        "decor_name": decor.get("n") or "—",
        "host_tier": host.get("tier") or "—",
        "dj_tier": dj.get("tier") or "—",
        "dj_addons": ", ".join(dj_addon_bits) or "None",
        "photo_tier": photo.get("tier") or "—",
        "pinata_name": pinata.get("n") or "—",
        "einvite_name": einvite.get("n") or "—",
        "activities": [a.get("n") for a in activities if a.get("n")] or ["—"],
        "gifts": [f"{g.get('n')} x{g.get('qty')}" for g in gifts if g.get("n")] or ["—"],
        "reward_code": reward_code or "—",
        "location": req.city or req.venue or "",
    }


def order_form_filename(data: dict, ext: str) -> str:
    """<customer name>-<date>-<location>-Birthday Order Form.<ext>"""
    raw = f"{data['child_name']}-{data['event_date']}-{data['location'] or ''}-Birthday Order Form.{ext}"
    safe = re.sub(r'[\\/:*?"<>|]+', "", raw)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe


# Rows we already have data for (label, value-key or literal).
_DETAIL_ROWS = [
    ("Client Name",        "client_name"),
    ("Client Number",      "client_phone"),
    ("Child Name(s)",      "child_names"),
    ("Age & Gender",       "child_age_gender"),
    ("Date",               "event_date"),
    ("Time",               "event_time"),
    ("Venue Type & Address", "venue_type_address"),
    ("Venue Contact",      "venue_contact"),
    ("# Kids",             "kids_count"),
    ("Theme",              "theme"),
    ("Event Sales Lead",   "event_sales_lead"),
]

_SERVICE_ROWS = [
    ("Decor",         "decor_name"),
    ("Host",          "host_tier"),
    ("Music (DJ)",    "dj_tier"),
    ("DJ Add-ons",    "dj_addons"),
    ("Photographer",  "photo_tier"),
    ("Piñata",        "pinata_name"),
    ("E-Invite",      "einvite_name"),
]

_BILLING_ROWS = [
    ("Billing Amount",  "billing_amount"),
    ("Advance Paid",    "advance_paid"),
    ("Pending Amount",  "pending_amount"),
    ("Coupon / Referral Code Applied", "coupon_code"),
]

# Manually-assigned fields — printed as blank lines for ops to fill by hand.
_MANUAL_ROWS = [
    "Event Ops Lead", "Decor Vendor", "Decor Reference Photo Confirmed",
    "Host Name", "DJ Name", "Entry Song", "Photographer Add-ons",
    "Cake", "Volunteers", "Piñata Bags", "Piñata Fillings",
    "Return Gift Wrapping (Y/N)", "Paper Bag (Y/N + size)",
    "Personalization (Y/N + design)", "Host Gifts (# confirmed)",
    "Advance Payment Mode", "Pending — Expected Payment Mode",
]


# ─── EXCEL (openpyxl) ─────────────────────────────────────────────────────

def build_order_form_xlsx(data: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Order Form"
    ws.sheet_view.showGridLines = False

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_font = Font(bold=True, size=16, color="FFFFFF")
    section_font = Font(bold=True, size=11, color="FFFFFF")
    label_font = Font(bold=True, size=10)
    value_font = Font(size=10)
    title_fill = PatternFill("solid", fgColor="7A4FBF")
    section_fill = PatternFill("solid", fgColor="B59DDE")
    manual_fill = PatternFill("solid", fgColor="FFF7E6")

    for col, width in zip("ABCDEFGHI", [22, 4, 26, 4, 22, 4, 26, 4, 4]):
        ws.column_dimensions[col].width = width

    # Title
    ws.merge_cells("A1:I2")
    c = ws["A1"]
    c.value = f"Wondershop Experiences — Birthday Order Form  (Lead #{data['lead_id']})"
    c.font = title_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 20
    ws.row_dimensions[2].height = 20

    left_row = 4
    right_row = 4

    def section(row, col_start, col_end, text):
        r = ws.cell(row=row, column=col_start)
        ws.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_end)
        r.value = text
        r.font = section_font
        r.fill = section_fill
        r.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[row].height = 16
        return row + 1

    def kv(row, label_col, value_col, value_end_col, label, value, fill=None):
        lc = ws.cell(row=row, column=label_col, value=label)
        lc.font = label_font
        lc.border = border
        ws.merge_cells(start_row=row, start_column=value_col, end_row=row, end_column=value_end_col)
        vc = ws.cell(row=row, column=value_col, value=value)
        vc.font = value_font
        vc.border = border
        vc.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        if fill:
            lc.fill = fill
            vc.fill = fill
        return row + 1

    # ── LEFT column: event details, services, billing ──
    left_row = section(left_row, 1, 3, "Event Details")
    for label, key in _DETAIL_ROWS:
        left_row = kv(left_row, 1, 3, 3, label, data.get(key, "—"))

    left_row += 1
    left_row = section(left_row, 1, 3, "Services (as booked)")
    for label, key in _SERVICE_ROWS:
        left_row = kv(left_row, 1, 3, 3, label, data.get(key, "—"))
    left_row = kv(left_row, 1, 3, 3, "Engagement Activities", ", ".join(data.get("activities", ["—"])))
    left_row = kv(left_row, 1, 3, 3, "Return Gifts", ", ".join(data.get("gifts", ["—"])))

    left_row += 1
    left_row = section(left_row, 1, 3, "Billing")
    for label, key in _BILLING_ROWS:
        left_row = kv(left_row, 1, 3, 3, label, data.get(key, "—"))

    left_row += 1
    left_row = section(left_row, 1, 3, "Remarks / Personalization Requests")
    ws.merge_cells(start_row=left_row, start_column=1, end_row=left_row + 1, end_column=3)
    rc = ws.cell(row=left_row, column=1, value=data.get("remarks", "—"))
    rc.font = value_font
    rc.border = border
    rc.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    left_row += 3

    # ── RIGHT column: to-be-filled-by-ops, inventory, schedule ──
    right_row = section(right_row, 5, 9, "To Be Filled By Ops")
    for label in _MANUAL_ROWS:
        right_row = kv(right_row, 5, 7, 9, label, "", fill=manual_fill)

    right_row += 1
    right_row = section(right_row, 5, 9, "Inventory To Be Packed")
    hdr_row = right_row
    headers = ["Type", "Item", "Qty", "Remarks"]
    cols = [5, 6, 8, 9]
    ends = [5, 7, 8, 9]
    for h, cs, ce in zip(headers, cols, ends):
        ws.merge_cells(start_row=hdr_row, start_column=cs, end_row=hdr_row, end_column=ce)
        hc = ws.cell(row=hdr_row, column=cs, value=h)
        hc.font = label_font
        hc.border = border
        hc.alignment = Alignment(horizontal="center")
    right_row += 1
    for _ in range(10):
        for cs, ce in zip(cols, ends):
            ws.merge_cells(start_row=right_row, start_column=cs, end_row=right_row, end_column=ce)
            cell = ws.cell(row=right_row, column=cs, value="")
            cell.border = border
        right_row += 1

    right_row += 1
    right_row = section(right_row, 5, 9, "Event Schedule")
    ws.merge_cells(start_row=right_row, start_column=5, end_row=right_row, end_column=6)
    hc = ws.cell(row=right_row, column=5, value="Time")
    hc.font = label_font
    hc.border = border
    hc.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=right_row, start_column=7, end_row=right_row, end_column=9)
    hc2 = ws.cell(row=right_row, column=7, value="Activity")
    hc2.font = label_font
    hc2.border = border
    hc2.alignment = Alignment(horizontal="center")
    right_row += 1
    for _ in range(8):
        ws.merge_cells(start_row=right_row, start_column=5, end_row=right_row, end_column=6)
        ws.cell(row=right_row, column=5, value="").border = border
        ws.merge_cells(start_row=right_row, start_column=7, end_row=right_row, end_column=9)
        ws.cell(row=right_row, column=7, value="").border = border
        right_row += 1

    last_row = max(left_row, right_row) + 1
    ws.row_dimensions[last_row].height = 8

    # Printer-friendly A4 landscape, fit to one page wide.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    ws.print_area = f"A1:I{last_row}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─── PDF (reportlab) ──────────────────────────────────────────────────────

_PURPLE = colors.HexColor("#7A4FBF")
_LIGHT_PURPLE = colors.HexColor("#B59DDE")
_MANUAL_BG = colors.HexColor("#FFF7E6")


def _kv_table(rows, col_widths, styles):
    body = getSampleStyleSheet()["BodyText"]
    body.fontSize = 8.5
    body.leading = 10.5
    data = []
    for label, value in rows:
        data.append([Paragraph(f"<b>{label}</b>", body), Paragraph(str(value), body)])
    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(TableStyle(styles + [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _section_header(text, width):
    styles = getSampleStyleSheet()
    st = ParagraphStyle("section", parent=styles["Normal"], textColor=colors.white,
                         fontSize=10, fontName="Helvetica-Bold", leftIndent=4, spaceBefore=0, spaceAfter=0)
    t = Table([[Paragraph(text, st)]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_PURPLE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def build_order_form_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        leftMargin=10 * mm, rightMargin=10 * mm, topMargin=8 * mm, bottomMargin=8 * mm,
        title="Birthday Order Form",
    )
    usable_w = page_size[0] - 20 * mm
    left_w = usable_w * 0.52
    right_w = usable_w * 0.44

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Normal"], textColor=colors.white,
                                  fontSize=14, fontName="Helvetica-Bold", leftIndent=4)
    title_tbl = Table([[Paragraph(f"Wondershop Experiences — Birthday Order Form (Lead #{data['lead_id']})", title_style)]],
                       colWidths=[usable_w])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PURPLE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    left_flow = []
    left_flow.append(_section_header("Event Details", left_w))
    left_flow.append(_kv_table([(l, data.get(k, "—")) for l, k in _DETAIL_ROWS],
                                [left_w * 0.4, left_w * 0.6], []))
    left_flow.append(Spacer(1, 4))
    left_flow.append(_section_header("Services (as booked)", left_w))
    svc_rows = [(l, data.get(k, "—")) for l, k in _SERVICE_ROWS]
    svc_rows.append(("Engagement Activities", ", ".join(data.get("activities", ["—"]))))
    svc_rows.append(("Return Gifts", ", ".join(data.get("gifts", ["—"]))))
    left_flow.append(_kv_table(svc_rows, [left_w * 0.4, left_w * 0.6], []))
    left_flow.append(Spacer(1, 4))
    left_flow.append(_section_header("Billing", left_w))
    left_flow.append(_kv_table([(l, data.get(k, "—")) for l, k in _BILLING_ROWS],
                                [left_w * 0.4, left_w * 0.6], []))
    left_flow.append(Spacer(1, 4))
    left_flow.append(_section_header("Remarks / Personalization Requests", left_w))
    body = styles["BodyText"]; body.fontSize = 8.5; body.leading = 10.5
    remarks_tbl = Table([[Paragraph(data.get("remarks", "—"), body)]], colWidths=[left_w])
    remarks_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    left_flow.append(remarks_tbl)

    right_flow = []
    right_flow.append(_section_header("To Be Filled By Ops", right_w))
    manual_rows = [(label, "") for label in _MANUAL_ROWS]
    right_flow.append(_kv_table(manual_rows, [right_w * 0.55, right_w * 0.45],
                                 [("BACKGROUND", (1, 0), (1, -1), _MANUAL_BG),
                                  ("BOTTOMPADDING", (1, 0), (1, -1), 10)]))
    right_flow.append(Spacer(1, 4))
    right_flow.append(_section_header("Inventory To Be Packed", right_w))
    inv_header = [Paragraph(f"<b>{h}</b>", body) for h in ["Type", "Item", "Qty", "Remarks"]]
    inv_data = [inv_header] + [["", "", "", ""] for _ in range(9)]
    inv_tbl = Table(inv_data, colWidths=[right_w * 0.22, right_w * 0.34, right_w * 0.14, right_w * 0.30])
    inv_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    right_flow.append(inv_tbl)
    right_flow.append(Spacer(1, 4))
    right_flow.append(_section_header("Event Schedule", right_w))
    sched_header = [Paragraph("<b>Time</b>", body), Paragraph("<b>Activity</b>", body)]
    sched_data = [sched_header] + [["", ""] for _ in range(7)]
    sched_tbl = Table(sched_data, colWidths=[right_w * 0.25, right_w * 0.75])
    sched_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    right_flow.append(sched_tbl)

    # Everything must fit on a single printed page — shrink-to-fit rather
    # than error if a booking has an unusually long remarks/services list.
    avail_h = page_size[1] - doc.topMargin - doc.bottomMargin - 110
    left_frame = KeepInFrame(left_w, avail_h, left_flow, mode="shrink")
    right_frame = KeepInFrame(right_w, avail_h, right_flow, mode="shrink")

    outer = Table([[left_frame, right_frame]], colWidths=[left_w, right_w])
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
    ]))

    doc.build([title_tbl, Spacer(1, 6), outer])
    return buf.getvalue()
