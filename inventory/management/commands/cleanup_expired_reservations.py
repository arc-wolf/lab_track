from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.services import clean_expired_reservations
from users.models import EmailOTP


class Command(BaseCommand):
    help = "Production cleanup command to release expired reservations and purge stale OTPs."

    def handle(self, *args, **options):
        self.stdout.write("Running production maintenance cleanup...")

        # 1. Release expired component reservations & restore stock
        clean_expired_reservations(user=None, user_ids=None)
        self.stdout.write(self.style.SUCCESS("Expired component reservations successfully released."))

        # 2. Mark stale OTP records older than 24 hours as used
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        purged_count, _ = EmailOTP.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Purged {purged_count} stale OTP records."))
