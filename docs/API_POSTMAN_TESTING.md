# LabTrack API Guide for Postman

Last updated: March 5, 2026

## 1) Base Setup
- Base URL (local): `http://127.0.0.1:8000/api`
- Content type: `application/json`
- Auth scheme for protected endpoints: `Authorization: Token <token>`

Recommended Postman environment variables:
- `base_url` = `http://127.0.0.1:8000/api`
- `token` = (set after login)

## 2) Endpoint List (Quick View)
- `POST {{base_url}}/auth/token/` -> issue API token
- `POST {{base_url}}/auth/logout/` -> rotate/logout token
- `GET {{base_url}}/me/` -> current user profile
- `GET {{base_url}}/components/` -> component list
- `GET {{base_url}}/requests/` -> role-scoped borrow requests
- `GET {{base_url}}/admin/overview/` -> admin dashboard glimpse payload
- `GET {{base_url}}/admin/console-map/` -> admin web console route map
- `GET {{base_url}}/admin/policy/` -> read global penalty/maintenance policy
- `POST {{base_url}}/admin/policy/update/` -> update global policy parameters
- `POST {{base_url}}/admin/components/<id>/fines/` -> update per-component fine overrides

## 3) Detailed Postman Requests

### A) Issue Token
Method:
- `POST`

URL:
- `{{base_url}}/auth/token/`

Headers:
- `Content-Type: application/json`

Body (raw JSON):
```json
{
  "identity": "api_admin",
  "password": "pass1234"
}
```

`identity` accepted values:
- username
- email
- full name (if unique)

Success response (`200`):
```json
{
  "token": "64_hex_chars...",
  "user": {
    "id": 1,
    "username": "api_admin",
    "email": "api_admin@example.com",
    "full_name": "Api Admin",
    "role": "admin",
    "group_id": ""
  }
}
```

Common errors:
- `400`: invalid JSON / missing fields / ambiguous full name
- `401`: invalid credentials
- `429`: too many login attempts (rate limited)

### B) Logout Token
Method:
- `POST`

URL:
- `{{base_url}}/auth/logout/`

Headers:
- `Authorization: Token {{token}}`

Body:
- none

Success response (`200`):
```json
{
  "ok": true
}
```

Common errors:
- `401`: missing/invalid/expired token

### C) Current User (`me`)
Method:
- `GET`

URL:
- `{{base_url}}/me/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`):
```json
{
  "user": {
    "id": 3,
    "username": "api_student",
    "email": "api_student@example.com",
    "full_name": "Api Student",
    "role": "student",
    "group_id": "APIGRP",
    "email_locked": true
  }
}
```

Common errors:
- `401`: missing/invalid/expired token

Notes:
- `email_locked=true` means email is frozen for that account profile.
- Student/faculty are expected to be locked after verification.

### D) Components
Method:
- `GET`

URL:
- `{{base_url}}/components/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`):
```json
{
  "components": [
    {
      "id": 1,
      "name": "Raspberry Pi",
      "category": "Boards",
      "total_stock": 5,
      "available_stock": 3,
      "student_limit": 0,
      "faculty_limit": 0,
      "fine_per_day": 20,
      "fine_damaged": 500,
      "fine_missing_parts": 700,
      "fine_not_working": 1000
    }
  ]
}
```

Common errors:
- `401`: missing/invalid/expired token

Notes:
- Fine fields are per-component overrides.
- `null` means "use global value from Lab Policy".

### E) Borrow Requests
Method:
- `GET`

URL:
- `{{base_url}}/requests/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`):
```json
{
  "requests": [
    {
      "id": 42,
      "status": "PENDING",
      "created_at": "2026-03-04T10:30:00+00:00",
      "due_date": "2026-04-18",
      "project_title": "Home Automation",
      "faculty": "api_faculty",
      "requester": "api_student",
      "requester_role": "student",
      "student": "api_student",
      "group": "APIGRP",
      "items": [
        {
          "component": "Raspberry Pi",
          "quantity": 1
        }
      ]
    }
  ]
}
```

Notes:
- `requester` and `requester_role` are the canonical fields for who created the request.
- `student` is still present for backward compatibility in existing clients.

Role scoping:
- admin: latest 100 requests (all users)
- faculty: latest 100 requests assigned to that faculty
- student: latest 100 requests for own group; fallback to own requests if no group

Common errors:
- `401`: missing/invalid/expired token

