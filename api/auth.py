from functools import wraps

from django.http import JsonResponse

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

        token.touch()
        request.api_user = token.user
        request.api_token = token
        return view_func(request, *args, **kwargs)

    return _wrapped
