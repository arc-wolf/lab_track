from datetime import timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from .models import BorrowRequest
from users.models import Group, GroupMember


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Header",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            alignment=1,  # center
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubHeader",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            alignment=1,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Label",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallRight",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            alignment=2,  # right
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallLabel",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
        )
    )
    return styles


def generate_borrow_slip_pdf(borrow_request_id):
    """
    Build an institutional-style A4 Borrow Request Slip (Version A) using Platypus.
    Returns (filename, bytes).
    """
    borrow_request = (
        BorrowRequest.objects.select_related("user", "user__profile")
        .prefetch_related("items__component")
        .get(id=borrow_request_id)
    )

    # derive fields with safe fallbacks
    profile = getattr(borrow_request.user, "profile", None)
    group_no = getattr(profile, "group_id", "") or "________________"
    project_title = (
        getattr(borrow_request, "project_title", None)
        or getattr(borrow_request, "counsellor_name", "")
        or "____________________________________________"
    )
    department = getattr(profile, "student_class", "") or "________________"
    batch = getattr(profile, "semester", "") or "________"
    request_date = borrow_request.created_at.date()
    due_date = borrow_request.due_date or (request_date + timedelta(days=45))

    styles = _build_styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.2 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    elements = []

    # Header
    elements.append(Paragraph("Hardware & IoT LAB", styles["Header"]))
    elements.append(Paragraph("Equipment’s /Components request & Issue Form", styles["SubHeader"]))

    # Right aligned meta
    meta_lines = [
        f"Request ID: {borrow_request.id}",
        f"Status: {borrow_request.status}",
    ]
    elements.append(Paragraph("<br/>".join(meta_lines), styles["SmallRight"]))
    elements.append(Spacer(1, 6))

    # Details section
    detail_lines = [
        f"Group No: {group_no}",
        f"Project/work Title : {project_title}",
        f"Department : {department}    Batch: {batch}    Request Date: {request_date}",
    ]
    for line in detail_lines:
        elements.append(Paragraph(line, styles["Label"]))
        elements.append(Spacer(1, 4))

    # Group members (name / reg / phone) fetched from DB
    members_line = ""
    if profile and profile.group_id:
        group = Group.objects.filter(code=profile.group_id).first()
        if group:
            members = (
                GroupMember.objects.filter(group=group)
                .select_related("user__profile")
                .order_by("role", "user__username")
            )
            member_bits = []
            for gm in members[:8]:
                p = getattr(gm.user, "profile", None)
                name = getattr(p, "full_name", "") or gm.user.username
                phone = getattr(p, "phone", "") or "—"
                member_bits.append(f"{name} (Mob: {phone})")
            if member_bits:
                members_line = "Members: " + "; ".join(member_bits)
    if members_line:
        elements.append(Paragraph(members_line, styles["SmallLabel"]))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 6))

    # ---------------- Table: fixed institutional layout ----------------
    headers = [
        Paragraph("Sl No", styles["TableCell"]),
        Paragraph("Equipment / Component", styles["TableCell"]),
        Paragraph("Qty", styles["TableCell"]),
        Paragraph("Rec Date", styles["TableCell"]),
        Paragraph("Sign", styles["TableCell"]),
        Paragraph("Return Date", styles["TableCell"]),
        Paragraph("Staff Sign", styles["TableCell"]),
        Paragraph("Remarks", styles["TableCell"]),
    ]

    item_rows = []
    for idx, item in enumerate(borrow_request.items.select_related("component"), start=1):
        item_rows.append(
            [
                Paragraph(str(idx), styles["TableCell"]),
                Paragraph(item.component.name, styles["TableCell"]),
                Paragraph(str(item.quantity), styles["TableCell"]),
                Paragraph("", styles["TableCell"]),
                Paragraph("", styles["TableCell"]),
                Paragraph("", styles["TableCell"]),
                Paragraph("", styles["TableCell"]),
                Paragraph("", styles["TableCell"]),
            ]
        )

    # pad to exactly 10 item rows
    while len(item_rows) < 10:
        item_rows.append([Paragraph("", styles["TableCell"]) for _ in headers])

    data = [headers] + item_rows[:10]

    col_widths = [25, 150, 35, 50, 40, 50, 40, 60]
    row_heights = [30] + [50] * 10  # header + 10 items ≈ 530 points to fit first page

    table = Table(
        data,
        colWidths=col_widths,
        rowHeights=row_heights,
        repeatRows=1,
        hAlign="LEFT",
    )

    table_style = TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),  # Sl No
            ("ALIGN", (2, 0), (2, -1), "CENTER"),  # Qty
            ("ALIGN", (3, 0), (6, -1), "CENTER"),  # dates/signs
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )

    # Full vertical separators for all rows (header + data)
    for col_idx in range(1, len(headers)):
        table_style.add("LINEBEFORE", (col_idx, 0), (col_idx, len(data) - 1), 1, colors.black)

    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 12))

    # Footer
    fac = getattr(borrow_request, "faculty", None)
    staff_name = (
        getattr(fac.profile, "full_name", "") if fac and hasattr(fac, "profile") else ""
    ) or (fac.get_full_name() if fac else "") or (fac.username if fac else "") or getattr(profile, "faculty_incharge", "") or "___________________________"
    footer_lines = [
        f"Staff In Charge Name : {staff_name}",
        "Sign : ___________________________",
    ]
    elements.append(Paragraph(footer_lines[0], styles["Label"]))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(footer_lines[1], styles["Label"]))
    elements.append(Spacer(1, 6))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"borrow_request_{borrow_request.id}.pdf"
    return filename, pdf_bytes
