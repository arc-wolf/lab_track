from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail

from .models import BorrowRequest


@shared_task
def send_due_reminders():
    """
    Send reminder emails at day 40 for items that are still not returned/terminated.
    """
    now = timezone.now().date()
    target_date = now + timedelta(days=5)  # 40th day -> 5 days before 45-day due
    qs = BorrowRequest.objects.filter(
        status__in=[BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_ISSUED],
        reminder_sent=False,
        due_date__isnull=False,
        due_date__gte=target_date,
        due_date__lte=target_date,
    )

    for req in qs:
        recipients = []
        if req.user.email:
            recipients.append(req.user.email)
        subject = "LabTrack return reminder"
        body = (
            f"Your borrow request #{req.id} is due on {req.due_date}. "
            f"Please return the components or contact lab admin."
        )
        try:
            if recipients:
                send_mail(subject, body, None, recipients, fail_silently=True)
        finally:
            req.reminder_sent = True
            req.save(update_fields=["reminder_sent"])
    return f"Processed {qs.count()} reminders"


@shared_task
def update_overdue_requests():
    """
    Move approved/issued requests to overdue once due date passes.
    """
    qs = BorrowRequest.objects.filter(
        status__in=[BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_ISSUED],
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
