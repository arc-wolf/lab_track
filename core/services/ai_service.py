from typing import Dict, List

from django.db.models import Count

from inventory.models import Component
from requests_app.models import BorrowRequest


def _component_context(limit: int = 100) -> List[Dict]:
    return list(
        Component.objects.all()
        .order_by("name")[:limit]
        .values("name", "category", "available_stock", "total_stock")
    )


def _request_context(limit: int = 50) -> Dict:
    status_counts = dict(
        BorrowRequest.objects.values_list("status")
        .annotate(total=Count("id"))
        .order_by()
    )
    recent = (
        BorrowRequest.objects.select_related("user", "group", "faculty")
        .prefetch_related("items__component")
        .order_by("-created_at")[:limit]
    )
    recent_brief = []
    for req in recent:
        items_summary = ", ".join([f"{it.component.name} x {it.quantity}" for it in req.items.all()])
        recent_brief.append(
            {
                "id": req.id,
                "status": req.status,
                "student": getattr(req.user, "username", ""),
                "group": getattr(req.group, "code", ""),
                "items": items_summary,
            }
        )
    return {"status_counts": status_counts, "recent": recent_brief}


def _build_context() -> Dict:
    return {
        "components": _component_context(),
        "requests": _request_context(),
    }


def answer_query(query: str) -> str:
    """
    Minimal, read-only assistant backed by live context.
    - Builds context from components and recent borrow requests.
    - Heuristically surfaces matches and status snapshots.
    """
    query = (query or "").strip()
    if not query:
        return "Please provide a question for LabTrack."

    context = _build_context()
    tokens = [tok for tok in query.lower().split() if len(tok) > 2]

    dangerous_tokens = {"delete", "drop", "remove", "wipe", "destroy", "truncate"}
    if any(tok in dangerous_tokens for tok in tokens):
        return "I cannot perform destructive or write actions. LabTrack assistant is read-only; please use the admin console for any changes."

    matched_components = []
    for comp in context["components"]:
        haystack = f"{comp['name']} {comp['category']}".lower()
        if any(tok in haystack for tok in tokens):
            matched_components.append(comp)
            if len(matched_components) >= 5:
                break

    lines = []

    if matched_components:
        lines.append("Closest matching components:")
        for comp in matched_components:
            lines.append(
                f"- {comp['name']} ({comp['category']}): {comp['available_stock']}/{comp['total_stock']} available"
            )

    status_counts = context["requests"]["status_counts"]
    if status_counts:
        lines.append(
            "Borrow request snapshot: "
            + ", ".join([f"{status}={count}" for status, count in status_counts.items()])
        )

    if not matched_components:
        lines.append("No direct component match found; here are recent requests:")
        for req in context["requests"]["recent"][:5]:
            lines.append(
                f"- #{req['id']} {req['status']} • {req['group'] or req['student']}: {req['items']}"
            )

    lines.append("If you need exact stock or request details, ask with component name or request id.")
    return "\n".join(lines)
