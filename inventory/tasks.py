from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import CartItem


@shared_task
def cleanup_expired_cart_items():
    expiry_time = timezone.now() - timedelta(hours=48)

    expired_items = CartItem.objects.filter(
        slip_generated=False,
        added_at__lt=expiry_time
    )

    for item in expired_items:
        component = item.component
        component.available_stock += item.quantity
        component.save()

        item.delete()

    return f"Cleaned {expired_items.count()} expired cart items"