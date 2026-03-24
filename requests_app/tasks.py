from datetime import timedelta
import logging

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail

from .models import BorrowRequest

logger = logging.getLogger(__name__)


@shared_task
def send_due_reminders():
    """
    Send reminder emails at day 40 for items that are still not returned/terminated.
    """
    now = timezone.now().date()
    target_date = now + timedelta(days=5)  # 40th day -> 5 days before 45-day due
    qs = BorrowRequest.objects.filter(
        status__in=[BorrowRequest.STATUS_ISSUED],
        reminder_sent=False,
        due_date__isnull=False,
        due_date=target_date,
    )

    processed = 0
    for req in qs:
        processed += 1
        recipients = set()
        if req.user.email:
            recipients.add(req.user.email)
        if req.faculty and req.faculty.email:
            recipients.add(req.faculty.email)
        if req.group and req.group.faculty and req.group.faculty.email:
            recipients.add(req.group.faculty.email)
        subject = "LabTrack return reminder"
        body = (
            f"Your borrow request #{req.id} is due on {req.due_date}. "
            f"Please return the components or contact lab admin."
        )
        if recipients:
            try:
                send_mail(subject, body, None, list(recipients), fail_silently=False)
                req.reminder_sent = True
                req.save(update_fields=["reminder_sent"])
            except Exception as exc:  # pragma: no cover - log delivery issues
                logger.warning("Reminder email failed for request %s: %s", req.id, exc)
    return f"Processed {processed} reminders"


@shared_task
def update_overdue_requests():
    """
    Move issued requests to overdue once due date passes.
    """
    qs = BorrowRequest.objects.filter(
        status__in=[BorrowRequest.STATUS_ISSUED],
        due_date__isnull=False,
    )
    updated = 0
    for req in qs:
        before = req.status
        req.auto_mark_overdue()
        req.refresh_from_db(fields=["status"])
        if before != req.status and req.status == BorrowRequest.STATUS_OVERDUE:
            updated += 1
    return f"Marked {updated} requests as overdue"
