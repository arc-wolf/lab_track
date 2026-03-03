from celery import shared_task
from django.utils import timezone

from .models import Reservation


@shared_task
def cleanup_expired_reservations():
    expired = Reservation.objects.filter(is_active=True, expires_at__lte=timezone.now())
    count = 0
    for res in expired.select_related("component"):
        res.expire_and_release()
        count += 1
    return f"Cleared {count} expired reservations"
