import json

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from inventory.models import Component
from requests_app.models import BorrowRequest
from users.models import APIToken, Group, Profile

from .auth import token_auth_required
from .serializers import serialize_borrow_request, serialize_component, serialize_profile


def _parse_json(request):
    try:
        body = request.body.decode('utf-8') if request.body else '{}'
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


@csrf_exempt
@require_POST
def issue_token(request):
    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    identity = (payload.get('identity') or '').strip()
    password = payload.get('password') or ''

    if not identity or not password:
        return JsonResponse({'error': 'identity and password are required.'}, status=400)

    user = authenticate(request, username=identity, password=password)
    if user is None:
        by_email = User.objects.filter(email__iexact=identity).first()
        if by_email:
            user = authenticate(request, username=by_email.username, password=password)

    if user is None:
        by_name = User.objects.filter(profile__full_name__iexact=identity).first()
        if by_name:
            user = authenticate(request, username=by_name.username, password=password)

    if user is None:
        return JsonResponse({'error': 'Invalid credentials.'}, status=401)

    token, _ = APIToken.objects.get_or_create(user=user)
    token.rotate()
    return JsonResponse({'token': token.key, 'user': serialize_profile(user)})


@csrf_exempt
@require_POST
@token_auth_required
def logout_token(request):
    request.api_token.rotate()
    return JsonResponse({'ok': True})


@require_GET
@token_auth_required
def me(request):
    return JsonResponse({'user': serialize_profile(request.api_user)})


@require_GET
@token_auth_required
def components(request):
    data = [serialize_component(c) for c in Component.objects.all().order_by('name')]
    return JsonResponse({'components': data})


@require_GET
@token_auth_required
def borrow_requests(request):
    user = request.api_user
    profile = getattr(user, 'profile', None)
    role = getattr(profile, 'role', '')

    slips = BorrowRequest.objects.select_related('user', 'faculty', 'group').prefetch_related('items__component')

    if role == Profile.ROLE_ADMIN:
        queryset = slips.order_by('-created_at')[:100]
    elif role == Profile.ROLE_FACULTY:
        queryset = slips.filter(faculty=user).order_by('-created_at')[:100]
    else:
        group = Group.objects.filter(code__iexact=(profile.group_id or '')).first() if profile else None
        if group:
            queryset = slips.filter(group=group).order_by('-created_at')[:100]
        else:
            queryset = slips.filter(user=user).order_by('-created_at')[:100]

    return JsonResponse({'requests': [serialize_borrow_request(slip) for slip in queryset]})
