from django.db import transaction

from requests_app.models import BorrowRequest
from users.services.audit_service import record_audit_log


class BorrowFlowError(Exception):
    """Raised when a lifecycle transition is invalid."""


def _restore_reserved_stock(borrow_request: BorrowRequest):
    for item in borrow_request.items.select_related("component"):
        item.component.adjust_available(item.quantity)


def approve_request(borrow_request: BorrowRequest, by_user):
    try:
        with transaction.atomic():
<<<<<<< HEAD
            locked_request = BorrowRequest.objects.select_for_update().get(id=borrow_request.id)
            if locked_request.status != BorrowRequest.STATUS_PENDING:
                raise BorrowFlowError("Request already processed.")
            locked_request.approve(by_user=by_user)
=======
            borrow_request.approve(by_user=by_user)
            record_audit_log(
                action="APPROVE_SLIP",
                target_object=f"BorrowRequest #{borrow_request.id}",
                user=by_user,
                details=f"Approved for user {borrow_request.user.username}",
            )
>>>>>>> e03ae81 (latest on 11aug2026)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def reject_request(borrow_request: BorrowRequest, by_user, note: str = ""):
    try:
        with transaction.atomic():
<<<<<<< HEAD
            locked_request = BorrowRequest.objects.select_for_update().get(id=borrow_request.id)
            if locked_request.status != BorrowRequest.STATUS_PENDING:
                raise BorrowFlowError("Only pending requests can be rejected.")
            _restore_reserved_stock(locked_request)
            locked_request.reject(by_user=by_user, note=note)
=======
            _restore_reserved_stock(borrow_request)
            borrow_request.reject(by_user=by_user, note=note)
            record_audit_log(
                action="REJECT_SLIP",
                target_object=f"BorrowRequest #{borrow_request.id}",
                user=by_user,
                details=f"Rejected. Remarks: {note}",
            )
>>>>>>> e03ae81 (latest on 11aug2026)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_returned(borrow_request: BorrowRequest, by_user, condition: str = ""):
    try:
        with transaction.atomic():
<<<<<<< HEAD
            locked_request = BorrowRequest.objects.select_for_update().get(id=borrow_request.id)
            allowed_statuses = (
                BorrowRequest.STATUS_ISSUED,
                BorrowRequest.STATUS_OVERDUE,
                BorrowRequest.STATUS_PENALTY,
            )
            if locked_request.status not in allowed_statuses:
                raise BorrowFlowError("Only collected, overdue, or penalty requests can be returned.")
            _restore_reserved_stock(locked_request)
            locked_request.mark_returned(by_user=by_user, condition=condition)
=======
            _restore_reserved_stock(borrow_request)
            borrow_request.mark_returned(by_user=by_user, condition=condition)
            record_audit_log(
                action="MARK_RETURNED",
                target_object=f"BorrowRequest #{borrow_request.id}",
                user=by_user,
                details=f"Condition: {condition or 'Good'}",
            )
>>>>>>> e03ae81 (latest on 11aug2026)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_issued(borrow_request: BorrowRequest, by_user, note: str = ""):
    try:
        with transaction.atomic():
<<<<<<< HEAD
            locked_request = BorrowRequest.objects.select_for_update().get(id=borrow_request.id)
            if locked_request.status != BorrowRequest.STATUS_APPROVED:
                raise BorrowFlowError("Only approved requests can be marked as collected.")
            locked_request.mark_issued(by_user=by_user, note=note)
=======
            # Stock was already reserved at cart stage; issuing only advances state.
            borrow_request.mark_issued(by_user=by_user, note=note)
            record_audit_log(
                action="MARK_ISSUED",
                target_object=f"BorrowRequest #{borrow_request.id}",
                user=by_user,
                details=note,
            )
>>>>>>> e03ae81 (latest on 11aug2026)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc


def mark_request_penalty(borrow_request: BorrowRequest, by_user, note: str = ""):
    try:
        with transaction.atomic():
<<<<<<< HEAD
            locked_request = BorrowRequest.objects.select_for_update().get(id=borrow_request.id)
            if locked_request.status not in (BorrowRequest.STATUS_ISSUED, BorrowRequest.STATUS_OVERDUE):
                raise BorrowFlowError("Penalty applies only after collection or overdue.")
            locked_request.mark_penalty(by_user=by_user, note=note)
=======
            borrow_request.mark_penalty(by_user=by_user, note=note)
            record_audit_log(
                action="APPLY_PENALTY",
                target_object=f"BorrowRequest #{borrow_request.id}",
                user=by_user,
                details=note,
            )
>>>>>>> e03ae81 (latest on 11aug2026)
    except ValueError as exc:
        raise BorrowFlowError("Request already processed.") from exc

