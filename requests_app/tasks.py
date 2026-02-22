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
        status=BorrowRequest.STATUS_APPROVED,
        reminder_sent=False,
        due_date__isnull=False,
        due_date__gte=target_date,
        due_date__lte=target_date,
    )

    for req in qs:
        recipients = [req.student.email]
        if req.faculty and req.faculty.email:
            recipients.append(req.faculty.email)
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
