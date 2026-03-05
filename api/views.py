import json
import hashlib

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.conf import settings
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from inventory.models import Component
from requests_app.models import BorrowItem, BorrowRequest, LabPolicy
from users.models import APIToken, Group, Profile

from .auth import token_auth_required
from .serializers import serialize_borrow_request, serialize_component, serialize_profile


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limited(request, scope: str, identity: str, limit: int, window_seconds: int) -> bool:
    raw = f"{scope}:{_client_ip(request)}:{(identity or '').strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    key = f"api_rl:{digest}"
    if cache.add(key, 1, timeout=window_seconds):
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    return count > limit


def _parse_json(request):
    try:
        body = request.body.decode('utf-8') if request.body else '{}'
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _admin_required_or_403(request):
    role = getattr(getattr(request.api_user, "profile", None), "role", "")
    if role != Profile.ROLE_ADMIN:
        return JsonResponse({'error': 'Admin role required.'}, status=403)
    return None


@csrf_exempt
@require_POST
def issue_token(request):
    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    identity = (payload.get('identity') or '').strip()
    password = payload.get('password') or ''
    token_issue_limit = int(getattr(settings, "API_TOKEN_ISSUE_RATE_LIMIT", 20))
    token_issue_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))

    if not identity or not password:
        return JsonResponse({'error': 'identity and password are required.'}, status=400)
    if _rate_limited(request, "token_issue", identity, token_issue_limit, token_issue_window):
        return JsonResponse({'error': 'Too many login attempts. Please wait and try again.'}, status=429)

    user = authenticate(request, username=identity, password=password)
    if user is None:
        by_email = User.objects.filter(email__iexact=identity).first()
        if by_email:
            user = authenticate(request, username=by_email.username, password=password)

    if user is None:
        name_matches = User.objects.filter(profile__full_name__iexact=identity).distinct()
        match_count = name_matches.count()
        if match_count > 1:
            return JsonResponse(
                {'error': 'Multiple accounts use this full name. Use username or email.'},
                status=400,
            )
        if match_count == 1:
            user = authenticate(request, username=name_matches.first().username, password=password)

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
    cache_key = "api_components_v1"
    data = cache.get(cache_key)
    if data is None:
        data = [serialize_component(c) for c in Component.objects.all().order_by('name')]
        cache.set(cache_key, data, timeout=60)
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


