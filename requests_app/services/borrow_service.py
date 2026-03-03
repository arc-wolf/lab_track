from django.db import transaction

from requests_app.models import BorrowRequest


class BorrowFlowError(Exception):
    """Raised when a lifecycle transition is invalid."""


def _restore_reserved_stock(borrow_request: BorrowRequest):
    for item in borrow_request.items.select_related("component"):
        item.component.adjust_available(item.quantity)


def approve_request(borrow_request: BorrowRequest, by_user):
    if borrow_request.status != BorrowRequest.STATUS_PENDING:
        raise BorrowFlowError("Request already processed.")
    try:
        with transaction.atomic():
            borrow_request.approve(by_user=by_user)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def reject_request(borrow_request: BorrowRequest, by_user, note: str = ""):
    if borrow_request.status not in (BorrowRequest.STATUS_PENDING, BorrowRequest.STATUS_APPROVED):
        raise BorrowFlowError("Request already closed.")
    try:
        with transaction.atomic():
            _restore_reserved_stock(borrow_request)
            borrow_request.reject(by_user=by_user, note=note)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_returned(borrow_request: BorrowRequest, by_user, condition: str = ""):
    allowed_statuses = (
        BorrowRequest.STATUS_APPROVED,
        BorrowRequest.STATUS_ISSUED,
        BorrowRequest.STATUS_OVERDUE,
        BorrowRequest.STATUS_PENALTY,
    )
    if borrow_request.status not in allowed_statuses:
        raise BorrowFlowError("Request already closed.")
    try:
        with transaction.atomic():
            _restore_reserved_stock(borrow_request)
            borrow_request.mark_returned(by_user=by_user, condition=condition)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_issued(borrow_request: BorrowRequest, by_user, note: str = ""):
    if borrow_request.status != BorrowRequest.STATUS_APPROVED:
        raise BorrowFlowError("Only approved requests can be marked as collected.")
    try:
        with transaction.atomic():
            # Stock was already reserved at cart stage; issuing only advances state.
            borrow_request.mark_issued(by_user=by_user, note=note)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_penalty(borrow_request: BorrowRequest, by_user, note: str = ""):
    if borrow_request.status not in (BorrowRequest.STATUS_ISSUED, BorrowRequest.STATUS_OVERDUE):
        raise BorrowFlowError("Penalty applies only after collection or overdue.")
    try:
        with transaction.atomic():
            borrow_request.mark_penalty(by_user=by_user, note=note)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc
