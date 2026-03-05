from django.contrib.auth.models import User

from inventory.models import Component
from requests_app.models import BorrowRequest


def serialize_profile(user: User) -> dict:
    profile = getattr(user, 'profile', None)
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': getattr(profile, 'full_name', '') or user.get_full_name() or user.username,
        'role': getattr(profile, 'role', ''),
        'group_id': getattr(profile, 'group_id', ''),
        'email_locked': bool(getattr(profile, 'email_locked', False)),
    }


def serialize_component(component: Component) -> dict:
    return {
        'id': component.id,
        'name': component.name,
        'category': component.category,
        'total_stock': component.total_stock,
        'available_stock': component.available_stock,
        'student_limit': component.student_limit,
        'faculty_limit': component.faculty_limit,
        'fine_per_day': component.fine_per_day,
        'fine_damaged': component.fine_damaged,
        'fine_missing_parts': component.fine_missing_parts,
        'fine_not_working': component.fine_not_working,
    }


def serialize_borrow_request(slip: BorrowRequest) -> dict:
    requester_role = getattr(getattr(slip.user, "profile", None), "role", "")
    return {
        'id': slip.id,
        'status': slip.status,
        'created_at': slip.created_at.isoformat() if slip.created_at else None,
        'due_date': slip.due_date.isoformat() if slip.due_date else None,
        'project_title': slip.project_title,
        'faculty': slip.faculty.username if slip.faculty else None,
        'requester': slip.user.username,
        'requester_role': requester_role,
        'student': slip.user.username,
        'group': slip.group.code if slip.group else None,
        'items': [
            {
                'component': item.component.name,
                'quantity': item.quantity,
            }
            for item in slip.items.all()
        ],
    }