@require_GET
@token_auth_required
def admin_overview(request):
    admin_error = _admin_required_or_403(request)
    if admin_error:
        return admin_error

    stats = BorrowRequest.objects.aggregate(
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        issued=Count("id", filter=Q(status=BorrowRequest.STATUS_ISSUED)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
        penalty=Count("id", filter=Q(status=BorrowRequest.STATUS_PENALTY)),
        rejected=Count("id", filter=Q(status=BorrowRequest.STATUS_REJECTED)),
        overdue=Count("id", filter=Q(status=BorrowRequest.STATUS_OVERDUE)),
    )
    pending_groups_count = Group.objects.filter(status=Group.STATUS_PENDING).count()
    low_stock_count = Component.objects.filter(available_stock__lte=2).count()
    maintenance_count = BorrowItem.objects.filter(
        borrow_request__status=BorrowRequest.STATUS_RETURNED,
    ).filter(
        Q(borrow_request__return_condition__icontains="service")
        | Q(borrow_request__return_condition__icontains="damaged")
        | Q(borrow_request__return_condition__icontains="not working")
        | Q(borrow_request__return_condition__icontains="missing")
    ).count()
    latest_requests = BorrowRequest.objects.select_related("user", "faculty", "group").prefetch_related("items__component").order_by("-created_at")[:6]
    priority_items = [
        {'key': 'pending_requests', 'count': stats.get('pending', 0), 'url': '/requests/admin/requests/?status=PENDING'},
        {'key': 'overdue_penalty', 'count': (stats.get('overdue', 0) or 0) + (stats.get('penalty', 0) or 0), 'url': '/requests/admin/requests/?status=OVERDUE'},
        {'key': 'pending_groups', 'count': pending_groups_count, 'url': '/users/admin/groups/'},
        {'key': 'low_stock', 'count': low_stock_count, 'url': '/inventory/admin/components/?stock=low'},
        {'key': 'maintenance_flags', 'count': maintenance_count, 'url': '/requests/admin/maintenance/'},
    ]

    return JsonResponse(
        {
            'overview': {
                'stats': stats,
                'pending_groups_count': pending_groups_count,
                'low_stock_count': low_stock_count,
                'maintenance_count': maintenance_count,
                'priority_items': priority_items,
                'latest_requests': [serialize_borrow_request(slip) for slip in latest_requests],
            }
        }
    )


@require_GET
@token_auth_required
def admin_console_map(request):
    admin_error = _admin_required_or_403(request)
    if admin_error:
        return admin_error

    return JsonResponse(
        {
            'console_map': {
                'dashboard': '/requests/admin/',
                'request_console': '/requests/admin/requests/',
                'inventory_console': '/inventory/admin/components/',
                'policy_console': '/requests/admin/component-console/',
                'maintenance_console': '/requests/admin/maintenance/',
                'analytics_console': '/requests/admin/analytics/',
                'reports_console': '/requests/admin/reports-console/',
                'profile_console': '/users/admin/profile-console/',
            }
        }
    )


@require_GET
@token_auth_required
def admin_policy(request):
    admin_error = _admin_required_or_403(request)
    if admin_error:
        return admin_error

    policy, _ = LabPolicy.objects.get_or_create(id=1)
    return JsonResponse(
        {
            'policy': {
                'per_day_fine': policy.per_day_fine,
                'grace_days': policy.grace_days,
                'overdue_penalty_trigger_days': policy.overdue_penalty_trigger_days,
                'damaged_fine': policy.damaged_fine,
                'missing_parts_fine': policy.missing_parts_fine,
                'not_working_fine': policy.not_working_fine,
                'maintenance_keywords': policy.maintenance_keywords,
                'notes': policy.notes,
            }
        }
    )


@csrf_exempt
@require_POST
@token_auth_required
def admin_update_policy(request):
    admin_error = _admin_required_or_403(request)
    if admin_error:
        return admin_error

    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    policy, _ = LabPolicy.objects.get_or_create(id=1)
    int_fields = [
        "per_day_fine",
        "grace_days",
        "overdue_penalty_trigger_days",
        "damaged_fine",
        "missing_parts_fine",
        "not_working_fine",
    ]
    for field in int_fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if not isinstance(value, int) or value < 0:
            return JsonResponse({'error': f'{field} must be a non-negative integer.'}, status=400)
        setattr(policy, field, value)

    if "maintenance_keywords" in payload:
        value = payload.get("maintenance_keywords")
        if not isinstance(value, str):
            return JsonResponse({'error': 'maintenance_keywords must be a string.'}, status=400)
        policy.maintenance_keywords = value.strip()
    if "notes" in payload:
        value = payload.get("notes")
        if not isinstance(value, str):
            return JsonResponse({'error': 'notes must be a string.'}, status=400)
        policy.notes = value.strip()
    policy.save()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
@token_auth_required
def admin_update_component_fines(request, component_id: int):
    admin_error = _admin_required_or_403(request)
    if admin_error:
        return admin_error

    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    component = Component.objects.filter(id=component_id).first()
    if not component:
        return JsonResponse({'error': 'Component not found.'}, status=404)

    fine_fields = [
        "fine_per_day",
        "fine_damaged",
        "fine_missing_parts",
        "fine_not_working",
    ]
    touched = []
    for field in fine_fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if value is None:
            setattr(component, field, None)
            touched.append(field)
            continue
        if not isinstance(value, int) or value < 0:
            return JsonResponse({'error': f'{field} must be a non-negative integer or null.'}, status=400)
        setattr(component, field, value)
        touched.append(field)
    if not touched:
        return JsonResponse({'error': 'No fine fields provided.'}, status=400)
    component.save(update_fields=touched)
    return JsonResponse({'component': serialize_component(component)})
