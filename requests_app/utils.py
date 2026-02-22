from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet


def build_request_pdf(borrow_request):
    """
    Build a print-ready A4 PDF for the lab request/issue form.
    Returns (filename, bytes).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=15 * mm,
        leftMargin=30 * mm,  # extra space for punching holes
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=18,
            alignment=1,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubtitleCenter",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=14,
            alignment=1,
            spaceAfter=10,
        )
    )
    normal = ParagraphStyle(
        "NormalSerif", parent=styles["Normal"], fontName="Times-Roman", fontSize=11, leading=14
    )

    elements = []

    # Header
    elements.append(Paragraph("Hardware & IoT LAB", styles["TitleCenter"]))
    elements.append(Paragraph("Equipment’s / Components Request & Issue Form", styles["SubtitleCenter"]))

    # Group number top-right
    elements.append(
        Paragraph(
            '<para align="right"><font size="10">Group No: ____________</font></para>',
            normal,
        )
    )
    elements.append(Spacer(1, 6))

    student_profile = getattr(borrow_request.student, "profile", None)
    dept = getattr(student_profile, "student_class", "") or "___________________________"
    batch = getattr(student_profile, "semester", "") or "____________"
    project_title = getattr(borrow_request, "counsellor", "") or "_______________________________________________"
    request_date = borrow_request.created_at.strftime("%Y-%m-%d")

    # Section 1: project details
    elements.append(
        Paragraph(
            f"Project/work Title : {project_title}",
            normal,
        )
    )
    elements.append(Spacer(1, 8))

    line2 = (
        f"Department : {dept}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        f"Batch : {batch}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        f"Request Date : {request_date}"
    )
    elements.append(Paragraph(line2, normal))
    elements.append(Spacer(1, 12))

    # Section 2: main table
    headers = [
        "Sl No",
        "Equipment’s / Components",
        "Qnty",
        "Rec Date",
        "Sign",
        "Return Date",
        "Staff Sign",
        "Remarks",
    ]

    # usable width after margins: 160mm (210 - 30 - 20). Apply percentages (wider date/sign cols to avoid clipping).
    usable_mm = 160.0
    col_widths = [
        0.06 * usable_mm * mm,  # Sl No
        0.28 * usable_mm * mm,  # Equipment
        0.08 * usable_mm * mm,  # Qnty
        0.12 * usable_mm * mm,  # Rec Date
        0.10 * usable_mm * mm,  # Sign
        0.14 * usable_mm * mm,  # Return Date
        0.10 * usable_mm * mm,  # Staff Sign
        0.12 * usable_mm * mm,  # Remarks
    ]

    data_rows_actual = []
    for idx, item in enumerate(borrow_request.items.select_related("component"), start=1):
        data_rows_actual.append(
            [
                str(idx),
                item.component.name,
                str(item.quantity),
                "",
                "",
                "",
                "",
                "",
            ]
        )

    rows = list(data_rows_actual)

    # compute row budget to keep single-page layout
    min_rows = 12
    max_rows = 15  # tuned to keep to single page while filling area
    row_height_mm = 11
    data_rows = max(len(rows), min_rows)
    data_rows = min(data_rows, max_rows)

    # pad or trim to fit budget
    if len(rows) < data_rows:
        while len(rows) < data_rows:
            rows.append([""] * len(headers))
    elif len(rows) > data_rows:
        rows = rows[: data_rows]

    table = Table(
        [headers] + rows,
        colWidths=col_widths,
        rowHeights=[row_height_mm * mm] + [row_height_mm * mm] * len(rows),
        repeatRows=1,
    )

    styles_table = [
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("FONTSIZE", (0, 1), (-1, -1), 11),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "LEFT"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),  # separate header
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    # add vertical column lines only
    num_cols = len(headers)
    for c in range(1, num_cols):
        styles_table.append(("LINEBEFORE", (c, 0), (c, len(rows)), 0.5, colors.black))

    # add separators between actual data rows (not blank padding)
    if len(data_rows_actual) > 1:
        for r in range(1, len(data_rows_actual)):
            styles_table.append(("LINEBELOW", (0, r), (-1, r), 0.5, colors.black))

    table.setStyle(TableStyle(styles_table))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    # Footer
    staff_name = ""
    if borrow_request.faculty:
        staff_name = getattr(borrow_request.faculty.profile, "full_name", "") or borrow_request.faculty.username

    footer_left = [
        ["Staff in Charge Name : ______________________"],
        ["Sign : ______________________"],
    ]
    footer_right = [
        ["Write Group Members Name, Reg: no"],
        ["& Mob number on other side"],
    ]

    footer_table = Table(
        [
            [Paragraph(footer_left[0][0], normal), Paragraph(footer_right[0][0], normal)],
            [Paragraph(footer_left[1][0], normal), Paragraph(footer_right[1][0], normal)],
        ],
        colWidths=[85 * mm, 85 * mm],
    )
    footer_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"borrow_slip_{borrow_request.id}.pdf"
    return filename, pdf_bytes
