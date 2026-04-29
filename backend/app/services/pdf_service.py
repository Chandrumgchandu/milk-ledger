from collections import defaultdict
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_farmer_statement_pdf(business_name, farmer, month_label, milk_entries, store_transactions, payment_logs, totals):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor("#16325c"))
    section_style = ParagraphStyle("Section", parent=styles["Heading4"], fontSize=11, leading=14, textColor=colors.HexColor("#1d4ed8"))
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#64748b"))

    elements = [
        Paragraph(f"<b>{business_name}</b>", title_style),
        Spacer(1, 4),
        _info_table(farmer, month_label),
        Spacer(1, 8),
        Paragraph("<b>Milk Summary</b>", section_style),
        Spacer(1, 4),
    ]

    milk_rows, morning_total, evening_total, milk_amount_total = _milk_statement_rows(milk_entries)
    milk_table = Table(milk_rows, colWidths=[36 * mm, 28 * mm, 28 * mm, 32 * mm], repeatRows=1, hAlign="LEFT")
    milk_table.setStyle(_default_table_style(len(milk_rows), header_color="#1d4ed8", total_color="#dcfce7"))
    elements.extend([milk_table, Spacer(1, 8)])

    elements.append(Paragraph("<b>Provision Store Purchases</b>", section_style))
    elements.append(Spacer(1, 4))
    store_rows, store_total = _store_rows(store_transactions)
    store_table = Table(store_rows, colWidths=[24 * mm, 52 * mm, 22 * mm, 22 * mm, 26 * mm], repeatRows=1, hAlign="LEFT")
    store_table.setStyle(_default_table_style(len(store_rows), header_color="#0f766e", total_color="#fef3c7"))
    elements.extend([store_table, Spacer(1, 8)])

    if payment_logs:
        elements.append(Paragraph("<b>Settlement Payment Logs</b>", section_style))
        elements.append(Spacer(1, 4))
        log_rows = [["Date", "Direction", "Amount", "Note"]]
        for log in payment_logs:
            log_rows.append(
                [
                    log.payment_date.strftime("%Y-%m-%d"),
                    "Pay Farmer" if log.direction == "to_farmer" else "Recover",
                    _fmt_money(log.amount),
                    log.note or "-",
                ]
            )
        payment_table = Table(log_rows, colWidths=[28 * mm, 30 * mm, 24 * mm, 90 * mm], repeatRows=1, hAlign="LEFT")
        payment_table.setStyle(_default_table_style(len(log_rows), header_color="#7c3aed", total_color="#ede9fe", include_total=False))
        elements.extend([payment_table, Spacer(1, 8)])

    summary_rows = [
        ["Total Morning", _fmt_qty(morning_total)],
        ["Total Evening", _fmt_qty(evening_total)],
        ["Total Milk Liters", _fmt_qty(totals["quantity"])],
        ["Total Milk Amount", _fmt_money(totals["amount"])],
        ["Total Shop Credit", _fmt_money(totals["store_total"])],
        ["Net Settlement", _fmt_money(totals["net_amount"])],
        ["Paid To Farmer", _fmt_money(totals.get("paid_to_farmer"))],
        ["Recovered From Farmer", _fmt_money(totals.get("recovered_from_farmer"))],
        ["Final Balance", _fmt_money(totals["final_balance"])],
        ["Final Status", totals["final_status"]],
        ["Signature", "____________________"],
    ]
    summary_table = Table(summary_rows, colWidths=[48 * mm, 60 * mm], hAlign="LEFT")
    summary_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.extend([Paragraph("<b>Final Settlement</b>", section_style), Spacer(1, 4), summary_table, Spacer(1, 8)])
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %I:%M %p')}", note_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer


