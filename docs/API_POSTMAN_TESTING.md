# LabTrack API Guide for Postman

Last updated: March 4, 2026

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
    "group_id": "APIGRP"
  }
}
```

Common errors:
- `401`: missing/invalid/expired token

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
      "faculty_limit": 0
    }
  ]
}
```

Common errors:
- `401`: missing/invalid/expired token

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

Role scoping:
- admin: latest 100 requests (all users)
- faculty: latest 100 requests assigned to that faculty
- student: latest 100 requests for own group; fallback to own requests if no group

Common errors:
- `401`: missing/invalid/expired token

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
5. `POST /auth/logout/`
6. `GET /me/` again (should return `401` with old token)

## 7) Notes for Reliable Local Testing
- Start server: `python manage.py runserver`
- Ensure test users exist with known passwords.
- If rate-limited on token issuance, wait for rate-limit window or use different identity/IP.
- If using HTTPS-only cookies in production, API token endpoints still use header auth and are Postman-friendly.
