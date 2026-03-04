from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from users.models import APIToken


def token_auth_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Token '):
            return JsonResponse({'error': 'Missing token.'}, status=401)

        token_key = header.replace('Token ', '', 1).strip()
        if not token_key:
            return JsonResponse({'error': 'Missing token.'}, status=401)

        token = APIToken.objects.select_related('user__profile').filter(key=token_key).first()
        if not token:
            return JsonResponse({'error': 'Invalid token.'}, status=401)

        now = timezone.now()
        max_age_days = int(getattr(settings, "API_TOKEN_MAX_AGE_DAYS", 30))
        idle_timeout_seconds = int(getattr(settings, "API_TOKEN_IDLE_TIMEOUT_SECONDS", 1209600))

        if token.created_at and (now - token.created_at).days > max_age_days:
            return JsonResponse({'error': 'Token expired.'}, status=401)
        if token.last_used_at and (now - token.last_used_at).total_seconds() > idle_timeout_seconds:
            return JsonResponse({'error': 'Token expired.'}, status=401)

        token.touch()
        request.api_user = token.user
        request.api_token = token
        return view_func(request, *args, **kwargs)

    return _wrapped