def build_monthly_settlement_summary_pdf(business_name, month, year, rows):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SummaryTitle", parent=styles["Title"], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor("#16325c"))
    subtitle_style = ParagraphStyle("SummarySubtitle", parent=styles["Normal"], fontSize=10, leading=13, alignment=1, textColor=colors.HexColor("#64748b"))

    table_rows = [["Farmer ID", "Farmer Name", "Milk Total", "Shop Credit", "Net Amount", "Status"]]
    for row in rows:
        table_rows.append(
            [
                str(row["farmer_code"]),
                row["farmer_name"],
                _fmt_money(row["milk_total"]),
                _fmt_money(row["shop_credit_total"]),
                _fmt_money(row["net_amount"]),
                row["status"],
            ]
        )
    if len(table_rows) == 1:
        table_rows.append(["-", "-", "0.00", "0.00", "0.00", "No Data"])

    total_milk = sum((row["milk_total"] for row in rows), 0)
    total_store = sum((row["shop_credit_total"] for row in rows), 0)
    total_net = sum((row["net_amount"] for row in rows), 0)
    table_rows.append(["Total", "", _fmt_money(total_milk), _fmt_money(total_store), _fmt_money(total_net), ""])

    elements = [
        Paragraph(f"<b>{business_name}</b>", title_style),
        Paragraph(f"Monthly Settlement Summary - {year}-{month:02d}", subtitle_style),
        Spacer(1, 10),
    ]
    table = Table(table_rows, colWidths=[24 * mm, 54 * mm, 24 * mm, 24 * mm, 24 * mm, 28 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(_default_table_style(len(table_rows), header_color="#1d4ed8", total_color="#dcfce7"))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer


def _info_table(farmer, month_label):
    rows = [["Name", farmer.name], ["Farmer ID", str(farmer.unique_code)], ["Phone No", farmer.phone], ["Month", month_label]]
    table = Table(rows, colWidths=[28 * mm, 72 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _milk_statement_rows(entries):
    grouped = defaultdict(lambda: {"morning": None, "evening": None, "amount": 0})
    morning_total = 0
    evening_total = 0
    amount_total = 0
    for entry in sorted(entries, key=lambda item: (item.date, item.session)):
        key = entry.date.strftime("%Y-%m-%d")
        grouped[key][entry.session] = entry.quantity
        grouped[key]["amount"] += entry.amount
        amount_total += entry.amount
        if entry.session == "morning":
            morning_total += entry.quantity
        else:
            evening_total += entry.quantity
    rows = [["Date", "Morning", "Evening", "Amount"]]
    for day in sorted(grouped.keys()):
        rows.append([day, _fmt_qty(grouped[day]["morning"]), _fmt_qty(grouped[day]["evening"]), _fmt_money(grouped[day]["amount"])])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "0.00"])
    rows.append(["Total", _fmt_qty(morning_total), _fmt_qty(evening_total), _fmt_money(amount_total)])
    return rows, morning_total, evening_total, amount_total


def _store_rows(transactions):
    rows = [["Date", "Item", "Qty", "Price", "Subtotal"]]
    total = 0
    for tx in transactions:
        for item in tx.items:
            qty = f"{_fmt_qty(item.quantity)}{item.unit or ''}"
            rows.append([tx.bill_date.strftime("%Y-%m-%d"), item.item_name, qty, _fmt_money(item.unit_price), _fmt_money(item.subtotal)])
            total += item.subtotal or 0
    if len(rows) == 1:
        rows.append(["-", "-", "-", "-", "0.00"])
    rows.append(["Total", "", "", "", _fmt_money(total)])
    return rows, total


def _default_table_style(row_count, header_color, total_color, include_total=True):
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#94a3b8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2 if include_total else -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]
    if include_total:
        style.extend(
            [
                ("BACKGROUND", (0, row_count - 1), (-1, row_count - 1), colors.HexColor(total_color)),
                ("FONTNAME", (0, row_count - 1), (-1, row_count - 1), "Helvetica-Bold"),
            ]
        )
    return TableStyle(style)


def _fmt_qty(value):
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _fmt_money(value):
    return f"{float(value or 0):.2f}".rstrip("0").rstrip(".")
