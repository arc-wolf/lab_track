import logging
from typing import Optional
from django.contrib.auth.models import User
from users.models import AuditLog

logger = logging.getLogger(__name__)


def record_audit_log(
    action: str,
    target_object: str = "",
    user: Optional[User] = None,
    details: str = "",
    ip_address: Optional[str] = None,
) -> Optional[AuditLog]:
    """
    Safely record an administrative audit log entry without interrupting execution flow.
    """
    try:
        entry = AuditLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            action=action,
            target_object=target_object,
            details=details,
            ip_address=ip_address,
        )
        return entry
    except Exception as exc:
        logger.error("Failed to record audit log: %s", exc, exc_info=True)
        return None
