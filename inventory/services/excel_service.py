import io
from typing import Dict, Tuple

import pandas as pd
from django.utils import timezone
from django.db import transaction

from inventory.models import Component


class ExcelImportError(Exception):
    """Raised when uploaded Excel data is invalid."""


REQUIRED_COLUMNS = {"name", "category", "total_stock"}


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(col).strip().lower() for col in frame.columns]
    return frame


def import_components_from_excel(file_obj) -> Dict[str, int]:
    """
    Ingest component rows from an Excel file.
    - Required columns: name, category, total_stock
    - Sets available_stock equal to total_stock for every row.
    - Uses update_or_create to avoid duplicates.
    Returns {'created': x, 'updated': y}.
    """
    try:
        if getattr(file_obj, "name", "").lower().endswith(".csv"):
            df = pd.read_csv(file_obj)
        else:
            df = pd.read_excel(file_obj)
    except Exception as exc:  # pandas/openpyxl errors
        raise ExcelImportError("Unable to read Excel file.") from exc

    df = _normalize_columns(df)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ExcelImportError(f"Missing required columns: {', '.join(sorted(missing))}.")

    created = 0
    updated = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            name = str(row.get("name", "")).strip()
            category = str(row.get("category", "")).strip()
            total_stock_raw = row.get("total_stock", 0)

            if not name:
                raise ExcelImportError(f"Row {idx + 2}: name is required.")
            if category == "":
                raise ExcelImportError(f"Row {idx + 2}: category is required.")

            try:
                total_stock = int(total_stock_raw)
            except (TypeError, ValueError) as exc:
                raise ExcelImportError(f"Row {idx + 2}: total_stock must be a number.") from exc
            if total_stock < 0:
                raise ExcelImportError(f"Row {idx + 2}: total_stock cannot be negative.")

            obj, is_created = Component.objects.update_or_create(
                name=name,
                defaults={
                    "category": category,
                    "total_stock": total_stock,
                    "available_stock": total_stock,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

    return {"created": created, "updated": updated}


def export_inventory_and_requests() -> Tuple[bytes, str]:
    """
    Export inventory and borrow requests to an Excel workbook with two sheets:
    - Inventory: component stock snapshot.
    - Requests: recent borrow requests with item summary.
    Returns (xlsx_bytes, filename).
    """
    # Inventory data
    inventory_qs = Component.objects.all().order_by("category", "name")
    inventory_df = pd.DataFrame(
        [
            {
                "Name": comp.name,
                "Category": comp.category,
                "Total Stock": comp.total_stock,
                "Available Stock": comp.available_stock,
                "Student Limit": comp.student_limit,
                "Faculty Limit": comp.faculty_limit,
                "Fine Per Day": comp.fine_per_day,
                "Fine Damaged": comp.fine_damaged,
                "Fine Missing Parts": comp.fine_missing_parts,
                "Fine Not Working": comp.fine_not_working,
            }
            for comp in inventory_qs
        ]
    )

    # Requests data
    from requests_app.models import BorrowRequest  # local import to avoid circular dependency at import time

    requests_qs = (
        BorrowRequest.objects.select_related("user", "faculty", "group")
        .prefetch_related("items__component")
        .order_by("-created_at")[:200]
    )
    requests_rows = []
    for req in requests_qs:
        items_summary = ", ".join([f"{item.component.name} x {item.quantity}" for item in req.items.all()])
        due_date_raw = req.due_date
        created_raw = req.created_at
        if due_date_raw is not None and hasattr(due_date_raw, "tzinfo"):
            due_date_raw = timezone.make_naive(due_date_raw)
        if created_raw is not None and hasattr(created_raw, "tzinfo"):
            created_raw = timezone.make_naive(created_raw)
        requests_rows.append(
            {
                "Request ID": req.id,
                "Student": getattr(req.user, "username", ""),
                "Group": getattr(req.group, "code", ""),
                "Faculty": getattr(req.faculty, "username", ""),
                "Status": req.status,
                "Due Date": due_date_raw,
                "Created At": created_raw,
                "Items": items_summary,
            }
        )
    requests_df = pd.DataFrame(requests_rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        inventory_df.to_excel(writer, index=False, sheet_name="Inventory")
        requests_df.to_excel(writer, index=False, sheet_name="Requests")
    return output.getvalue(), "labtrack-export.xlsx"
