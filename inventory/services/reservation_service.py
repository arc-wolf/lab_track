"""Reservation service primitives for inventory operations.

Stub for blueprint Phase 2. Extract reservation hold/release logic from views.py.
"""

from django.db import transaction
from django.core.exceptions import ValidationError

from inventory.models import CartItem, Reservation, Component


def create_reservation(user_profile_id: int, component_id: int, quantity: int) -> Reservation:
    """
    Create or update reservation (hold) for a component.
    
    Ensures available_stock >= quantity, creates CartItem + Reservation atomically.
    """
    with transaction.atomic():
        component = Component.objects.select_for_update().get(id=component_id)
        if component.available_stock < quantity:
            raise ValidationError(f"Insufficient stock: {component.available_stock} < {quantity}")
        
        # Check/merge existing cart item for profile
        cart_item, created = CartItem.objects.get_or_create(
            student_id=user_profile_id,
            component=component,
            defaults={"quantity": quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save(update_fields=["quantity"])
        
        reservation = Reservation.objects.create(
            cart_item=cart_item,
            component=component,
            quantity=quantity
        )
        
        # Mutate stock
        component.available_stock -= quantity
        component.save(update_fields=["available_stock"])
        
        return reservation


def release_reservation(reservation_id: int) -> None:
    """
    Release reservation hold, restore available_stock.
    """
    with transaction.atomic():
        reservation = Reservation.objects.select_for_update().get(id=reservation_id)
        component = reservation.component
        
        component.available_stock += reservation.quantity
        component.save(update_fields=["available_stock"])
        
        reservation.delete()


# TODO: Add batch_reserve, validate_cart, etc. for full extraction

