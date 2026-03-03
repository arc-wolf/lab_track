from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Reservation


class Command(BaseCommand):
    help = "Clear expired reservations and release stock"

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Reservation.objects.filter(is_active=True, expires_at__lte=now)
        count = 0
        for res in expired.select_related("component"):
            res.expire_and_release()
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Cleared {count} expired reservations."))