### F) Admin Overview (Glimpse Payload)
Method:
- `GET`

URL:
- `{{base_url}}/admin/overview/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`, admin only):
```json
{
  "overview": {
    "stats": {
      "pending": 4,
      "approved": 2,
      "issued": 1,
      "returned": 15,
      "penalty": 1,
      "rejected": 3,
      "overdue": 1
    },
    "pending_groups_count": 2,
    "low_stock_count": 3,
    "maintenance_count": 2,
    "priority_items": [
      {
        "key": "pending_requests",
        "count": 4,
        "url": "/requests/admin/requests/?status=PENDING"
      }
    ],
    "latest_requests": []
  }
}
```

Common errors:
- `401`: missing/invalid token
- `403`: authenticated user is not admin

### G) Admin Console Map
Method:
- `GET`

URL:
- `{{base_url}}/admin/console-map/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`, admin only):
```json
{
  "console_map": {
    "dashboard": "/requests/admin/",
    "request_console": "/requests/admin/requests/",
    "inventory_console": "/inventory/admin/components/",
    "policy_console": "/requests/admin/component-console/",
    "maintenance_console": "/requests/admin/maintenance/",
    "analytics_console": "/requests/admin/analytics/",
    "reports_console": "/requests/admin/reports-console/",
    "profile_console": "/users/admin/profile-console/"
  }
}
```

### H) Admin Policy (Read)
Method:
- `GET`

URL:
- `{{base_url}}/admin/policy/`

Headers:
- `Authorization: Token {{token}}`

Success response (`200`, admin only):
```json
{
  "policy": {
    "per_day_fine": 10,
    "grace_days": 2,
    "overdue_penalty_trigger_days": 5,
    "damaged_fine": 500,
    "missing_parts_fine": 700,
    "not_working_fine": 1000,
    "maintenance_keywords": "service,damaged,not working,missing",
    "notes": ""
  }
}
```

### I) Admin Policy (Update)
Method:
- `POST`

URL:
- `{{base_url}}/admin/policy/update/`

Headers:
- `Authorization: Token {{token}}`
- `Content-Type: application/json`

Body (any subset of fields):
```json
{
  "per_day_fine": 15,
  "grace_days": 1,
  "maintenance_keywords": "service,damaged",
  "notes": "Updated by API"
}
```

Success response (`200`):
```json
{
  "ok": true
}
```

### J) Component Fine Overrides (Update)
Method:
- `POST`

URL:
- `{{base_url}}/admin/components/1/fines/`

Headers:
- `Authorization: Token {{token}}`
- `Content-Type: application/json`

Body (`int` or `null` for each field):
```json
{
  "fine_per_day": 25,
  "fine_damaged": 1000,
  "fine_missing_parts": null,
  "fine_not_working": 1500
}
```

Success response (`200`):
```json
{
  "component": {
    "id": 1,
    "name": "Raspberry Pi",
    "fine_per_day": 25,
    "fine_damaged": 1000,
    "fine_missing_parts": null,
    "fine_not_working": 1500
  }
}
```

## 4) Token Rules (Important for Testing)
- Token format in header must start with exact prefix: `Token `
- Example: `Authorization: Token 0123abcd...`
- Tokens can expire by:
  - max age days (`API_TOKEN_MAX_AGE_DAYS`)
  - idle timeout seconds (`API_TOKEN_IDLE_TIMEOUT_SECONDS`)
- Calling logout rotates token immediately; old token becomes unusable.

## 5) Postman Test Script (Save Token Automatically)
Add this script in the `Tests` tab of the `auth/token` request:

```javascript
const jsonData = pm.response.json();
if (jsonData.token) {
  pm.environment.set("token", jsonData.token);
}
```

## 6) Suggested Postman Collection Order
1. `POST /auth/token/`
2. `GET /me/`
3. `GET /components/`
4. `GET /requests/`
5. `GET /admin/overview/` (admin token)
6. `GET /admin/console-map/` (admin token)
7. `POST /auth/logout/`
8. `GET /me/` again (should return `401` with old token)

## 7) Notes for Reliable Local Testing
- Start server: `python manage.py runserver`
- Ensure test users exist with known passwords.
- If rate-limited on token issuance, wait for rate-limit window or use different identity/IP.
- If using HTTPS-only cookies in production, API token endpoints still use header auth and are Postman-friendly.
